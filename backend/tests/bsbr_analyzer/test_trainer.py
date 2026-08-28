"""Testes do trainer: treino com dataset sintético + fallback da heurística."""

import random

import pandas as pd
import pytest

from bsbr_analyzer import trainer
from bsbr_analyzer.stars_heuristic import heuristic_stars


def _synthetic_dataset(tmp_path, n=120):
    """Dataset sintético: stars = 2 + 1.2*nps + 0.8*tech_density + ruído."""
    random.seed(42)
    rows = []
    for i in range(n):
        nps = round(random.uniform(1.5, 10.0), 2)
        tech_density = round(random.uniform(0.1, 3.0), 2)
        duration_seconds = round(random.uniform(60, 240), 2)
        stars = round(2 + 1.2 * nps + 0.8 * tech_density + random.uniform(-0.4, 0.4), 2)
        rows.append({
            "map_hash": f"h{i:040d}",
            "song_name": f"song{i}",
            "difficulty": "ExpertPlus",
            "stars": stars,
            "bpm": 120.0,
            "nps": nps,
            "peak_nps": nps * 1.5,
            "weighted_peak_sum": nps * 1.2,
            "effective_nps": nps * 0.9,
            "peak_ratio": 1.4,
            "complexity_score": 3.0,
            "angle_strain": tech_density,
            "tech_density": tech_density,
            "stream_ratio": 0.3,
            "alternation_ratio": 0.5,
            "vision_block_ratio": 0.1,
            "peak_strain": 5.0,
            "strain_volatility": 1.0,
            "bpm_meta": 120.0,
            "duration_seconds": duration_seconds,
            "pat_stream_count": random.randint(0, 30),
            "map_styles": "['tech']",
        })
    return rows


def _train_with_tmp_paths(tmp_path, monkeypatch, rows):
    dataset = tmp_path / "dataset.csv"
    pd.DataFrame(rows).to_csv(dataset, index=False)
    model_file = tmp_path / "star_rating_model.pkl"
    monkeypatch.setattr(trainer, "DATASET_FILE", dataset)
    monkeypatch.setattr(trainer, "MODEL_FILE", model_file)
    monkeypatch.setattr(trainer, "MODELS_DIR", tmp_path)
    trainer._model_cache.clear()
    return dataset, model_file


def test_train_model_saves_and_predicts(tmp_path, monkeypatch):
    rows = _synthetic_dataset(tmp_path)
    dataset, model_file = _train_with_tmp_paths(tmp_path, monkeypatch, rows)

    metrics = trainer.train_model(dataset)
    assert model_file.exists()
    assert metrics["n_samples"] == len(rows)
    assert metrics["mae_cv"] < 0.6, "MAE CV muito alto para dados sintéticos"
    assert metrics["r2_cv"] > 0.9

    # predição de um row do próprio dataset (mesmo domínio do treino)
    features = {k: v for k, v in rows[0].items() if k in trainer.ALL_FEATURES}
    pred = trainer.predict_stars(features)
    assert pred is not None
    assert abs(pred - rows[0]["stars"]) < 1.0


def test_predict_with_fallback_without_model(tmp_path, monkeypatch):
    """Sem modelo treinado, cai na heurística com source='heuristic'."""
    trainer._model_cache.clear()
    monkeypatch.setattr(trainer, "MODEL_FILE", tmp_path / "nao_existe.pkl")
    features = {"nps": 5.0, "bpm": 120.0, "duration_seconds": 120.0}
    stars, source = trainer.predict_with_fallback(features)
    assert source == "heuristic"
    assert stars == pytest.approx(heuristic_stars(features), abs=0.01)


def test_predict_with_fallback_with_model(tmp_path, monkeypatch):
    rows = _synthetic_dataset(tmp_path)
    dataset, model_file = _train_with_tmp_paths(tmp_path, monkeypatch, rows)
    trainer.train_model(dataset)

    features = {k: v for k, v in rows[0].items() if k in trainer.ALL_FEATURES}
    stars, source = trainer.predict_with_fallback(features)
    assert source == "model"
    assert stars > 1.0


def test_missing_pattern_features_fill_zero(tmp_path, monkeypatch):
    """Features pat_* ausentes no row viram 0 (não quebram o predict)."""
    rows = _synthetic_dataset(tmp_path)
    dataset, model_file = _train_with_tmp_paths(tmp_path, monkeypatch, rows)
    trainer.train_model(dataset)

    features = {k: v for k, v in rows[0].items() if k in trainer.ALL_FEATURES}
    features.pop("pat_stream_count")  # simulando features pat ausentes
    stars, source = trainer.predict_with_fallback(features)
    assert source == "model"
    assert stars > 1.0
