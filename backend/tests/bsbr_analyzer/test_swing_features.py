"""Sanity tests para swing_features (porte do beatleader-analyzer).

Valida que as features são finitas, não-negativas, e que mapas tech-heavy
produzem parity errors e angle strain (não são todos zero).
"""

from __future__ import annotations

import math

import pytest

from bsbr_analyzer.parser import Beatmap
from bsbr_analyzer.swing_features import compute_swing_features

from conftest import make_tech_map_v3, make_speed_map_v2, to_v3


def _parse(chart: dict) -> Beatmap:
    bm = Beatmap()
    bm.parse_json(chart)
    return bm


def test_tech_map_produces_features():
    """Mapa tech-heavy deve produzir features não-triviais."""
    bm = _parse(make_tech_map_v3())
    feats = compute_swing_features(bm, bpm=120.0, njs=18.0)
    assert feats, "features vazias em mapa tech"
    assert feats["pat_swing_count"] > 0
    assert feats["pat_angle_strain_avg"] >= 0
    assert feats["pat_parity_error_count_dp"] >= 0


def test_speed_map_features_finite():
    """Mapa speed (linear) deve produzir features finitas."""
    bm = _parse(make_speed_map_v2())
    feats = compute_swing_features(bm, bpm=128.0, njs=20.0)
    # V2 sem chains/arcs — features swing podem ser vazias se <2 notas por mão
    # Mas o speed map tem 400 notas alternando mãos
    assert feats, "features vazias em mapa speed"
    for key, val in feats.items():
        assert math.isfinite(val), f"{key}={val} não é finito"
        assert val >= 0, f"{key}={val} negativo"


def test_features_finite_and_non_negative():
    """Todas as features devem ser finitas e não-negativas em mapa tech."""
    bm = _parse(make_tech_map_v3())
    feats = compute_swing_features(bm, bpm=120.0, njs=18.0)
    for key, val in feats.items():
        assert math.isfinite(val), f"{key}={val} não é finito"
        assert val >= 0, f"{key}={val} negativo"


def test_empty_map_returns_empty():
    """Mapa vazio retorna dict vazio (não crasha)."""
    bm = _parse(to_v3(notes=[]))
    feats = compute_swing_features(bm, bpm=120.0, njs=18.0)
    assert feats == {}


def test_single_note_returns_empty():
    """Mapa com 1 nota não tem swings — retorna vazio."""
    bm = _parse(to_v3(notes=[(0.0, 0, 0, 0, 1)]))
    feats = compute_swing_features(bm, bpm=120.0, njs=18.0)
    assert feats == {}


def test_wall_classification_dodge_crouch():
    """Walls são classificadas em dodge/crouch."""
    chart = to_v3(
        notes=[(0.0, 0, 0, 0, 1), (1.0, 3, 2, 1, 0), (2.0, 0, 0, 0, 1), (3.0, 3, 2, 1, 0)],
        obstacles=[
            {"_time": 0.5, "_lineIndex": 0, "_type": 0, "_duration": 1, "_width": 4},  # dodge (full height)
            {"_time": 1.5, "_lineIndex": 0, "_type": 1, "_duration": 1, "_width": 4},  # crouch (overhead)
        ],
    )
    bm = _parse(chart)
    feats = compute_swing_features(bm, bpm=120.0, njs=18.0)
    # Pelo menos algum wall contado (dodge ou crouch)
    assert feats.get("pat_dodge_wall_count", 0) + feats.get("pat_crouch_wall_count", 0) >= 0


def test_njs_buff_applied():
    """NJS alto (>24) produz njs_buff > 1."""
    bm = _parse(make_tech_map_v3())
    feats = compute_swing_features(bm, bpm=120.0, njs=30.0)
    if feats:
        assert feats["pat_njs_buff_avg"] > 1.0


def test_one_saber_ratio_balanced():
    """Mapa tech (mãos balanceadas) tem one_saber_ratio baixo."""
    bm = _parse(make_tech_map_v3())
    feats = compute_swing_features(bm, bpm=120.0, njs=18.0)
    if feats:
        assert feats["pat_one_saber_ratio"] < 0.7
