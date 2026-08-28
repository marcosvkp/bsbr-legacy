"""Padrões pat_* e classificador de estilo."""

import math

from bsbr_analyzer.parser import Beatmap
from bsbr_analyzer.patterns import KNOWN_STYLES, analyze_patterns, classify_map_style
from conftest import make_speed_map_v2, make_tech_map_v2, to_v3

REQUIRED_PAT_KEYS = {
    "pat_stream_count",
    "pat_avg_stream_length",
    "pat_max_stream_length",
    "pat_stream_note_ratio",
    "pat_stream_bpm_avg",
    "pat_jump_count",
    "pat_avg_jump_distance",
    "pat_max_jump_distance",
    "pat_jump_density",
    "pat_crossover_count",
    "pat_crossover_ratio",
    "pat_double_count",
    "pat_double_ratio",
    "pat_stack_count",
    "pat_parity_break_count",
    "pat_parity_break_ratio",
    "pat_reset_intensity",
    "pat_tech_ratio",
    "pat_avg_angle_offset",
    "pat_hand_dominance",
    "pat_left_ratio",
    "pat_right_ratio",
    "pat_obstacle_density",
    "pat_bomb_density",
    "pat_advanced_vision_block_count",
    "pat_vision_block_severity",
    "pat_arc_count",
    "pat_chain_count",
    "pat_arc_density",
    "pat_pattern_complexity",
    "pat_left_stream_ratio",
    "pat_right_stream_ratio",
    "pat_left_crossover_ratio",
    "pat_right_crossover_ratio",
}


def _analyze(chart, bpm=120.0, raw=None):
    bm = Beatmap()
    bm.parse_json(chart)
    duration = (max(n.b for n in bm.notes) / bpm) * 60.0
    return bm, analyze_patterns(
        notes=bm.notes,
        bombs=bm.bombs,
        obstacles=bm.obstacles,
        bpm=bpm,
        duration_seconds=duration,
        version=bm.version,
        raw_data=raw,
    )


def test_all_pat_keys_present_and_finite():
    for builder in (make_tech_map_v2, make_speed_map_v2):
        _, pats = _analyze(builder())
        missing = REQUIRED_PAT_KEYS - set(pats)
        assert not missing, f"ausentes: {missing}"
        assert all(math.isfinite(v) and v >= 0 for v in pats.values())


def test_linear_stream_map_detection():
    _, pats = _analyze(make_speed_map_v2(), bpm=128.0)
    assert pats["pat_tech_ratio"] == 0.0
    assert pats["pat_stream_note_ratio"] > 0.9
    assert pats["pat_crossover_ratio"] == 0.0


def test_tech_map_detection():
    _, pats = _analyze(make_tech_map_v2(), bpm=120.0)
    assert pats["pat_tech_ratio"] == 1.0
    assert pats["pat_parity_break_ratio"] > 0.5
    assert pats["pat_crossover_ratio"] > 0.1


def test_v3_arcs_chains():
    specs = [(i * 0.5, i % 4, i % 3, i % 2, 1) for i in range(20)]
    _, pats = _analyze(to_v3(specs, arcs=[{"b": 1}, {"b": 2}], chains=[{"b": 3}]), bpm=120.0, raw={})
    # raw_data sem sliders/chains → 0
    assert pats["pat_arc_count"] == 0
    # raw_data com sliders/chains e versão 3 → contados
    _, pats = _analyze(
        to_v3(specs, arcs=[{"b": 1}, {"b": 2}], chains=[{"b": 3}]),
        bpm=120.0,
        raw={"sliders": [{"b": 1}, {"b": 2}], "burstSliders": [{"b": 3}]},
    )
    assert pats["pat_arc_count"] == 2
    assert pats["pat_chain_count"] == 1
    assert pats["pat_arc_density"] > 0


def test_style_classifier_known_set():
    for builder in (make_tech_map_v2, make_speed_map_v2):
        _, pats = _analyze(builder())
        styles = classify_map_style(pats)
        assert styles, "deve retornar ao menos um estilo"
        assert set(styles) <= KNOWN_STYLES


def test_tech_map_classified_tech():
    _, pats = _analyze(make_tech_map_v2(), bpm=120.0)
    assert "tech" in classify_map_style(pats)


def test_speed_stream_map_classified_stream():
    _, pats = _analyze(make_speed_map_v2(), bpm=128.0)
    styles = classify_map_style(pats)
    assert "stream" in styles


def test_empty_notes_returns_empty():
    assert analyze_patterns([], [], [], bpm=120.0, duration_seconds=1.0) == {}
