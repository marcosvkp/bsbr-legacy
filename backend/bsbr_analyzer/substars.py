"""
Sub-stars (Plan.md §3.1): decomposição de totalStars em acc + tech + speed.

    totalStars = accStars + techStars + speedStars   (invariante: soma fecha)

Cada eixo vira um score bruto computado das features do analyzer; os scores
são normalizados em shares (`share_acc + share_tech + share_speed = 1`) e
`subStars_x = totalStars × share_x`.

v1 é heurística sobre as features (sem ML novo); o v2 aprendido substituirá
estes pesos quando houver dataset de accRating/techRating público do
BeatLeader (Plan.md §3.1).

KNOBS DE CALIBRAÇÃO
-------------------
Todos os pesos abaixo são knobs deliberados de calibração. Ajustar um peso
NÃO altera o invariante da soma (shares sempre renormalizados), apenas a
distribuição relativa entre eixos.

- AXIS_WEIGHTS: peso global de cada eixo antes da normalização. O tech recebe
  1.5 porque suas features discriminantes (ratios de padrão) têm magnitude
  menor que as de NPS do eixo speed — sem o boost, todo mapa rápido pareceria
  "speed".
- TECH/SPEED/ACC_FEATURE_WEIGHTS: importância de cada feature no seu eixo,
  seguindo o Plan.md §3.1:
    * tech ← pat_tech_ratio (1 − linear), parity breaks, crossovers,
      pat_pattern_complexity;
    * speed ← peak_nps, nps, effective_nps, stream_ratio, bursts/doubles;
    * acc ← vision_block_ratio, stacks, bombas/s, paredes/s, peak_strain.
- Compressão de escala (_LOG_SCALED): features de magnitude larga (NPS,
  densidades, strain acumulado) passam por log1p para que nenhum eixo domine
  só por escala numérica. Ratios em [0,1] entram lineares.
- tech_density (legado) NÃO entra direto no eixo tech: na referência ele é
  angle_strain × nps, ou seja, cresce com velocidade pura — um stream linear
  simples maximizaria o eixo tech. O conteúdo "técnico por nota" já está
  coberto por pat_tech_ratio/parity/crossovers.
"""

from __future__ import annotations

import math
from typing import Any, Dict

# ── Knobs de calibração ──────────────────────────────────

AXIS_WEIGHTS: Dict[str, float] = {
    "acc": 1.0,
    "tech": 1.5,
    "speed": 1.0,
}

TECH_FEATURE_WEIGHTS: Dict[str, float] = {
    "pat_tech_ratio": 0.35,
    "pat_parity_break_ratio": 0.25,
    "pat_crossover_ratio": 0.15,
    "pat_pattern_complexity": 0.25,
}

# Bursts/doubles contam como velocidade (janelas curtíssimas por mão).
SPEED_FEATURE_WEIGHTS: Dict[str, float] = {
    "peak_nps": 0.35,
    "nps": 0.20,
    "effective_nps": 0.15,
    "stream_ratio": 0.15,
    "pat_stream_note_ratio": 0.05,
    "pat_double_ratio": 0.10,
}

ACC_FEATURE_WEIGHTS: Dict[str, float] = {
    "vision_block_ratio": 0.30,
    "pat_stack_count_per_note": 0.15,
    "bomb_density_per_sec": 0.20,
    "obstacle_density_per_sec": 0.15,
    "peak_strain": 0.20,
}

# Features lineares grandes → compressão logarítmica.
_LOG_SCALED = {
    "peak_nps",
    "nps",
    "effective_nps",
    "pat_pattern_complexity",
    "peak_strain",
}


def _feature_score(features: Dict[str, Any], weights: Dict[str, float]) -> float:
    total = 0.0
    for name, w in weights.items():
        value = max(float(features.get(name, 0.0)), 0.0)
        if name in _LOG_SCALED:
            value = math.log1p(value)
        total += w * value
    return total


def compute_axis_scores(features: Dict[str, Any]) -> Dict[str, float]:
    """Scores brutos por eixo a partir das features (sem normalizar)."""
    f = dict(features)
    # Derivados normalizados para escala comparável
    note_count = max(float(f.get("note_count", 0.0)), 1.0)
    duration = max(float(f.get("duration_seconds", 0.0)), 1e-6)
    f["pat_stack_count_per_note"] = float(f.get("pat_stack_count", 0.0)) / note_count
    f["bomb_density_per_sec"] = float(f.get("bomb_count", 0.0)) / duration
    f["obstacle_density_per_sec"] = float(f.get("obstacle_count", 0.0)) / duration

    return {
        "acc": _feature_score(f, ACC_FEATURE_WEIGHTS),
        "tech": _feature_score(f, TECH_FEATURE_WEIGHTS),
        "speed": _feature_score(f, SPEED_FEATURE_WEIGHTS),
    }


def compute_shares(features: Dict[str, Any]) -> Dict[str, float]:
    """
    Normaliza os scores dos eixos em shares somando 1.0.
    Mapa degenerado (todos os scores zero) → distribuição uniforme.
    """
    scores = compute_axis_scores(features)
    raw = {axis: scores[axis] * AXIS_WEIGHTS[axis] for axis in scores}
    total = sum(raw.values())
    if total <= 0.0:
        return {axis: 1.0 / len(raw) for axis in raw}
    return {axis: raw[axis] / total for axis in raw}


def compute_substars(total_stars: float, features: Dict[str, Any]) -> Dict[str, float]:
    """
    Decomposição final: retorna share_acc/share_tech/share_speed (somam 1.0)
    e acc_stars/tech_stars/speed_stars (somam total_stars).
    """
    shares = compute_shares(features)
    return {
        "share_acc": shares["acc"],
        "share_tech": shares["tech"],
        "share_speed": shares["speed"],
        "acc_stars": total_stars * shares["acc"],
        "tech_stars": total_stars * shares["tech"],
        "speed_stars": total_stars * shares["speed"],
    }
