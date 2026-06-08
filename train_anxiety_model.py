#!/usr/bin/env python3
"""
NeuroDrive — Anxiety Model Trainer
===================================
Loads all session CSV files, extracts EEG features, computes EMA-smoothed
anxiety labels, and trains a RandomForestRegressor for stable prediction.

Usage: python tools/train_anxiety_model.py
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MODEL_DIR = ROOT / "artifacts" / "models"
MODEL_PATH = MODEL_DIR / "anxiety_rf.pkl"
SCALER_PATH = MODEL_DIR / "scaler.pkl"
CSV_PREFIX = "neurodrive_session"

EMA_ALPHA = 0.05  # smoothing factor for anxiety labels

FEATURE_COLS = [
    "delta", "theta", "alpha", "beta", "gamma",
    "theta_beta_ratio", "alpha_sum_ratio", "high_freq_ratio",
]
TARGET_COL = "anxiety"


def load_sessions() -> List[Dict[str, float]]:
    """Load all session CSVs and return list of row dicts."""
    if not DATA_DIR.exists():
        print(f"Data directory not found: {DATA_DIR}")
        return []

    all_rows: List[Dict[str, float]] = []
    csv_files = sorted(DATA_DIR.glob(f"{CSV_PREFIX}_*.csv"))
    print(f"Found {len(csv_files)} session file(s)")

    for csv_file in csv_files:
        row_count = 0
        with csv_file.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    parsed = {}
                    for col in FEATURE_COLS + [TARGET_COL]:
                        val = float(row.get(col, 0) or 0)
                        if math.isfinite(val):
                            parsed[col] = val
                        else:
                            parsed[col] = 0.0
                    all_rows.append(parsed)
                    row_count += 1
                except (ValueError, KeyError):
                    continue
        print(f"  {csv_file.name}: {row_count} rows")

    return all_rows


def compute_ema_labels(rows: List[Dict[str, float]]) -> List[Dict[str, float]]:
    """Apply EMA smoothing to the anxiety column as training labels."""
    if not rows:
        return rows

    ema_value = rows[0].get(TARGET_COL, 0.0)
    for row in rows:
        raw = row.get(TARGET_COL, 0.0)
        ema_value = EMA_ALPHA * raw + (1 - EMA_ALPHA) * ema_value
        row[TARGET_COL] = ema_value

    return rows


def extract_features_labels(
    rows: List[Dict[str, float]],
) -> Tuple[np.ndarray, np.ndarray]:
    """Extract feature matrix X and target vector y."""
    X = np.array([
        [row.get(col, 0.0) for col in FEATURE_COLS]
        for row in rows
    ], dtype=np.float64)

    y = np.array([
        row.get(TARGET_COL, 0.0) for row in rows
    ], dtype=np.float64)

    return X, y


def train_model(
    X: np.ndarray, y: np.ndarray
) -> Tuple[RandomForestRegressor, StandardScaler, Dict[str, float]]:
    """Train the model and return model, scaler, and metrics."""
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = RandomForestRegressor(
        n_estimators=100,
        max_depth=10,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train_scaled, y_train)

    y_pred = model.predict(X_test_scaled)

    # Metrics
    mse = float(mean_squared_error(y_test, y_pred))
    rmse = float(math.sqrt(mse))
    mae = float(mean_absolute_error(y_test, y_pred))
    r2 = float(r2_score(y_test, y_pred))

    cv_scores = cross_val_score(model, X_train_scaled, y_train, cv=5, scoring="r2")
    cv_r2_mean = float(np.mean(cv_scores))
    cv_r2_std = float(np.std(cv_scores))

    # Feature importance
    importance = dict(zip(FEATURE_COLS, model.feature_importances_))

    metrics = {
        "mse": mse,
        "rmse": rmse,
        "mae": mae,
        "r2_score": r2,
        "cv_r2_mean": cv_r2_mean,
        "cv_r2_std": cv_r2_std,
        "n_samples": len(X),
        "n_features": len(FEATURE_COLS),
        "feature_importance": importance,
    }

    return model, scaler, metrics


def print_metrics(metrics: Dict[str, Any]) -> None:
    """Pretty-print training metrics."""
    print("\n" + "=" * 50)
    print("MODEL TRAINING RESULTS")
    print("=" * 50)
    print(f"Samples:       {metrics['n_samples']}")
    print(f"Features:      {metrics['n_features']}")
    print(f"MSE:           {metrics['mse']:.4f}")
    print(f"RMSE:          {metrics['rmse']:.4f}")
    print(f"MAE:           {metrics['mae']:.4f}")
    print(f"R² Score:      {metrics['r2_score']:.4f}")
    print(f"CV R² (mean):  {metrics['cv_r2_mean']:.4f} (±{metrics['cv_r2_std']:.4f})")
    print("\nFeature Importance:")
    for feat, imp in sorted(
        metrics["feature_importance"].items(), key=lambda x: x[1], reverse=True
    ):
        bar = "█" * int(imp * 40)
        print(f"  {feat:20s}: {imp:.4f} {bar}")


def main() -> int:
    print("=" * 50)
    print("NeuroDrive — Anxiety Model Trainer")
    print("=" * 50)
    print()

    rows = load_sessions()
    if not rows:
        print("\nNo session data found. Run some sessions first to collect training data.")
        print(f"Session CSVs should be in: {DATA_DIR}")
        print(f"Files should start with: {CSV_PREFIX}")
        return 1

    print(f"\nTotal rows loaded: {len(rows)}")

    print("\nApplying EMA smoothing to anxiety labels...")
    rows = compute_ema_labels(rows)

    X, y = extract_features_labels(rows)
    print(f"Feature matrix shape: {X.shape}")
    print(f"Target vector shape: {y.shape}")

    model, scaler, metrics = train_model(X, y)
    print_metrics(metrics)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, str(MODEL_PATH))
    joblib.dump(scaler, str(SCALER_PATH))

    print(f"\nModel saved to: {MODEL_PATH}")
    print(f"Scaler saved to: {SCALER_PATH}")
    print("\nDone! The ML predictor will now use this model automatically.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
