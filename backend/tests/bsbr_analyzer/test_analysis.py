"""Orquestrador analyze_map_folder + contrato dos dataclasses + CLI."""

import json

from bsbr_analyzer import DifficultyAnalysis, MapAnalysis, analyze_map_folder
from bsbr_analyzer.analysis import iter_standard_difficulties, parse_difficulty_file
from bsbr_analyzer.__main__ import main as cli_main
from conftest import (
    SPEED_INFO_V2,
    TECH_INFO_V2,
    make_speed_map_v2,
    make_tech_map_v2,
    make_tech_map_v3,
    to_v3,
)


def _write_map(tmp_path, info, chart):
    for diff_set in info["_difficultyBeatmapSets"]:
        for diff in diff_set["_difficultyBeatmaps"]:
            (tmp_path / diff["_beatmapFilename"]).write_text(json.dumps(chart))
    (tmp_path / "Info.dat").write_text(json.dumps(info))


V3_INFO = {
    "beatsPerMinute": 120.0,
    "songName": "Tech V3",
    "levelAuthorName": "MapperC",
    "difficultyBeatmapSets": [
        {
            "beatmapCharacteristicName": "Standard",
            "difficultyBeatmaps": [
                {
                    "difficulty": "ExpertPlus",
                    "beatmapFilename": "ExpertPlusV3.dat",
                    "noteJumpMovementSpeed": 19.0,
                }
            ],
        },
        {
            "beatmapCharacteristicName": "90Degree",
            "difficultyBeatmaps": [
                {"difficulty": "Expert", "beatmapFilename": "ignored.dat"}
            ],
        },
    ],
}


def _write_map(tmp_path, info, chart):
    sets = info.get("_difficultyBeatmapSets") or info.get("difficultyBeatmapSets")
    for diff_set in sets:
        diffs = diff_set.get("_difficultyBeatmaps", diff_set.get("difficultyBeatmaps"))
        for diff in diffs:
            fname = diff.get("_beatmapFilename") or diff.get("beatmapFilename")
            (tmp_path / fname).write_text(json.dumps(chart))
    (tmp_path / "Info.dat").write_text(json.dumps(info))
def test_iter_standard_difficulties_filters_characteristic():
    diffs = iter_standard_difficulties(V3_INFO)
    assert len(diffs) == 1
    assert diffs[0]["difficulty"] == "ExpertPlus"
    assert diffs[0]["njs"] == 19.0
    assert iter_standard_difficulties(TECH_INFO_V2)[0]["njs"] == 18.0


def test_analyze_folder_v2(tmp_path):
    _write_map(tmp_path, TECH_INFO_V2, make_tech_map_v2())
    analysis = analyze_map_folder(str(tmp_path))
    assert isinstance(analysis, MapAnalysis)
    assert analysis.name == "Tech Test"
    assert analysis.mapper == "MapperA"
    assert analysis.bpm == 120.0
    assert len(analysis.difficulties) == 1
    d = analysis.difficulties[0]
    assert isinstance(d, DifficultyAnalysis)
    assert d.characteristic == "Standard"
    assert d.difficulty == "ExpertPlus"
    assert d.njs == 18.0
    assert d.notes == 200
    assert d.nps > 0
    assert d.total_stars > 0
    assert abs(d.acc_stars + d.tech_stars + d.speed_stars - d.total_stars) < 1e-6
    assert abs(d.share_acc + d.share_tech + d.share_speed - 1.0) < 1e-6
    assert set(d.style_tags) <= {
        "stream", "tech", "jump", "crossover", "speed", "obstacle", "balanced",
    }
    # features contém físicas e pat_*
    assert "nps" in d.features and "pat_pattern_complexity" in d.features


def test_analyze_folder_v3(tmp_path):
    _write_map(tmp_path, V3_INFO, make_tech_map_v3())
    analysis = analyze_map_folder(str(tmp_path))
    assert analysis.name == "Tech V3"
    assert analysis.mapper == "MapperC"
    assert analysis.bpm == 120.0
    # features só contém numéricos; a versão do formato é verificada no parse
    beatmap, _ = parse_difficulty_file(str(tmp_path), "ExpertPlusV3.dat")
    assert beatmap.version.startswith("3")
    assert all(isinstance(v, float) for v in analysis.difficulties[0].features.values())


def test_cli_prints_table(tmp_path, capsys):
    from bsbr_analyzer import analysis
    _write_map(tmp_path, TECH_INFO_V2, make_tech_map_v2())
    # Redireciona o analisador para a pasta local via monkeypatch do cliente
    from bsbr_analyzer import beatsaver, analysis

    orig_fetch = analysis.fetch_map_metadata
    orig_download = analysis.download_map_zip
    orig_extract = analysis.extract_to_tempdir

    def fake_extract(zip_bytes):
        return str(tmp_path)

    analysis.fetch_map_metadata = lambda source: {}
    analysis.download_map_zip = lambda metadata: b""
    analysis.extract_to_tempdir = fake_extract

    try:
        rc = cli_main(["12345"])
    finally:
        analysis.fetch_map_metadata = orig_fetch
        analysis.download_map_zip = orig_download
        analysis.extract_to_tempdir = orig_extract

    out = capsys.readouterr().out
    assert rc == 0
    assert "Tech Test" in out
    assert "ExpertPlus" in out
    assert "*" in out


def test_corrupt_difficulty_file_skipped(tmp_path):
    _write_map(tmp_path, SPEED_INFO_V2, make_speed_map_v2())
    (tmp_path / "Expert.dat").write_text("{invalid json")
    analysis = analyze_map_folder(str(tmp_path))
    assert analysis.difficulties == []
