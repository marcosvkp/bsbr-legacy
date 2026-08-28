"""
Heurística de stars (fallback sem modelo ML) — porte de
references/BSStarAnalyzer/trainer.py::heuristic_stars.

Estimativa empírica das curvas do ScoreSaber; não é precisa, serve como
estimativa inicial quando não há modelo treinado.
"""

from __future__ import annotations

import math
from typing import Any, Dict


def heuristic_stars(features: Dict[str, Any]) -> float:
    nps = features.get("nps", 0)
    peak_nps = features.get("peak_nps", 0)
    peak_strain = features.get("peak_strain", 0)
    tech_ratio = features.get("pat_tech_ratio", features.get("tech_density", 0) / max(nps, 1))
    cross_ratio = features.get("pat_crossover_ratio", 0)
    double_ratio = features.get("pat_double_ratio", 0)
    stream_bpm = features.get("pat_stream_bpm_avg", 0)

    # Base: NPS contribui linearmente com coeficiente ~0.8
    base = nps * 0.75

    # Peak modifica para cima (mapas burst)
    peak_bonus = (peak_nps - nps) * 0.4

    # Strain normalizado contribui
    strain_bonus = math.log1p(peak_strain) * 0.3

    # Tech modifica: mapas tech são mais difíceis por nota
    tech_bonus = tech_ratio * 2.0

    # Crossovers e doubles adicionam dificuldade
    pattern_bonus = cross_ratio * 1.5 + double_ratio * 2.0

    # Streams rápidos (>180 BPM efetivo) somam
    if stream_bpm > 180:
        stream_bonus = (stream_bpm - 180) / 60.0
    else:
        stream_bonus = 0.0

    estimated = base + peak_bonus + strain_bonus + tech_bonus + pattern_bonus + stream_bonus
    return round(max(0.5, min(20.0, estimated)), 2)
