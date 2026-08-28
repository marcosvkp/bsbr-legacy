"""
trainer.py
────────────────────────────────────────────────────────────────────────────
Treinamento e predição do modelo de stars.

Melhorias:
  - Features de padrão (pat_*) integradas automaticamente se disponíveis no dataset
  - Sistema de ajuste por performance de players (rating_adjustment)
  - Suporte a predição sem modelo (heurística fallback para mapas não rankeados)
  - Avaliação por range de stars e por estilo de mapa
"""

from __future__ import annotations

import os
import json
import math
from typing import Optional, Dict, Any, List

import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import KFold, cross_val_score
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.inspection import permutation_importance

MODEL_FILE   = "star_rating_model.pkl"
DATASET_FILE = "dataset.csv"

# ─────────────────────────────────────────────────────────
# Features base (sempre presentes, preenchidas com 0 se ausentes)
# ─────────────────────────────────────────────────────────

BASE_FEATURES = [
    # Velocidade
    "nps", "peak_nps", "weighted_peak_sum", "effective_nps", "peak_ratio",
    # Técnica
    "complexity_score", "angle_strain", "tech_density",
    # Padrão legado
    "stream_ratio", "alternation_ratio", "vision_block_ratio",
    # Strain
    "peak_strain", "strain_volatility",
    # Meta
    "bpm", "duration_seconds",
]

# Features de padrão — adicionadas automaticamente ao modelo se presentes no dataset
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
    # Vision blocks avançado
    "pat_advanced_vision_block_count", "pat_vision_block_severity",
    # Arcs / Chains (V3)
    "pat_arc_count", "pat_chain_count", "pat_arc_density",
    # Complexidade agregada
    "pat_pattern_complexity",
    # Assimetria entre mãos
    "pat_left_stream_ratio", "pat_right_stream_ratio",
    "pat_left_crossover_ratio", "pat_right_crossover_ratio",
]

TARGET_COL = "stars"


# ─────────────────────────────────────────────────────────
# Heurística de stars (fallback sem modelo treinado)
# ─────────────────────────────────────────────────────────

def heuristic_stars(features: Dict[str, Any]) -> float:
    """
    Estimativa heurística de stars para mapas não rankeados.
    Baseado em observações empíricas das curvas do ScoreSaber.

    Não é preciso — serve como estimativa inicial quando não há modelo.
    """
    nps         = features.get("nps", 0)
    peak_nps    = features.get("peak_nps", 0)
    peak_strain = features.get("peak_strain", 0)
    tech_ratio  = features.get("pat_tech_ratio", features.get("tech_density", 0) / max(nps, 1))
    cross_ratio = features.get("pat_crossover_ratio", 0)
    double_ratio = features.get("pat_double_ratio", 0)
    stream_bpm  = features.get("pat_stream_bpm_avg", 0)

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


# ─────────────────────────────────────────────────────────
# Avaliação por range e estilo
# ─────────────────────────────────────────────────────────

def evaluate_by_range(y_true: pd.Series, y_pred: np.ndarray) -> None:
    df = pd.DataFrame({"true": y_true, "pred": y_pred})
    ranges = [
        (0, 5,  "< 5★"),
        (5, 8,  "5–8★"),
        (8, 10, "8–10★"),
        (10, 99, "> 10★"),
    ]
    print("\n  MAE por Range de Stars:")
    for lo, hi, label in ranges:
        mask = (df["true"] >= lo) & (df["true"] < hi)
        if mask.sum() > 0:
            mae = mean_absolute_error(df[mask]["true"], df[mask]["pred"])
            n   = mask.sum()
            print(f"    {label:>8} : MAE={mae:.4f}  (n={n})")


def evaluate_by_style(df_full: pd.DataFrame, y_pred: np.ndarray) -> None:
    """Avalia MAE por estilo de mapa se a coluna 'map_styles' existir."""
    if "map_styles" not in df_full.columns:
        return

    df = df_full.copy()
    df["pred"] = y_pred

    # map_styles é uma string serializada como lista, ex: "['stream', 'tech']"
    import ast
    print("\n  MAE por Estilo de Mapa:")
    style_errors: Dict[str, List[float]] = {}

    for _, row in df.iterrows():
        try:
            styles = ast.literal_eval(str(row["map_styles"]))
        except Exception:
            styles = ["unknown"]
        err = abs(row["stars"] - row["pred"])
        for s in styles:
            style_errors.setdefault(s, []).append(err)

    for style, errors in sorted(style_errors.items()):
        mae = sum(errors) / len(errors)
        print(f"    {style:<12} : MAE={mae:.4f}  (n={len(errors)})")


# ─────────────────────────────────────────────────────────
# Treinamento
# ─────────────────────────────────────────────────────────

def train_model() -> None:
    if not os.path.exists(DATASET_FILE):
        print(f"Erro: {DATASET_FILE} não encontrado.")
        return

    print("Carregando dataset...")
    try:
        df = pd.read_csv(DATASET_FILE)
    except Exception as e:
        print(f"Erro ao ler dataset: {e}")
        return

    df = df.dropna(subset=[TARGET_COL])
    print(f"  {len(df)} amostras carregadas.")

    # Seleciona features disponíveis (base + padrão)
    all_candidates = BASE_FEATURES + PATTERN_FEATURES
    available_features = []
    for col in all_candidates:
        if col not in df.columns:
            df[col] = 0.0
        available_features.append(col)

    pat_count = sum(1 for f in available_features if f.startswith("pat_") and df[f].sum() != 0)
    print(f"  Features base: {len(BASE_FEATURES)} | Features de padrão ativas: {pat_count}")

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

    # 5-fold CV
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    mae_scores = -cross_val_score(model, X, y, cv=kf, scoring="neg_mean_absolute_error")
    r2_scores  =  cross_val_score(model, X, y, cv=kf, scoring="r2")

    print(f"\n  Cross-Validation (5-fold):")
    print(f"    MAE : {mae_scores.mean():.4f}  ±{mae_scores.std():.4f}")
    print(f"    R²  : {r2_scores.mean():.4f}")

    # Fit final
    model.fit(X, y)
    y_pred = model.predict(X)

    evaluate_by_range(y, y_pred)
    evaluate_by_style(df, y_pred)

    # Feature importance (permutation)
    print("\n  Feature Importance (permutation):")
    perm = permutation_importance(
        model, X, y, n_repeats=8, random_state=42,
        scoring="neg_mean_absolute_error",
    )
    importances = perm.importances_mean
    imp_min, imp_max = importances.min(), importances.max()
    imp_range = (imp_max - imp_min) or 1.0
    ranked = sorted(zip(available_features, importances), key=lambda x: x[1], reverse=True)
    for name, imp in ranked[:20]:  # top 20
        bar = "█" * int(((imp - imp_min) / imp_range) * 30)
        print(f"    {name:<30} {imp:.4f}  {bar}")

    # Salva modelo + lista de features
    joblib.dump({"model": model, "features": available_features}, MODEL_FILE)
    print(f"\nModelo salvo em {MODEL_FILE}")


# ─────────────────────────────────────────────────────────
# Predição
# ─────────────────────────────────────────────────────────

def predict_stars(features: Dict[str, Any]) -> Optional[float]:
    """
    Prediz stars para um conjunto de features.
    Retorna None se o modelo não existir (use heuristic_stars como fallback).
    """
    if not os.path.exists(MODEL_FILE):
        return None

    bundle = joblib.load(MODEL_FILE)
    model, feature_list = bundle["model"], bundle["features"]

    row = {col: features.get(col, 0.0) for col in feature_list}
    df  = pd.DataFrame([row])[feature_list]

    return float(model.predict(df)[0])


def predict_with_fallback(features: Dict[str, Any]) -> tuple[float, str]:
    """
    Prediz stars usando o modelo se disponível, caso contrário usa heurística.

    Returns:
        (stars, source) onde source é "model" ou "heuristic"
    """
    pred = predict_stars(features)
    if pred is not None:
        return round(pred, 2), "model"
    return heuristic_stars(features), "heuristic"


# ─────────────────────────────────────────────────────────
# Ajuste de rating por performance de players
# ─────────────────────────────────────────────────────────

RATING_ADJUSTMENTS_FILE = "rating_adjustments.json"


def load_adjustments() -> Dict[str, Any]:
    if os.path.exists(RATING_ADJUSTMENTS_FILE):
        try:
            with open(RATING_ADJUSTMENTS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_adjustment(
    map_hash: str,
    difficulty: str,
    base_stars: float,
    delta: float,
    reason: str,
    confidence: str,
) -> None:
    """Persiste um ajuste de rating para um mapa/dificuldade."""
    adjustments = load_adjustments()
    key = f"{map_hash}_{difficulty}"
    adjustments[key] = {
        "map_hash":    map_hash,
        "difficulty":  difficulty,
        "base_stars":  base_stars,
        "delta":       delta,
        "final_stars": round(max(0.1, base_stars + delta), 2),
        "reason":      reason,
        "confidence":  confidence,
    }
    with open(RATING_ADJUSTMENTS_FILE, "w") as f:
        json.dump(adjustments, f, indent=2)
    print(f"Ajuste salvo: {map_hash}/{difficulty} → {adjustments[key]['final_stars']}★")


def get_adjustment(map_hash: str, difficulty: str) -> Optional[float]:
    """Retorna o delta de ajuste salvo para um mapa/dificuldade, ou None."""
    adjustments = load_adjustments()
    key = f"{map_hash}_{difficulty}"
    entry = adjustments.get(key)
    if entry:
        return entry.get("delta", 0.0)
    return None


def apply_adjustment(
    predicted_stars: float,
    map_hash: str,
    difficulty: str,
) -> float:
    """Aplica ajuste salvo ao rating predito."""
    delta = get_adjustment(map_hash, difficulty)
    if delta is not None:
        return round(max(0.1, predicted_stars + delta), 2)
    return predicted_stars
