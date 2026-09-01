"""Reweight com persistência (Plan.md §3.4, fase F4).

- ``collect_suggestions``: roda o algoritmo puro sobre os scores JÁ SINCRONIZADOS
  no banco (o batch semanal sincroniza antes), cria/atualiza sugestões e
  auto-aplica as de confiança alta com |delta| ≤ 1★.
- ``apply_suggestion`` / ``reject_suggestion``: ação de staff; aplicar grava
  RatingHistory (antes→depois) e reescala os sub-stars proporcionalmente.
"""

from __future__ import annotations

import asyncio
import statistics
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import (
    Difficulty,
    Map,
    MapStatus,
    Player,
    RatingHistory,
    ReweightSuggestion,
    Score,
    SuggestionStatus,
)
from app.services.reweight import (
    AUTO_APPLY_MAX,
    MIN_PLAYER_PP,
    MIN_SCORES,
    ReweightResult,
    analyze_difficulty,
)

_SYSTEM_REVIEWER = "system"

# Cache da predição do ML por mapa (evita re-baixar o beatmap no processo).
_ML_CACHE: dict[str, dict[str, float]] = {}

# ── Amostra global e remap por faixa de estrelas ─────────────────────────
# Janela superior da amostra global: só os top-100 por rank entram na mediana
# não ponderada (proteção estatística; o payload do SS não traz PP confiável).
GLOBAL_SAMPLE_LIMIT = 100
# Alvo de consistência do pool remap: 50+ → medium, 100+ → high (auto-aplica).
REMAP_TARGET = 50
REMAP_BAND = 0.5  # faixa de estrelas em torno da dificuldade alvo
REMAP_MAX_DONORS = 15  # teto de candidatos consultados
REMAP_MIN_DONORS = 3  # mínimo de doadores aceitos para o remap contar
REMAP_SIGMA = 2.0  # filtro de coerência de acc (desvios da mediana da faixa)
REMAP_POOL_CAP = 150  # teto de scores no pool remap


@dataclass(frozen=True)
class ReweightSample:
    """Amostra de performance observada + diagnóstico da fonte."""

    scores: list[dict]
    source: str  # "scoresaber_global" | "br_local" | "remap"
    global_scores_fetched: int = 0
    remap_scores_fetched: int = 0
    remap_candidates_found: int = 0
    remap_donors_used: int = 0


async def _ml_stars_by_difficulty(map_source: str | None) -> dict[str, float] | None:
    """Predição do ML (bsbr_analyzer) das stars por dificuldade do beatmap."""
    if not map_source:
        return None
    if map_source in _ML_CACHE:
        return _ML_CACHE[map_source]
    try:
        from bsbr_analyzer import analyze_map  # import tardio: pacote pesado

        analysis = await asyncio.to_thread(analyze_map, map_source)
        result = {
            d.difficulty: float(d.total_stars)
            for d in analysis.difficulties
            if d.total_stars and d.characteristic == "Standard"
        }
    except Exception:
        result = {}
    _ML_CACHE[map_source] = result
    return result or None


async def analyze_difficulty_with_ml(
    difficulty: Difficulty,
    map_: Map,
    scores: list[dict],
    *,
    min_player_pp: float | None = MIN_PLAYER_PP,
) -> ReweightResult:
    """Análise de reweight combinando o ML (stars do beatmap) com a performance.

    O ML re-prediz as stars do mapa pelas features do beatmap (``delta_ml``);
    a performance observada (acc mediana vs esperada) dá ``delta_perf``. O
    delta final é a média dos dois — "o ML acha que o mapa vale X★" aliado a
    "os scores estão rendendo acima/abaixo do esperado".

    ``min_player_pp=None`` desliga o filtro por PP (amostra global/remap).
    """
    base = analyze_difficulty(scores, float(difficulty.total_stars), min_player_pp=min_player_pp)
    if base.confidence == "none":
        return base

    ml = await _ml_stars_by_difficulty(map_.beatsaver_id or map_.hash)
    if not ml or difficulty.name not in ml:
        return base

    ml_stars = ml[difficulty.name]
    delta_ml = round(ml_stars - float(difficulty.total_stars), 2)
    delta_final = round(0.5 * delta_ml + 0.5 * base.delta_stars, 2)
    suggested = round(max(0.1, float(difficulty.total_stars) + delta_final), 2)
    reason = (
        f"ML {ml_stars:.2f}★ (Δ{delta_ml:+.2f}) + perf "
        f"{base.median_acc * 100:.1f}% vs {base.expected_acc * 100:.1f}% esperado "
        f"(n={base.sample_size}) → {delta_final:+.2f}★"
    )

    return ReweightResult(
        sample_size=base.sample_size,
        weighted_acc=base.weighted_acc,
        median_acc=base.median_acc,
        fc_rate=base.fc_rate,
        expected_acc=base.expected_acc,
        delta_stars=delta_final,
        suggested_stars=suggested,
        confidence=base.confidence,
        direction="increase" if delta_final > 0.05 else ("decrease" if delta_final < -0.05 else "keep"),
        reason=reason,
        can_auto_apply=(base.confidence == "high" and abs(delta_final) <= AUTO_APPLY_MAX),
    )


def _scale_stars(total_before: float, delta: float, difficulty: Difficulty) -> tuple[float, float, float, float]:
    """Aplica delta no total preservando a proporção dos sub-stars."""
    new_total = max(0.1, total_before + delta)
    factor = new_total / total_before if total_before > 0 else 1.0
    return (
        round(new_total, 2),
        round((difficulty.acc_stars or 0.0) * factor, 2),
        round((difficulty.tech_stars or 0.0) * factor, 2),
        round((difficulty.speed_stars or 0.0) * factor, 2),
    )


async def _difficulty_scores(session: AsyncSession, difficulty_id: int) -> list[dict]:
    # player_pp usa o PP interno do ranking BSBR (Player.pp_total): o payload
    # de score do ScoreSaber não traz o pp do player (leaderboardPlayerInfo só
    # tem id/name/country/avatar), então ss_player_pp fica sempre 0.
    rows = (
        await session.execute(
            select(Score.acc, Score.score, Score.full_combo, Player.pp_total)
            .join(Player, Score.player_id == Player.id)
            .where(Score.difficulty_id == difficulty_id)
            .order_by(Score.leaderboard_rank.nulls_last())
        )
    ).all()
    return [
        {
            "acc": acc or 0.0,
            "base_score": score or 0,
            "full_combo": bool(full_combo),
            "player_pp": pp_total or 0.0,
        }
        for acc, score, full_combo, pp_total in rows
    ]


async def _global_difficulty_scores(
    client: Any, difficulty: Difficulty
) -> tuple[list[dict], int, bool]:
    """Scores globais do leaderboard (janela top-100 por rank, sem PP filter).

    Devolve ``(scores válidos no formato analyze, qtd bruta, transport_ok)``.
    Retorna vazio SEM erro quando faltam ``ss_leaderboard_id``/``max_score``
    (fallback silencioso); falha de transporte marca ``transport_ok=False``.
    """
    from app.services.sync import parse_leaderboard_score

    if not difficulty.ss_leaderboard_id:
        return [], 0, True
    max_score = difficulty.max_score
    if max_score is None:
        info = await client.leaderboard_info_by_id(difficulty.ss_leaderboard_id)
        max_score = (info or {}).get("maxScore")
        if not max_score:
            return [], 0, True
    result = await client.leaderboard_scores_by_id_with_status(
        difficulty.ss_leaderboard_id, country=None, max_pages=10
    )
    if not result.transport_ok:
        return [], result.pages_fetched, False
    valid: list[dict] = []
    for raw in result.scores:
        item = parse_leaderboard_score(raw, max_score)
        if item is None:
            continue
        valid.append(
            {
                "acc": item["acc"] or 0.0,
                "base_score": int(raw.get("baseScore") or 0),
                "full_combo": item["full_combo"],
                "player_pp": 0.0,  # payload do SS não traz pp confiável
                "rank": item["leaderboard_rank"],
            }
        )
    valid.sort(key=lambda s: s["rank"] if s["rank"] is not None else 10**9)
    return valid[:GLOBAL_SAMPLE_LIMIT], result.pages_fetched, True


def _coherent_donor_scores(
    donor_scores: list[tuple[float, list[dict]]], *, sigma: float
) -> list[list[dict]]:
    """Mantém doadores com mediana de acc dentro de σ desvios da mediana da faixa.

    Duas passadas (mediana + desvio recomputados após o corte): descarta
    doadores mal calibrados — exatamente os que o reweight quer corrigir —
    para não contaminar o pool.
    """
    medians = [m for m, _ in donor_scores]
    if len(medians) < REMAP_MIN_DONORS:
        return []

    def _pass(ms: list[float]) -> list[int]:
        med = statistics.median(ms)
        sd = statistics.pstdev(ms)
        if sd == 0:
            sd = 1e-9
        return [i for i, m in enumerate(medians) if abs(m - med) <= sigma * sd]

    kept_idx = _pass(medians)
    if len(kept_idx) < REMAP_MIN_DONORS:
        return []
    kept_idx = _pass([medians[i] for i in kept_idx])
    return [donor_scores[i][1] for i in kept_idx]


async def _remap_band_sample(
    client: Any, difficulty: Difficulty, *, min_stars: float, max_stars: float
) -> tuple[list[dict], int, int, int]:
    """Pool de scores de doadores da faixa (coerência de acc aplicada).

    Devolve ``(pool no formato analyze, candidatos vistos, doadores aceitos,
    páginas buscadas)``. Falha de busca/filtro → pool vazio (remap indisponível).
    """
    from app.services.sync import parse_leaderboard_score

    try:
        candidates = await client.ranked_leaderboards_by_star_band(min_stars, max_stars)
    except Exception:
        return [], 0, 0, 0
    self_hash = difficulty.map.hash if difficulty.map else None
    candidates = [
        c
        for c in candidates
        if (c.get("map") or {}).get("hash") != self_hash
        and str(c.get("id") or "") != str(difficulty.ss_leaderboard_id or "")
    ]
    candidates_seen = len(candidates)
    donor_scores: list[tuple[float, list[dict]]] = []
    scores_fetched = 0
    for cand in candidates[:REMAP_MAX_DONORS]:
        try:
            result = await client.leaderboard_scores_by_id_with_status(
                cand["id"], country=None, max_pages=1
            )
        except Exception:
            continue
        scores_fetched += result.pages_fetched
        if not result.transport_ok:
            continue
        donor: list[dict] = []
        accs: list[float] = []
        for raw in result.scores:
            item = parse_leaderboard_score(raw, cand.get("maxScore"))
            if item is None or not item["acc"]:
                continue
            accs.append(item["acc"])
            donor.append(
                {
                    "acc": item["acc"],
                    "base_score": int(raw.get("baseScore") or 0),
                    "full_combo": item["full_combo"],
                    "player_pp": 0.0,
                    "rank": item["leaderboard_rank"],
                }
            )
        if len(donor) < MIN_SCORES:
            continue
        donor_scores.append((statistics.median(accs), donor))

    kept = _coherent_donor_scores(donor_scores, sigma=REMAP_SIGMA)
    if not kept:
        return [], candidates_seen, 0, scores_fetched
    pool: list[dict] = []
    for donor in kept:
        pool.extend(donor)
    pool.sort(key=lambda s: s["rank"] if s["rank"] is not None else 10**9)
    return pool[:REMAP_POOL_CAP], candidates_seen, len(kept), scores_fetched


async def _select_reweight_sample(
    session: AsyncSession,
    difficulty: Difficulty,
    *,
    use_global: bool,
    score_client: Any,
) -> ReweightSample:
    """Seleciona a fonte da amostra: global → BR local → remap.

    ``use_global=False`` (testes/sem cliente externo) → só BR local, mantendo
    o comportamento atual. Em modo rede, a amostra é suplementada com o remap
    por faixa até o alvo de consistência (``REMAP_TARGET=50``).
    """
    if not use_global or score_client is None:
        return ReweightSample(
            scores=await _difficulty_scores(session, difficulty.id), source="br_local"
        )

    band_min = float(difficulty.total_stars) - REMAP_BAND
    band_max = float(difficulty.total_stars) + REMAP_BAND
    global_scores, fetched, transport_ok = await _global_difficulty_scores(score_client, difficulty)

    if transport_ok and len(global_scores) >= MIN_SCORES:
        if len(global_scores) >= REMAP_TARGET:
            return ReweightSample(
                scores=global_scores,
                source="scoresaber_global",
                global_scores_fetched=fetched,
            )
        pool, cand, donors, remap_fetched = await _remap_band_sample(
            score_client, difficulty, min_stars=band_min, max_stars=band_max
        )
        if pool:
            return ReweightSample(
                scores=(global_scores + pool)[:REMAP_POOL_CAP],
                source="remap",
                global_scores_fetched=fetched,
                remap_scores_fetched=remap_fetched,
                remap_candidates_found=cand,
                remap_donors_used=donors,
            )
        return ReweightSample(scores=global_scores, source="scoresaber_global", global_scores_fetched=fetched)

    # Global insuficiente/falhou → BR local, com suplemento remap se fraco.
    local = await _difficulty_scores(session, difficulty.id)
    if len(local) >= REMAP_TARGET:
        return ReweightSample(scores=local, source="br_local", global_scores_fetched=fetched)
    pool, cand, donors, remap_fetched = await _remap_band_sample(
        score_client, difficulty, min_stars=band_min, max_stars=band_max
    )
    if pool:
        return ReweightSample(
            scores=(local + pool)[:REMAP_POOL_CAP],
            source="remap",
            global_scores_fetched=fetched,
            remap_scores_fetched=remap_fetched,
            remap_candidates_found=cand,
            remap_donors_used=donors,
        )
    return ReweightSample(scores=local, source="br_local", global_scores_fetched=fetched)


async def _upsert_suggestion(
    session: AsyncSession,
    difficulty: Difficulty,
    result: ReweightResult,
    *,
    sample_source: str = "br_local",
) -> ReweightSuggestion:
    existing = (
        await session.scalars(
            select(ReweightSuggestion)
            .where(
                ReweightSuggestion.difficulty_id == difficulty.id,
                ReweightSuggestion.status == SuggestionStatus.PENDING,
            )
            .limit(1)
        )
    ).first()
    if existing is None:
        existing = ReweightSuggestion(difficulty_id=difficulty.id)
        session.add(existing)
    existing.observed_acc = result.median_acc
    existing.expected_acc = result.expected_acc
    existing.sample_size = result.sample_size
    existing.delta_stars = result.delta_stars
    existing.confidence = result.confidence
    existing.suggested_stars = result.suggested_stars
    existing.reason = result.reason[:256]
    # Fonte sempre atualizada: uma sugestão pendente reaproveitada não pode
    # carregar a fonte obsoleta da coleta anterior.
    existing.sample_source = sample_source
    return existing


async def _apply_to_difficulty(
    session: AsyncSession,
    difficulty: Difficulty,
    result: ReweightResult,
    *,
    reviewed_by: str,
    batch_id: int | None = None,
) -> RatingHistory:
    before_total = float(difficulty.total_stars or 0.0)
    new_total, new_acc, new_tech, new_speed = _scale_stars(before_total, result.delta_stars, difficulty)
    history = RatingHistory(
        difficulty_id=difficulty.id,
        total_stars_before=before_total,
        total_stars_after=new_total,
        acc_stars_before=difficulty.acc_stars,
        acc_stars_after=new_acc,
        tech_stars_before=difficulty.tech_stars,
        tech_stars_after=new_tech,
        speed_stars_before=difficulty.speed_stars,
        speed_stars_after=new_speed,
        reason=result.reason[:256],
        batch_id=batch_id,
        applied_by=reviewed_by,
    )
    session.add(history)
    difficulty.total_stars = new_total
    difficulty.acc_stars = new_acc
    difficulty.tech_stars = new_tech
    difficulty.speed_stars = new_speed
    return history


async def collect_suggestions(
    session: AsyncSession,
    *,
    batch_id: int | None = None,
    auto_apply: bool = True,
    use_global: bool = False,
    score_client: Any | None = None,
) -> dict[str, int]:
    """Avalia todas as dificuldades rankeadas. Retorna contadores.

    ``use_global=True`` liga a coleta global (leaderboard do ScoreSaber) com
    suplemento/fallback remap por faixa de estrelas; sem cliente externo, o
    serviço cria um ``ScoreSaberClient`` próprio (fechado ao final). Scores
    globais/doadores NUNCA são gravados em ``scores``/``players``.
    """
    own_client = None
    if use_global and score_client is None:
        from app.integrations.scoresaber import ScoreSaberClient

        own_client = ScoreSaberClient()
        score_client = own_client

    difficulties = (
        (
            await session.execute(
                select(Difficulty)
                .join(Map, Difficulty.map_id == Map.id)
                .options(joinedload(Difficulty.map))
                .where(Map.status == MapStatus.RANKED)
                .where(Difficulty.total_stars.is_not(None))
                .where(Difficulty.is_ranked.is_(True))
            )
        )
        .scalars()
        .all()
    )

    stats = {
        "evaluated": 0,
        "pending": 0,
        "auto_applied": 0,
        "global_scores_fetched": 0,
        "global_difficulties_used": 0,
        "br_fallbacks": 0,
        "remap_difficulties_used": 0,
        "remap_scores_fetched": 0,
        "remap_candidates_found": 0,
        "remap_donors_used": 0,
    }
    try:
        for difficulty in difficulties:
            sample = await _select_reweight_sample(
                session, difficulty, use_global=use_global, score_client=score_client
            )
            min_player_pp = None if sample.source in ("scoresaber_global", "remap") else MIN_PLAYER_PP
            result = await analyze_difficulty_with_ml(
                difficulty, difficulty.map, sample.scores, min_player_pp=min_player_pp
            )
            if result.confidence == "none":
                continue
            stats["evaluated"] += 1
            if sample.source == "scoresaber_global":
                stats["global_difficulties_used"] += 1
                stats["global_scores_fetched"] += sample.global_scores_fetched
            elif sample.source == "remap":
                stats["remap_difficulties_used"] += 1
                stats["global_scores_fetched"] += sample.global_scores_fetched
                stats["remap_scores_fetched"] += sample.remap_scores_fetched
                stats["remap_candidates_found"] += sample.remap_candidates_found
                stats["remap_donors_used"] += sample.remap_donors_used
            elif use_global and score_client is not None:
                stats["br_fallbacks"] += 1
            suggestion = await _upsert_suggestion(
                session, difficulty, result, sample_source=sample.source
            )
            if auto_apply and result.can_auto_apply:
                await _apply_to_difficulty(
                    session, difficulty, result, reviewed_by=_SYSTEM_REVIEWER, batch_id=batch_id
                )
                suggestion.status = SuggestionStatus.APPLIED
                suggestion.reviewed_by = _SYSTEM_REVIEWER
                stats["auto_applied"] += 1
            else:
                stats["pending"] += 1
    finally:
        if own_client is not None:
            await own_client.close()
    await session.commit()
    return stats


async def apply_suggestion(
    session: AsyncSession, suggestion_id: int, *, reviewer: str, batch_id: int | None = None
) -> ReweightSuggestion:
    suggestion = await session.get(ReweightSuggestion, suggestion_id)
    if suggestion is None:
        raise ValueError(f"sugestão {suggestion_id} não encontrada")
    if suggestion.status != SuggestionStatus.PENDING:
        raise ValueError(f"sugestão {suggestion_id} já resolvida ({suggestion.status})")
    difficulty = await session.get(Difficulty, suggestion.difficulty_id)
    if difficulty is None or difficulty.total_stars is None:
        raise ValueError(f"dificuldade da sugestão {suggestion_id} inválida")

    result = ReweightResult(
        sample_size=suggestion.sample_size or 0,
        weighted_acc=None,
        median_acc=suggestion.observed_acc,
        fc_rate=None,
        expected_acc=suggestion.expected_acc,
        delta_stars=suggestion.delta_stars or 0.0,
        suggested_stars=suggestion.suggested_stars or difficulty.total_stars,
        confidence=suggestion.confidence or "low",
        direction="keep",
        reason=suggestion.reason or "aplicação manual",
        can_auto_apply=False,
    )
    await _apply_to_difficulty(session, difficulty, result, reviewed_by=reviewer, batch_id=batch_id)
    suggestion.status = SuggestionStatus.APPLIED
    suggestion.reviewed_by = reviewer
    await session.commit()
    return suggestion


async def reject_suggestion(
    session: AsyncSession, suggestion_id: int, *, reviewer: str
) -> ReweightSuggestion:
    suggestion = await session.get(ReweightSuggestion, suggestion_id)
    if suggestion is None:
        raise ValueError(f"sugestão {suggestion_id} não encontrada")
    if suggestion.status != SuggestionStatus.PENDING:
        raise ValueError(f"sugestão {suggestion_id} já resolvida ({suggestion.status})")
    suggestion.status = SuggestionStatus.REJECTED
    suggestion.reviewed_by = reviewer
    await session.commit()
    return suggestion


async def preview_suggestions(
    session: AsyncSession,
    *,
    use_global: bool = False,
    score_client: Any | None = None,
) -> dict:
    """Simulação do reweight em memória — não persiste nada.

    Roda a análise para todas as dificuldades rankeadas, aplica os deltas
    sugeridos e recalcula o ranking ponderado como ficaria. A curva de PP é
    linear em stars, então o novo PP de cada score = pp_atual × (novas/atuais).
    Scores globais/doadores entram apenas na estimativa do delta — o ranking
    simulado continua sobre os scores BR persistidos.
    """
    from app.services.pp_engine import weighted_pp

    own_client = None
    if use_global and score_client is None:
        from app.integrations.scoresaber import ScoreSaberClient

        own_client = ScoreSaberClient()
        score_client = own_client

    difficulties = (
        (
            await session.execute(
                select(Difficulty)
                .join(Map, Difficulty.map_id == Map.id)
                .options(joinedload(Difficulty.map))
                .where(Map.status == MapStatus.RANKED)
                .where(Difficulty.total_stars.is_not(None))
                .where(Difficulty.is_ranked.is_(True))
            )
        )
        .scalars()
        .all()
    )

    changes: dict[int, dict] = {}  # difficulty_id -> {old, new, result, map_name, diff_name}
    try:
        for difficulty in difficulties:
            sample = await _select_reweight_sample(
                session, difficulty, use_global=use_global, score_client=score_client
            )
            min_player_pp = None if sample.source in ("scoresaber_global", "remap") else MIN_PLAYER_PP
            result = await analyze_difficulty_with_ml(
                difficulty, difficulty.map, sample.scores, min_player_pp=min_player_pp
            )
            if result.confidence == "none":
                continue
            changes[difficulty.id] = {
                "old": float(difficulty.total_stars),
                "new": result.suggested_stars,
                "result": result,
                "map_name": difficulty.map.name,
                "diff_name": difficulty.name,
                "source": sample.source,
            }
    finally:
        if own_client is not None:
            await own_client.close()

    # Novo PP por jogador: agregação ponderada (0.965^n) sobre os scores
    # escalados pelo fator de cada dificuldade alterada.
    rows = (
        (
            await session.execute(
                select(Score, Player.id, Player.name, Difficulty.id)
                .join(Player, Score.player_id == Player.id)
                .join(Difficulty, Score.difficulty_id == Difficulty.id)
                .join(Map, Difficulty.map_id == Map.id)
                .where(Map.status == MapStatus.RANKED)
                .where(Difficulty.is_ranked.is_(True))
            )
        )
        .all()
    )
    players_before: dict[int, tuple[str, list[float]]] = {}
    players_after: dict[int, tuple[str, list[float]]] = {}
    for score, player_id, player_name, difficulty_id in rows:
        if score.pp is None:
            continue
        players_before.setdefault(player_id, (player_name, []))[1].append(float(score.pp))
        change = changes.get(difficulty_id)
        if change:
            factor = change["new"] / change["old"] if change["old"] else 1.0
            new_pp = float(score.pp) * factor
        else:
            new_pp = float(score.pp)
        players_after.setdefault(player_id, (player_name, []))[1].append(new_pp)

    def _ranking(by_player: dict[int, tuple[str, list[float]]]) -> list[tuple[float, str]]:
        ranked = []
        for player_id, (name, pps) in by_player.items():
            pps.sort(reverse=True)
            ranked.append((weighted_pp(pps), name))
        ranked.sort(reverse=True)
        return ranked

    before = _ranking(players_before)
    after = _ranking(players_after)
    before_rank = {name: i + 1 for i, (_, name) in enumerate(before)}
    after_rank = {name: i + 1 for i, (_, name) in enumerate(after)}
    before_pp = {name: pp for pp, name in before}
    after_pp = {name: pp for pp, name in after}

    top_affected = sorted(after, key=lambda t: t[0], reverse=True)[:20]
    ranking_payload = [
        {
            "name": name,
            "rank_before": before_rank.get(name),
            "rank_after": after_rank.get(name),
            "pp_before": round(before_pp.get(name, 0.0), 2),
            "pp_after": round(after_pp.get(name, 0.0), 2),
            "delta_pp": round(after_pp.get(name, 0.0) - before_pp.get(name, 0.0), 2),
        }
        for _, name in top_affected
        if before_pp.get(name, 0.0) != after_pp.get(name, 0.0) or before_rank.get(name) != after_rank.get(name)
    ]

    return {
        "difficulties": [
            {
                "difficulty_id": did,
                "map_name": ch["map_name"],
                "difficulty": ch["diff_name"],
                "current_stars": round(ch["old"], 2),
                "suggested_stars": round(ch["new"], 2),
                "delta_stars": round(ch["result"].delta_stars, 2),
                "confidence": ch["result"].confidence,
                "sample_size": ch["result"].sample_size,
                "observed_acc": ch["result"].median_acc,
                "expected_acc": ch["result"].expected_acc,
                "auto_appliable": ch["result"].can_auto_apply,
                "sample_source": ch["source"],
            }
            for did, ch in changes.items()
        ],
        "ranking": ranking_payload,
    }
