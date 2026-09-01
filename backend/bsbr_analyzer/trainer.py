"""
Treinamento e predicao do modelo de stars ? porte de references/BSStarAnalyzer/trainer.py.

Mesmas features (BASE_FEATURES + PATTERN_FEATURES), mesmo modelo
(HistGradientBoostingRegressor) e mesmos hiperparametros da referencia.
O modelo treinado fica em `models/star_rating_model.pkl` (joblib) e e
carregado por `analysis.py` na predicao; sem modelo, `predict_with_fallback`
cai na heuristica (`stars_heuristic.heuristic_stars`).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import KFold, cross_val_score

from .stars_heuristic import heuristic_stars

PACKAGE_DIR = Path(__file__).resolve().parent
MODELS_DIR = PACKAGE_DIR / "models"
DATA_DIR = PACKAGE_DIR / "data"
MODEL_FILE = MODELS_DIR / "star_rating_model.pkl"
DATASET_FILE = DATA_DIR / "dataset.csv"

TARGET_COL = "stars"

# Features base ? sempre presentes (preenchidas com 0 se ausentes no row)
BASE_FEATURES = [
    # Velocidade
    "nps", "peak_nps", "weighted_peak_sum", "effective_nps", "peak_ratio",
    # Tecnica
    "complexity_score", "angle_strain", "tech_density",
    # Padrao legado
    "stream_ratio", "alternation_ratio", "vision_block_ratio",
    # Strain
    "peak_strain", "strain_volatility",
    # Meta
    "bpm", "duration_seconds",
]

# Features de padrao (pat_*) ? adicionadas automaticamente se presentes no dataset
PATTERN_FEATURES = [
    # Streams
    "pat_stream_count", "pat_avg_stream_length", "pat_max_stream_length",
    "pat_stream_note_ratio", "pat_stream_bpm_avg",
    # Jumps
    "pat_jump_count", "pat_avg_jump_distance", "pat_max_jump_distance", "pat_jump_density",
    # Crossovers
    "pat_crossover_count", "pat_crossover_ratio",
    # Doubles / Bursts
    "pat_double_count", "pat_double_ratio",
    # Stacks
    "pat_stack_count",
    # Parity / Reset
    "pat_parity_break_count", "pat_parity_break_ratio", "pat_reset_intensity",
    # Linear vs Tech
    "pat_tech_ratio", "pat_avg_angle_offset",
    # Hand dominance
    "pat_hand_dominance", "pat_left_ratio", "pat_right_ratio",
    # Obstacles / Bombs
    "pat_obstacle_density", "pat_bomb_density",
    # Vision blocks avancado
    "pat_advanced_vision_block_count", "pat_vision_block_severity",
    # Arcs / Chains (V3)
    "pat_arc_count", "pat_chain_count", "pat_arc_density",
    # Complexidade agregada
    "pat_pattern_complexity",
# Assimetria entre maos
    "pat_left_stream_ratio", "pat_right_stream_ratio",
    "pat_left_crossover_ratio", "pat_right_crossover_ratio",
]

# Features swing-based (porte do beatleader-analyzer, ML v1.5)
# Agrupam notas em swings, prevêem paridade via DP, calculam strain angular,
# repositioning/rotation, classificam multi-note e walls, e produzem ratings
# determinísticos (PassRating/TechRating/MultiRating/PeakSustainedEBPM).
SWING_FEATURES = [
    # Swing básico
    "pat_swing_count", "pat_swing_frequency_avg", "pat_swing_frequency_peak",
    "pat_hit_distance_avg", "pat_hit_distance_peak",
    # Movimento (tech)
    "pat_repositioning_distance_avg", "pat_repositioning_distance_peak",
    "pat_rotation_amount_avg", "pat_rotation_amount_peak",
    # Strain angular
    "pat_angle_strain_avg", "pat_angle_strain_peak",
    "pat_linear_swing_ratio",
    # Paridade (DP — mais preciso que pat_parity_break_count heurístico)
    "pat_parity_error_count_dp", "pat_parity_error_ratio_dp",
    "pat_bomb_avoidance_count",
    # Multi-note discriminado (pat_stack_count já existe em PATTERN_FEATURES;
    # swing_features sobrescreve com a versão BL mais precisa)
    "pat_tower_count",
    "pat_slider_count", "pat_curved_slider_count",
    "pat_window_count", "pat_slanted_window_count",
    # Walls classificadas (vs pat_obstacle_density genérico)
    "pat_dodge_wall_count", "pat_crouch_wall_count",
    # NJS
    "pat_njs_buff_avg", "pat_njs_max",
    # Ratings determinísticos do BL (features compostos)
    "pat_peak_sustained_ebpm", "pat_multi_rating_bl",
    "pat_low_note_nerf", "pat_one_saber_ratio",
    "pat_pass_rating_bl", "pat_tech_rating_bl",
]

ALL_FEATURES = BASE_FEATURES + PATTERN_FEATURES + SWING_FEATURES

_model_cache: Dict[str, Any] = {}


def _load_model(model_file: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Carrega o bundle do modelo com cache em modulo (chamado por diffs em batch)."""
    model_path = Path(model_file or MODEL_FILE)  # lookup dinamico (testes trocam MODEL_FILE)
    key = str(model_path)
    if key in _model_cache:
        return _model_cache[key]
    if not model_path.exists():
        return None
    bundle = joblib.load(model_path)
    _model_cache[key] = bundle
    return bundle


def train_model(dataset_path: Path = DATASET_FILE) -> Dict[str, Any]:
    """
    Treina o modelo de stars a partir do dataset.csv (gerado pelo builder).

    Validacao: 5-fold CV (MAE e R^2), MAE por range de stars e por estilo,
    permutation importance (top 20). Salva `{model, features}` em
    `models/star_rating_model.pkl` (joblib) e retorna metricas resumidas.
    """
    if not Path(dataset_path).exists():
        raise FileNotFoundError(f"dataset nao encontrado: {dataset_path} (rode 'download' antes)")

    print("Carregando dataset...")
    df = pd.read_csv(dataset_path)
    df = df.dropna(subset=[TARGET_COL])
    print(f"  {len(df)} amostras carregadas.")

    available_features = []
    for col in ALL_FEATURES:
        if col not in df.columns:
            df[col] = 0.0
        available_features.append(col)

    pat_active = sum(1 for f in available_features if f.startswith("pat_") and df[f].sum() != 0)
    print(f"  Features base: {len(BASE_FEATURES)} | Features de padrao ativas: {pat_active}")

    X = df[available_features]
    y = df[TARGET_COL]

    model = HistGradientBoostingRegressor(
        max_iter=1000,
        max_depth=8,
        learning_rate=0.04,
        min_samples_leaf=6,
        l2_regularization=0.1,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=20,
        random_state=42,
    )

    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    mae_scores = -cross_val_score(model, X, y, cv=kf, scoring="neg_mean_absolute_error")
    r2_scores = cross_val_score(model, X, y, cv=kf, scoring="r2")

    print(f"\n  Cross-Validation (5-fold):")
    print(f"    MAE : {mae_scores.mean():.4f}  +-{mae_scores.std():.4f}")
    print(f"    R^2  : {r2_scores.mean():.4f}")

    model.fit(X, y)
    y_pred = model.predict(X)

    evaluate_by_range(y, y_pred)
    evaluate_by_style(df, y_pred)

    print("\n  Feature Importance (permutation):")
    perm = permutation_importance(
        model, X, y, n_repeats=8, random_state=42,
        scoring="neg_mean_absolute_error",
    )
    importances = perm.importances_mean
    imp_min, imp_max = importances.min(), importances.max()
    imp_range = (imp_max - imp_min) or 1.0
    ranked = sorted(zip(available_features, importances), key=lambda x: x[1], reverse=True)
    for name, imp in ranked[:20]:
        bar = "#" * int(((imp - imp_min) / imp_range) * 30)
        print(f"    {name:<30} {imp:.4f}  {bar}")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": available_features}, MODEL_FILE)
    print(f"\nModelo salvo em {MODEL_FILE}")

    _model_cache.clear()

    return {
        "n_samples": int(len(df)),
        "mae_cv": float(mae_scores.mean()),
        "mae_cv_std": float(mae_scores.std()),
        "r2_cv": float(r2_scores.mean()),
        "model_file": str(MODEL_FILE),
    }


def evaluate_by_range(y_true: pd.Series, y_pred: np.ndarray) -> None:
    df = pd.DataFrame({"true": y_true, "pred": y_pred})
    ranges = [
        (0, 5, "< 5*"),
        (5, 8, "5-8*"),
        (8, 10, "8-10*"),
        (10, 99, "> 10*"),
    ]
    print("\n  MAE por Range de Stars:")
    for lo, hi, label in ranges:
        mask = (df["true"] >= lo) & (df["true"] < hi)
        if mask.sum() > 0:
            mae = mean_absolute_error(df[mask]["true"], df[mask]["pred"])
            print(f"    {label:>8} : MAE={mae:.4f}  (n={mask.sum()})")


def evaluate_by_style(df_full: pd.DataFrame, y_pred: np.ndarray) -> None:
    """MAE por estilo de mapa se a coluna 'map_styles' existir."""
    if "map_styles" not in df_full.columns:
        return
    import ast

    df = df_full.copy()
    df["pred"] = y_pred
    print("\n  MAE por Estilo de Mapa:")
    style_errors: Dict[str, list] = {}
    for _, row in df.iterrows():
        try:
            styles = ast.literal_eval(str(row["map_styles"]))
        except Exception:
            styles = ["unknown"]
        err = abs(row[TARGET_COL] - row["pred"])
        for s in styles:
            style_errors.setdefault(s, []).append(err)
    for style, errors in sorted(style_errors.items()):
        print(f"    {style:<12} : MAE={sum(errors) / len(errors):.4f}  (n={len(errors)})")


def predict_stars(features: Dict[str, Any]) -> Optional[float]:
    """Prediz stars com o modelo; None se nao existir modelo treinado."""
    bundle = _load_model()
    if bundle is None:
        return None
    model, feature_list = bundle["model"], bundle["features"]
    row = {col: features.get(col, 0.0) for col in feature_list}
    df = pd.DataFrame([row])[feature_list]
    pred = float(model.predict(df)[0])
    return max(0.1, pred)


def predict_with_fallback(features: Dict[str, Any]) -> Tuple[float, str]:
    """
    Prediz stars usando o modelo se disponivel, senao a heuristica.

    Returns:
        (stars, source) com source em {"model", "heuristic"}.
    """
    pred = predict_stars(features)
    if pred is not None:
        return round(pred, 2), "model"
    return heuristic_stars(features), "heuristic"


__all__ = [
    "BASE_FEATURES",
    "PATTERN_FEATURES",
    "ALL_FEATURES",
    "MODEL_FILE",
    "DATASET_FILE",
    "train_model",
    "predict_stars",
    "predict_with_fallback",
    "heuristic_stars",
]
