"""Testes do builder de dataset (sem rede — paths e CSV temporários)."""

import csv

import pandas as pd
import pytest

from bsbr_analyzer import dataset
from bsbr_analyzer.dataset import SS_DIFF_RANK_TO_NAME, group_by_hash, update_dataset


def _fake_rows(n):
    return [
        {
            "map_hash": f"h{i:040d}",
            "song_name": f"song{i}",
            "difficulty": "ExpertPlus",
            "stars": 7.0,
            "bpm": 120.0,
            "map_styles": "['tech']",
            "nps": 4.0,
            "duration_seconds": 120.0,
        }
        for i in range(n)
    ]


def test_group_by_hash_groups_entries():
    entries = [
        {"songHash": "aaaa", "id": 1, "difficulty": {"difficulty": 9}},
        {"songHash": "aaaa", "id": 2, "difficulty": {"difficulty": 7}},
        {"songHash": "bbbb", "id": 3, "difficulty": {"difficulty": 9}},
    ]
    groups = group_by_hash(entries)
    assert set(groups) == {"aaaa", "bbbb"}
    assert len(groups["aaaa"]) == 2


def test_ss_diff_rank_mapping():
    assert SS_DIFF_RANK_TO_NAME == {1: "Easy", 3: "Normal", 5: "Hard", 7: "Expert", 9: "ExpertPlus"}


def test_update_dataset_appends_and_dedupes(tmp_path, monkeypatch):
    dataset_file = tmp_path / "dataset.csv"
    monkeypatch.setattr(dataset, "DATASET_FILE", dataset_file)

    added, skipped = update_dataset(_fake_rows(3))
    assert added == 3 and skipped == 0
    assert dataset_file.exists()

    # linhas iguais são duplicatas → puladas
    added, skipped = update_dataset(_fake_rows(3))
    assert added == 0 and skipped == 3

    # linhas novas são adicionadas
    rows_new = _fake_rows(3)
    rows_new[0]["difficulty"] = "Expert"
    added, skipped = update_dataset(rows_new)
    assert added == 1 and skipped == 2

    with open(dataset_file, newline="", encoding="utf-8") as f:
        written = list(csv.DictReader(f))
    assert len(written) == 4
    assert written[0]["map_hash"] == f"h0:040d".replace("0:040d", "0" * 40)  # sanity
    assert written[0]["stars"] == "7.0"


def test_dataset_stats_counts(tmp_path, monkeypatch):
    dataset_file = tmp_path / "dataset.csv"
    monkeypatch.setattr(dataset, "DATASET_FILE", dataset_file)
    update_dataset(_fake_rows(2))

    stats = dataset.dataset_stats()
    assert stats["rows"] == 2
    assert stats["unique_maps"] == 2
    assert stats["by_difficulty"] == {"ExpertPlus": 2}


def test_processed_keys_matches_update(tmp_path, monkeypatch):
    dataset_file = tmp_path / "dataset.csv"
    monkeypatch.setattr(dataset, "DATASET_FILE", dataset_file)
    update_dataset(_fake_rows(2))

    keys = dataset._processed_keys()
    assert len(keys) == 2
    assert f"h0:040d".replace("0:040d", "0" * 40) + "_ExpertPlus" in keys


def test_csv_row_has_all_trainer_features(tmp_path, monkeypatch):
    """O CSV escrito tem todas as features do treino (DictWriter extrasaction=ignore)."""
    dataset_file = tmp_path / "dataset.csv"
    monkeypatch.setattr(dataset, "DATASET_FILE", dataset_file)
    update_dataset(_fake_rows(1))

    with open(dataset_file, newline="", encoding="utf-8") as f:
        fieldnames = f.readline().strip().split(",")
    from bsbr_analyzer.trainer import ALL_FEATURES

    missing = [f for f in ALL_FEATURES if f not in fieldnames]
    assert not missing, f"features ausentes no CSV: {missing}"


def test_fetch_ss_leaderboards_v2(monkeypatch):
    """Usa /api/v2/maps/hash/{hash} — cobre mapas ranked, qualified e unranked."""
    import httpx

    from bsbr_analyzer import dataset

    captured = {}

    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        return httpx.Response(
            200,
            json={
                "hash": "2C6425D059A6FAAA918BF02B86961246CBB0CD9E",
                "leaderboards": [
                    {
                        "id": 2243270,
                        "difficulty": 3,
                        "maxScore": 165715,
                        "realm": {
                            "leaderboardStatus": "UNRANKED",
                            "stars": 0,
                            "rankedAt": None,
                        },
                    },
                    {
                        "id": 2243271,
                        "difficulty": 7,
                        "maxScore": 400000,
                        "realm": {"leaderboardStatus": "RANKED", "stars": 6.2},
                    },
                ],
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(dataset.httpx, "get", fake_get)
    entries = dataset.fetch_ss_leaderboards("2c6425d059a6faaa918bf02b86961246cbb0cd9e")
    assert "/v2/maps/hash/2C6425D059A6FAAA918BF02B86961246CBB0CD9E" in captured["url"]
    assert len(entries) == 2
    assert entries[0]["id"] == 2243270
    assert entries[0]["ranked"] is False
    assert entries[0]["stars"] is None
    assert entries[1]["id"] == 2243271
    assert entries[1]["ranked"] is True
    assert entries[1]["stars"] == 6.2
    assert entries[1]["difficulty"] == {"difficulty": 7}
