"""
player_performance.py
────────────────────────────────────────────────────────────────────────────
Analisa a performance real dos jogadores no ScoreSaber para:

1. Calcular o rating baseado em performance observada (não só análise estática)
2. Ajustar dinamicamente o rating quando solicitado
3. Fornecer insights sobre como os players estão performando comparado ao esperado

Lógica de ajuste:
  - Coleta scores do leaderboard (até N páginas)
  - Filtra por jogadores qualificados (PP alto o suficiente para ser relevante)
  - Calcula accuracy média / mediana ponderada
  - Compara com curva PP→stars do ScoreSaber
  - Estima o delta de rating ideal
"""

from __future__ import annotations

import math
import time
import requests
from typing import Optional, Dict, Any, List, Tuple

SCORESABER_API = "https://scoresaber.com/api"

# Accuracy que o ScoreSaber usa como referência para mapas "calibrados"
# 93.5% = full combo decente, ~5-6★; 80% = passa com custo
REFERENCE_ACC_FULL_COMBO = 0.935
REFERENCE_ACC_PASS       = 0.800

# Peso decrescente para ranks mais baixos no leaderboard
# rank 1 tem peso 1.0, rank N tem peso decay^(N-1)
RANK_DECAY = 0.97

# Mínimo de scores para considerar o ajuste confiável
MIN_SCORES_FOR_ADJUSTMENT = 10

# Mínimo de PP do jogador para filtrar casuals
MIN_PLAYER_PP = 1000.0

# Janela de páginas de score para coletar
MAX_PAGES = 5


class ScoreSaberPerformanceAnalyzer:
    """
    Analisa performance real dos players e gera sugestões de ajuste de rating.
    """

    def __init__(self, rate_limit_per_second: float = 5.0):
        self._min_delay = 1.0 / rate_limit_per_second
        self._last_call = 0.0

    def _get(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Rate-limited GET request."""
        now = time.time()
        wait = self._min_delay - (now - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception:
            return None

    # ─────────────────────────────────────────────────────
    # Coleta de dados
    # ─────────────────────────────────────────────────────

    def get_leaderboard_info(self, map_hash: str, difficulty_rank: int) -> Optional[Dict]:
        """Retorna info do leaderboard incluindo stars e maxScore."""
        url = f"{SCORESABER_API}/leaderboard/by-hash/{map_hash}/info"
        return self._get(url, {"difficulty": difficulty_rank})

    def get_scores(
        self,
        map_hash: str,
        difficulty_rank: int,
        max_pages: int = MAX_PAGES,
    ) -> List[Dict]:
        """Coleta scores de múltiplas páginas do leaderboard."""
        all_scores: List[Dict] = []
        url = f"{SCORESABER_API}/leaderboard/by-hash/{map_hash}/scores"

        for page in range(1, max_pages + 1):
            data = self._get(url, {"difficulty": difficulty_rank, "page": page})
            if not data:
                break
            scores = data.get("scores", [])
            if not scores:
                break
            all_scores.extend(scores)

        return all_scores

    def get_player_pp(self, player_id: str) -> Optional[float]:
        """Busca PP de um jogador específico (basic endpoint)."""
        url = f"{SCORESABER_API}/player/{player_id}/basic"
        data = self._get(url)
        if data:
            return data.get("pp")
        return None

    # ─────────────────────────────────────────────────────
    # Análise de performance
    # ─────────────────────────────────────────────────────

    def compute_weighted_accuracy(
        self,
        scores: List[Dict],
        max_score: int,
        filter_min_pp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Calcula accuracy ponderada pelo rank no leaderboard.
        Jogadores melhor rankeados têm mais peso.
        """
        if not scores or max_score <= 0:
            return {"weighted_acc": None, "median_acc": None, "sample_size": 0}

        valid_scores: List[Tuple[float, float]] = []  # (accuracy, weight)

        for i, score in enumerate(scores):
            base_score = score.get("baseScore", 0)
            if base_score <= 0:
                continue

            acc = base_score / max_score
            if acc > 1.05:  # ignora scores impossíveis (modifiers)
                continue

            # Filtro por PP do jogador (se fornecido)
            player_info = score.get("leaderboardPlayerInfo", {})
            player_pp = player_info.get("pp", 0) if player_info else 0
            if filter_min_pp and player_pp < filter_min_pp:
                continue

            weight = RANK_DECAY ** i
            valid_scores.append((acc, weight))

        if not valid_scores:
            return {"weighted_acc": None, "median_acc": None, "sample_size": 0}

        total_weight = sum(w for _, w in valid_scores)
        weighted_acc = sum(a * w for a, w in valid_scores) / total_weight

        accs_sorted = sorted(a for a, _ in valid_scores)
        n = len(accs_sorted)
        median_acc = accs_sorted[n // 2] if n % 2 == 1 else (accs_sorted[n // 2 - 1] + accs_sorted[n // 2]) / 2

        # Distribuição de accuracy
        bins = {"90-100%": 0, "80-90%": 0, "70-80%": 0, "<70%": 0}
        for a, _ in valid_scores:
            if a >= 0.90:
                bins["90-100%"] += 1
            elif a >= 0.80:
                bins["80-90%"] += 1
            elif a >= 0.70:
                bins["70-80%"] += 1
            else:
                bins["<70%"] += 1

        fc_rate = sum(1 for s in scores if s.get("fullCombo", False)) / len(scores)

        return {
            "weighted_acc": round(weighted_acc, 4),
            "median_acc": round(median_acc, 4),
            "sample_size": n,
            "acc_distribution": bins,
            "fc_rate": round(fc_rate, 4),
            "top1_acc": round(valid_scores[0][0], 4) if valid_scores else None,
        }

    # ─────────────────────────────────────────────────────
    # Estimativa de ajuste de rating
    # ─────────────────────────────────────────────────────

    def estimate_star_delta(
        self,
        current_stars: float,
        weighted_acc: float,
        median_acc: float,
        sample_size: int,
    ) -> Dict[str, Any]:
        """
        Estima o delta de rating baseado na accuracy observada.

        Lógica:
        - Mapa calibrado: top1 ≈ 99%, mediana ≈ 93-95%
        - Se mediana muito alta (>96%): mapa muito fácil → aumentar stars
        - Se mediana muito baixa (<88%): mapa muito difícil → diminuir stars
        - Confiança cresce com o tamanho da amostra
        """
        if sample_size < MIN_SCORES_FOR_ADJUSTMENT:
            return {
                "suggested_delta": 0.0,
                "confidence": "low",
                "reason": f"Amostra insuficiente ({sample_size} scores, mínimo {MIN_SCORES_FOR_ADJUSTMENT})",
            }

        # Mediana de referência por range de estrelas (empírico, baseado em dados do SS)
        # Stars mais altas → accuracy mediana esperada cai
        def expected_median_acc(stars: float) -> float:
            # Curva empírica aproximada:
            # 1★  → 97%, 5★ → 93%, 9★ → 88%, 13★+ → 83%
            return max(0.78, 0.98 - (stars * 0.015))

        expected = expected_median_acc(current_stars)
        diff = median_acc - expected  # positivo = mais fácil que esperado

        # Mapeamento: cada 1% de diferença na accuracy ≈ 0.25 stars
        # Calibrado empiricamente: diferença de 4% ≈ 1 star de erro
        SENSITIVITY = 0.25
        delta = -diff * 100 * SENSITIVITY  # invertido: mais fácil → delta positivo (aumentar)

        # Limita o delta a ±2 stars por segurança (mudanças maiores requerem confirmação manual)
        delta = max(-2.0, min(2.0, delta))

        # Confiança baseada no tamanho da amostra
        if sample_size >= 100:
            confidence = "high"
        elif sample_size >= 40:
            confidence = "medium"
        else:
            confidence = "low"

        direction = "aumentar" if delta > 0.05 else ("diminuir" if delta < -0.05 else "manter")
        reason = (
            f"Accuracy mediana observada: {median_acc*100:.1f}% | "
            f"Esperada para {current_stars:.1f}★: {expected*100:.1f}% | "
            f"Sugestão: {direction} em {abs(delta):.2f}★"
        )

        return {
            "suggested_delta": round(delta, 2),
            "suggested_stars": round(max(0.1, current_stars + delta), 2),
            "confidence": confidence,
            "reason": reason,
            "expected_median_acc": round(expected, 4),
            "observed_median_acc": round(median_acc, 4),
        }

    # ─────────────────────────────────────────────────────
    # API pública
    # ─────────────────────────────────────────────────────

    def analyze(
        self,
        map_hash: str,
        difficulty_rank: int,
        current_stars: Optional[float] = None,
        suggest_adjustment: bool = False,
    ) -> Dict[str, Any]:
        """
        Análise completa de performance para um mapa+dificuldade.

        Args:
            map_hash: Hash do mapa
            difficulty_rank: Rank da dificuldade (1=Easy, 3=Normal, 5=Hard, 7=Expert, 9=ExpertPlus)
            current_stars: Stars atuais (obtido da API se None)
            suggest_adjustment: Se True, calcula delta de rating sugerido
        """
        result: Dict[str, Any] = {
            "map_hash": map_hash,
            "difficulty_rank": difficulty_rank,
            "is_ranked": False,
            "stars": current_stars,
        }

        # 1. Info do leaderboard
        info = self.get_leaderboard_info(map_hash, difficulty_rank)
        if not info:
            result["error"] = "Mapa não encontrado no ScoreSaber ou não rankeado"
            return result

        result["is_ranked"] = info.get("ranked", False)
        result["leaderboard_id"] = info.get("id")
        result["song_name"] = info.get("songName", "")
        result["max_score"] = info.get("maxScore", 0)
        result["max_pp"] = info.get("maxPP", 0.0)
        result["plays"] = info.get("plays", 0)
        result["daily_plays"] = info.get("dailyPlays", 0)

        if current_stars is None:
            current_stars = info.get("stars", 0.0)
        result["stars"] = current_stars

        if not result["is_ranked"]:
            result["note"] = "Mapa não rankeado — análise de performance indisponível"
            return result

        # 2. Coleta de scores
        scores = self.get_scores(map_hash, difficulty_rank)
        result["scores_collected"] = len(scores)

        if not scores:
            result["error"] = "Nenhum score encontrado"
            return result

        # 3. Análise de accuracy
        max_score = result["max_score"]
        acc_analysis = self.compute_weighted_accuracy(
            scores, max_score, filter_min_pp=MIN_PLAYER_PP
        )
        result["accuracy_analysis"] = acc_analysis

        # 4. Ajuste de rating (se solicitado)
        if suggest_adjustment and current_stars and acc_analysis.get("median_acc"):
            adjustment = self.estimate_star_delta(
                current_stars=current_stars,
                weighted_acc=acc_analysis["weighted_acc"],
                median_acc=acc_analysis["median_acc"],
                sample_size=acc_analysis["sample_size"],
            )
            result["rating_adjustment"] = adjustment

        # 5. Análise de PP curva
        if result["max_pp"] and current_stars:
            pp_per_star = result["max_pp"] / current_stars if current_stars > 0 else 0
            result["pp_per_star"] = round(pp_per_star, 2)

        return result

    def batch_analyze(
        self,
        maps: List[Dict[str, Any]],  # list of {map_hash, difficulty_rank, stars}
        suggest_adjustment: bool = False,
    ) -> List[Dict[str, Any]]:
        """Analisa múltiplos mapas em sequência."""
        results = []
        for m in maps:
            r = self.analyze(
                map_hash=m["map_hash"],
                difficulty_rank=m["difficulty_rank"],
                current_stars=m.get("stars"),
                suggest_adjustment=suggest_adjustment,
            )
            results.append(r)
        return results


# ─────────────────────────────────────────────────────────
# Funções de conveniência
# ─────────────────────────────────────────────────────────

_analyzer_singleton: Optional[ScoreSaberPerformanceAnalyzer] = None


def get_analyzer() -> ScoreSaberPerformanceAnalyzer:
    global _analyzer_singleton
    if _analyzer_singleton is None:
        _analyzer_singleton = ScoreSaberPerformanceAnalyzer()
    return _analyzer_singleton


def quick_performance_analysis(
    map_hash: str,
    difficulty_rank: int,
    current_stars: Optional[float] = None,
) -> Dict[str, Any]:
    """Análise rápida sem ajuste de rating."""
    return get_analyzer().analyze(map_hash, difficulty_rank, current_stars, suggest_adjustment=False)


def performance_with_adjustment(
    map_hash: str,
    difficulty_rank: int,
    current_stars: Optional[float] = None,
) -> Dict[str, Any]:
    """Análise com sugestão de ajuste de rating."""
    return get_analyzer().analyze(map_hash, difficulty_rank, current_stars, suggest_adjustment=True)


# ─────────────────────────────────────────────────────────
# Formatação de resultado para CLI
# ─────────────────────────────────────────────────────────

def format_performance_report(result: Dict[str, Any]) -> str:
    """Formata o resultado de análise de performance para exibição no terminal."""
    lines = []
    sep = "─" * 60

    lines.append(sep)
    lines.append(f"  Performance: {result.get('song_name', result.get('map_hash', '?'))}")
    lines.append(sep)

    if result.get("error"):
        lines.append(f"  ⚠  {result['error']}")
        return "\n".join(lines)

    lines.append(f"  Rankeado    : {'✅ Sim' if result.get('is_ranked') else '❌ Não'}")
    lines.append(f"  Stars       : {result.get('stars', 'N/A')}★")
    lines.append(f"  MaxPP       : {result.get('max_pp', 'N/A')}")
    lines.append(f"  Plays       : {result.get('plays', 'N/A')} ({result.get('daily_plays', 0)}/dia)")
    lines.append(f"  Scores col. : {result.get('scores_collected', 0)}")
    lines.append("")

    acc = result.get("accuracy_analysis", {})
    if acc:
        lines.append("  Accuracy dos players:")
        if acc.get("top1_acc") is not None:
            lines.append(f"    Top 1        : {acc['top1_acc']*100:.2f}%")
        if acc.get("weighted_acc") is not None:
            lines.append(f"    Ponderada    : {acc['weighted_acc']*100:.2f}%")
        if acc.get("median_acc") is not None:
            lines.append(f"    Mediana      : {acc['median_acc']*100:.2f}%")
        lines.append(f"    FC Rate      : {acc.get('fc_rate', 0)*100:.1f}%")
        lines.append(f"    Amostra      : {acc.get('sample_size', 0)} jogadores")
        dist = acc.get("acc_distribution", {})
        if dist:
            lines.append("    Distribuição :")
            for label, count in dist.items():
                lines.append(f"      {label:>8} : {count}")
        lines.append("")

    adj = result.get("rating_adjustment")
    if adj:
        lines.append("  Sugestão de Ajuste de Rating:")
        lines.append(f"    Confiança    : {adj['confidence'].upper()}")
        lines.append(f"    Stars atuais : {result.get('stars', '?')}★")
        lines.append(f"    Stars sugerd : {adj.get('suggested_stars', '?')}★")
        delta = adj.get("suggested_delta", 0)
        sign = "+" if delta >= 0 else ""
        lines.append(f"    Delta        : {sign}{delta:.2f}★")
        lines.append(f"    Razão        : {adj.get('reason', '')}")

    lines.append(sep)
    return "\n".join(lines)
