"""
bsbr_analyzer — motor de análise de mapas do BSBR v2.

Porte de references/BSStarAnalyzer (parser V2/V3, features físicas, padrões
pat_*, heurística de stars) + sub-stars (Plan.md §3.1) + cliente BeatSaver.
"""

from .analysis import (
    DifficultyAnalysis,
    MapAnalysis,
    analyze_map,
    analyze_map_folder,
)
from .stars_heuristic import heuristic_stars
from .substars import compute_shares, compute_substars

__all__ = [
    "analyze_map",
    "analyze_map_folder",
    "MapAnalysis",
    "DifficultyAnalysis",
    "compute_shares",
    "compute_substars",
]
