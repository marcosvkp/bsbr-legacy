"""Algoritmo de reweight — porta pura de references/BSStarAnalyzer/player_performance.py.

Regras (Plan.md §3.4):
- acc mediana dos scores válidos comparada à curva esperada por estrelas;
- delta = -(mediana - esperada) × 100 × SENSITIVITY, clamp ±CLAMP;
- confiança pela amostra: n>=HIGH_MIN→high, n>=MEDIUM_MIN→medium, senão low;
- n < MIN_SCORES → sem sugestão;
- auto-aplicação apenas com confiança alta e |delta| ≤ AUTO_APPLY_MAX.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

# Amostra mínima por dificuldade. O legado usava 10 (leaderboards globais com
# centenas de scores); os leaderboards BR do BSBR têm ~10-15 scores, então o
# mínimo foi reescalado — a confiança (low/medium/high) já sinaliza amostras
# pequenas e nada é auto-aplicado abaixo de high.
MIN_SCORES = 6
# PP mínimo do jogador para a amostra contar. O valor original (1000.0) era
# calibrado para a escala do ScoreSaber; no BSBR a curva própria dá valores
# menores (top ~5000pp, topo competitivo a partir de ~300pp), então o limiar
# foi reescalado para o topo competitivo brasileiro.
MIN_PLAYER_PP = 300.0
RANK_DECAY = 0.97
SENSITIVITY = 0.25  # 1% de acc ≈ 0.25★
CLAMP_STARS = 2.0
AUTO_APPLY_MAX = 1.0
MEDIUM_MIN = 40
HIGH_MIN = 100
MAX_ACC = 1.05  # descarta scores impossíveis (modifiers)


def expected_median_acc(stars: float) -> float:
    """Curva empírica do legado: 1★→96.5% … 5★→90.5% … piso 78%."""
    return max(0.78, 0.98 - stars * 0.015)


@dataclass(frozen=True)
class ReweightResult:
    sample_size: int
    weighted_acc: float | None
    median_acc: float | None
    fc_rate: float | None
    expected_acc: float | None
    delta_stars: float
    suggested_stars: float
    confidence: str  # none | low | medium | high
    direction: str  # increase | decrease | keep
    reason: str
    can_auto_apply: bool


def analyze_difficulty(
    scores: Iterable[Mapping],
    current_stars: float,
    *,
    min_player_pp: float | None = MIN_PLAYER_PP,
) -> ReweightResult:
    """Avalia um mapa/dificuldade.

    Cada score é um Mapping com chaves: ``acc`` (0..1), ``base_score`` (>0),
    ``full_combo`` (bool) e ``player_pp`` (float).

    ``min_player_pp=None`` desliga o filtro por PP — usado pela amostra global
    do ScoreSaber, cujo payload não entrega PP confiável por jogador.
    """
    valid: list[tuple[float, float]] = []  # (acc, weight)
    fc_count = 0
    total = 0
    for i, s in enumerate(scores):
        total += 1
        base = float(s.get("base_score") or 0)
        acc = float(s.get("acc") or 0)
        if base <= 0 or acc <= 0 or acc > MAX_ACC:
            continue
        if s.get("full_combo"):
            fc_count += 1
        player_pp = float(s.get("player_pp") or 0)
        if min_player_pp is not None and player_pp < min_player_pp:
            continue
        valid.append((acc, RANK_DECAY**i))

    fc_rate = fc_count / total if total else None

    if len(valid) < MIN_SCORES:
        return ReweightResult(
            sample_size=len(valid),
            weighted_acc=None,
            median_acc=None,
            fc_rate=fc_rate,
            expected_acc=None,
            delta_stars=0.0,
            suggested_stars=current_stars,
            confidence="none",
            direction="keep",
            reason=f"Amostra insuficiente ({len(valid)} scores, mínimo {MIN_SCORES})",
            can_auto_apply=False,
        )

    total_weight = sum(w for _, w in valid)
    weighted_acc = sum(a * w for a, w in valid) / total_weight
    median_acc = statistics.median(a for a, _ in valid)

    expected = expected_median_acc(current_stars)
    diff = median_acc - expected  # positivo = mais fácil que o esperado
    raw_delta = max(-CLAMP_STARS, min(CLAMP_STARS, -diff * 100 * SENSITIVITY))
    # Delta único já arredondado: o valor reportado é EXATAMENTE o aplicado
    # (sem drift de float entre reason/sugestão/aplicação)
    delta = round(raw_delta, 2)

    confidence = "high" if len(valid) >= HIGH_MIN else ("medium" if len(valid) >= MEDIUM_MIN else "low")
    direction = "increase" if delta > 0.05 else ("decrease" if delta < -0.05 else "keep")
    reason = (
        f"Mediana observada {median_acc * 100:.1f}% vs esperada {expected * 100:.1f}% "
        f"para {current_stars:.2f}★ (n={len(valid)}) → {'+' if delta >= 0 else ''}{delta:.2f}★"
    )

    return ReweightResult(
        sample_size=len(valid),
        weighted_acc=round(weighted_acc, 4),
        median_acc=round(median_acc, 4),
        fc_rate=round(fc_rate, 4) if fc_rate is not None else None,
        expected_acc=round(expected, 4),
        delta_stars=delta,
        suggested_stars=round(max(0.1, current_stars + delta), 2),
        confidence=confidence,
        direction=direction,
        reason=reason,
        can_auto_apply=(confidence == "high" and abs(delta) <= AUTO_APPLY_MAX),
    )


def extract_scores_from_leaderboard(scores: Iterable[Mapping]) -> list[dict]:
    """Adapta o payload bruto do ScoreSaber para o formato de analyze_difficulty."""
    out: list[dict] = []
    for s in scores:
        info = s.get("leaderboardPlayerInfo") or {}
        max_score_hint = s.get("maxScore")  # presente em alguns payloads
        base = float(s.get("baseScore") or 0)
        acc = None
        if s.get("accuracy"):
            acc = float(s["accuracy"])
        elif max_score_hint:
            acc = base / float(max_score_hint)
        out.append(
            {
                "base_score": base,
                "acc": acc or 0.0,
                "full_combo": bool(s.get("fullCombo")),
                "player_pp": float(info.get("pp") or 0),
            }
        )
    return out
