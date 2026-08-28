"""Features físicas: valores exatos em chart conhecido + sanidade finita."""

import math

import pytest

from bsbr_analyzer.features import compute_physical_features
from bsbr_analyzer.parser import Beatmap
from conftest import make_speed_map_v2, make_tech_map_v2, to_v2

PHYSICAL_KEYS = [
    "nps",
    "peak_nps",
    "weighted_peak_sum",
    "effective_nps",
    "peak_ratio",
    "complexity_score",
    "angle_strain",
    "tech_density",
    "stream_ratio",
    "alternation_ratio",
    "vision_block_ratio",
    "peak_strain",
    "strain_volatility",
    "bomb_count",
    "obstacle_count",
]


def _beatmap(chart):
    bm = Beatmap()
    bm.parse_json(chart)
    return bm


def test_simple_chart_exact_values():
    # 4 notas: 2 por mão, 1 beat entre elas, bpm 60 → duração 3s → nps = 4/3
    specs = [
        (0.0, 0, 0, 0, 1),
        (0.0, 3, 2, 1, 1),
        (1.0, 0, 0, 0, 1),
        (1.0, 3, 2, 1, 1),
        (2.0, 0, 0, 0, 1),
        (2.0, 3, 2, 1, 1),
    ]
    feats = compute_physical_features(_beatmap(to_v2(specs)), bpm=60.0)
    assert feats["note_count"] == 6
    assert feats["alternation_ratio"] == round(5 / 6, 2)
    assert feats["nps"] == 3.0
    assert feats["bomb_count"] == 0
    assert feats["obstacle_count"] == 0


def test_all_features_finite_nonnegative():
    for builder in (make_tech_map_v2, make_speed_map_v2):
        feats = compute_physical_features(_beatmap(builder()), bpm=120.0)
        for key in PHYSICAL_KEYS:
            value = feats[key]
            assert isinstance(value, (int, float)), key
            assert math.isfinite(value), key
            assert value >= 0.0, key


def test_peak_nps_window():
    # Burst de 4 notas dentro de 1 segundo isolado no tempo
    specs = [(i * 0.25, i % 4, 0, i % 2, 1) for i in range(4)]
    specs += [(10.0 + i, i % 4, 0, i % 2, 1) for i in range(2)]
    feats = compute_physical_features(_beatmap(to_v2(specs)), bpm=60.0)
    # Janela de 1s (=1 beat @60bpm): pico contém as 4 notas do burst
    assert feats["peak_nps"] == 4.0
    assert feats["peak_ratio"] > 1.0


def test_strain_decay_matches_reference_constant():
    from bsbr_analyzer.features import DECAY_RATE

    assert DECAY_RATE == 2.0


def test_bombs_and_obstacles_counted():
    chart = to_v2(
        notes=[(0.0, 0, 0, 0, 1), (0.5, 3, 2, 1, 1)],
        bombs=[(1.0, 1, 1, 3, 0), (2.0, 2, 1, 3, 0)],
        obstacles=[
            {"_time": 0, "_lineIndex": 0, "_type": 1, "_duration": 1, "_width": 1},
            {"_time": 2, "_lineIndex": 2, "_type": 0, "_duration": 1, "_width": 4},
        ],
    )
    feats = compute_physical_features(_beatmap(chart), bpm=60.0)
    assert feats["bomb_count"] == 2
    assert feats["obstacle_count"] == 2


def test_empty_notes_rejected():
    with pytest.raises(ValueError):
        compute_physical_features(_beatmap(to_v2([])), bpm=120.0)


def test_speed_map_high_nps():
    feats = compute_physical_features(_beatmap(make_speed_map_v2()), bpm=128.0)
    assert feats["nps"] > 12.0
    assert feats["stream_ratio"] > 0.9
