"""Heurística de stars e sub-stars (invariantes de soma e dominância)."""

import math

from bsbr_analyzer.analysis import analyze_difficulty, read_info_dat
from bsbr_analyzer.stars_heuristic import heuristic_stars
from bsbr_analyzer.substars import compute_axis_scores, compute_shares, compute_substars
from conftest import SPEED_INFO_V2, TECH_INFO_V2, make_speed_map_v2, make_tech_map_v2


def _features(tmp_path, info, chart_builder):
    (tmp_path / info["_difficultyBeatmapSets"][0]["_difficultyBeatmaps"][0]["_beatmapFilename"]).write_text(
        __import__("json").dumps(chart_builder())
    )
    (tmp_path / "Info.dat").write_text(__import__("json").dumps(info))
    return _difficulty_features(str(tmp_path), info)


def _difficulty_features(map_dir, info):
    diff = info["_difficultyBeatmapSets"][0]["_difficultyBeatmaps"][0]
    result = analyze_difficulty(
        map_dir,
        diff["_beatmapFilename"],
        bpm=float(info["_beatsPerMinute"]),
        difficulty_name=diff["_difficulty"],
        njs=diff["_noteJumpMovementSpeed"],
    )
    assert result is not None
    return result


def test_heuristic_clamped():
    assert heuristic_stars({"nps": 1000}) <= 20.0
    assert heuristic_stars({}) >= 0.5
    assert math.isfinite(heuristic_stars({"nps": 5, "peak_nps": 9}))


def test_shares_sum_to_one():
    for builder in (make_tech_map_v2, make_speed_map_v2):
        import json
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(tmp, exist_ok=True)
            fname = "ExpertPlus.dat"
            with open(os.path.join(tmp, fname), "w") as f:
                json.dump(builder(), f)
            with open(os.path.join(tmp, "Info.dat"), "w") as f:
                json.dump(TECH_INFO_V2, f)
            d = _difficulty_features(tmp, TECH_INFO_V2)
            total = d.share_acc + d.share_tech + d.share_speed
            assert abs(total - 1.0) < 1e-6


def test_substars_sum_to_total():
    features = {
        "note_count": 200,
        "duration_seconds": 50.0,
        "nps": 4.0,
        "peak_nps": 4.0,
        "effective_nps": 2.0,
        "stream_ratio": 0.0,
        "pat_stream_note_ratio": 0.0,
        "pat_double_ratio": 0.0,
        "pat_tech_ratio": 1.0,
        "pat_parity_break_ratio": 0.8,
        "pat_crossover_ratio": 0.5,
        "pat_pattern_complexity": 6.0,
        "vision_block_ratio": 0.1,
        "pat_stack_count": 0,
        "bomb_count": 0,
        "obstacle_count": 0,
        "peak_strain": 5.0,
    }
    sub = compute_substars(7.0, features)
    assert abs(sub["acc_stars"] + sub["tech_stars"] + sub["speed_stars"] - 7.0) < 1e-6
    assert abs(sub["share_acc"] + sub["share_tech"] + sub["share_speed"] - 1.0) < 1e-6


def test_degenerate_map_uniform_shares():
    shares = compute_shares({})
    assert all(abs(s - 1 / 3) < 1e-9 for s in shares.values())


def test_tech_heavy_map_share_tech_dominates(tmp_path):
    d = _features(tmp_path, TECH_INFO_V2, make_tech_map_v2)
    assert d.share_tech > d.share_speed
    assert d.share_tech > d.share_acc
    assert abs(d.acc_stars + d.tech_stars + d.speed_stars - d.total_stars) < 1e-6


def test_linear_fast_map_share_speed_dominates(tmp_path):
    d = _features(tmp_path, SPEED_INFO_V2, make_speed_map_v2)
    assert d.share_speed > d.share_tech
    assert d.share_speed > d.share_acc
    assert abs(d.acc_stars + d.tech_stars + d.speed_stars - d.total_stars) < 1e-6


def test_axis_scores_nonnegative_finite():
    scores = compute_axis_scores({"nps": 10, "peak_strain": 3})
    assert set(scores) == {"acc", "tech", "speed"}
    assert all(math.isfinite(v) and v >= 0 for v in scores.values())
