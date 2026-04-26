from __future__ import annotations

import json
import logging
import os
import pickle
import warnings
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import xgboost as xgb

from tradingcat.domain.models import Bar

warnings.filterwarnings("ignore", category=UserWarning)
logger = logging.getLogger(__name__)

ModelCategory = Literal["xgboost_rank", "xgboost_regression", "xgboost_classification"]


@dataclass
class MLSignal:
    symbol: str
    score: float  # 0-1 score
    prediction: float  # raw model output
    feature_importance: dict[str, float] | None = None
    model_name: str = ""


@dataclass
class MLSignalResult:
    as_of: date
    signals: list[MLSignal]
    model_name: str
    n_features: int
    feature_names: list[str] = field(default_factory=list)
    top_features: list[tuple[str, float]] = field(default_factory=list)


@dataclass
class TrainingMetrics:
    train_score: float
    val_score: float
    walk_forward_sharpe: float
    feature_importance: dict[str, float]
    n_epochs: int
    n_samples: int
    n_features: int


class ModelRegistry:
    """Persist and load ML models to/from disk."""

    _MODELS_DIR = Path("data/models")

    def __init__(self, models_dir: Path | None = None) -> None:
        self._dir = models_dir or self._MODELS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, model: xgb.Booster, name: str, metadata: dict | None = None) -> Path:
        path = self._dir / f"{name}.json"
        model.save_model(str(path))
        if metadata:
            meta_path = self._dir / f"{name}_meta.json"
            meta_path.write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
        logger.info("Model saved: %s", path)
        return path

    def load(self, name: str) -> xgb.Booster:
        model = xgb.Booster()
        model.load_model(str(self._dir / f"{name}.json"))
        return model

    def list_models(self) -> list[str]:
        return sorted({p.stem for p in self._dir.glob("*.json") if not p.stem.endswith("_meta")})

    def latest_model(self) -> str | None:
        models = self.list_models()
        return models[-1] if models else None

    def exists(self, name: str) -> bool:
        return (self._dir / f"{name}.json").exists()


class MLPipeline:
    """End-to-end ML pipeline: feature prep → training → inference → signal generation."""

    def __init__(self, models_dir: Path | None = None) -> None:
        self._registry = ModelRegistry(models_dir)

    # ---- feature preparation ----

    def prepare_training_data(
        self,
        feature_history: dict[str, pd.DataFrame],
        forward_returns: dict[str, pd.Series],
        lookback_days: int = 252,
    ) -> tuple[pd.DataFrame, pd.Series]:
        """Align features and forward returns across symbols and time.

        feature_history: {symbol: DataFrame with date index and feature columns}
        forward_returns: {symbol: Series with date index and forward return values}
        """
        X_list: list[pd.DataFrame] = []
        y_list: list[pd.Series] = []
        for symbol in feature_history:
            if symbol not in forward_returns:
                continue
            feat = feature_history[symbol].tail(lookback_days)
            ret = forward_returns[symbol].reindex(feat.index).dropna()
            feat_aligned = feat.loc[ret.index]
            if len(feat_aligned) < 10:
                continue
            X_list.append(feat_aligned)
            y_list.append(ret)
        if not X_list:
            raise ValueError("No aligned training data after merging features and returns.")
        X = pd.concat(X_list).astype(np.float32)
        y = pd.concat(y_list).astype(np.float32)
        # Drop constant and NaN columns
        X = X.loc[:, X.nunique() > 1]
        X = X.fillna(X.median())
        return X, y

    # ---- training ----

    def train_xgboost(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        val_split: float = 0.2,
        category: ModelCategory = "xgboost_rank",
        max_epochs: int = 200,
        early_stop: int = 20,
    ) -> tuple[xgb.Booster, TrainingMetrics]:
        """Train XGBoost model with early stopping."""
        split_idx = int(len(X) * (1 - val_split))
        X_train, X_val = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_val = y.iloc[:split_idx], y.iloc[split_idx:]

        params: dict = {
            "objective": "reg:squarederror",
            "eval_metric": "rmse",
            "learning_rate": 0.05,
            "max_depth": 5,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "verbosity": 0,
            "seed": 42,
        }

        dtrain = xgb.DMatrix(X_train, label=y_train)
        dval = xgb.DMatrix(X_val, label=y_val)

        model = xgb.train(
            params,
            dtrain,
            num_boost_round=max_epochs,
            evals=[(dtrain, "train"), (dval, "val")],
            early_stopping_rounds=early_stop,
            verbose_eval=False,
        )

        train_pred = model.predict(dtrain)
        val_pred = model.predict(dval)

        imp = model.get_score(importance_type="gain")
        sorted_imp = dict(sorted(imp.items(), key=lambda x: -x[1])[:30])

        return model, TrainingMetrics(
            train_score=float(np.corrcoef(y_train, train_pred)[0, 1]) if len(y_train) > 1 else 0.0,
            val_score=float(np.corrcoef(y_val, val_pred)[0, 1]) if len(y_val) > 1 else 0.0,
            walk_forward_sharpe=0.0,
            feature_importance=sorted_imp,
            n_epochs=model.best_iteration if hasattr(model, "best_iteration") else max_epochs,
            n_samples=len(X),
            n_features=X.shape[1],
        )

    # ---- inference ----

    def predict(self, model: xgb.Booster, features: pd.DataFrame) -> np.ndarray:
        """Run inference on feature DataFrame."""
        dmatrix = xgb.DMatrix(features.astype(np.float32))
        return model.predict(dmatrix)

    def generate_signals(
        self,
        model: xgb.Booster,
        features: pd.DataFrame,
        model_name: str = "",
        top_k: int = 5,
    ) -> MLSignalResult:
        """Generate ranked signals from model predictions."""
        preds = self.predict(model, features)
        scores = 1.0 / (1.0 + np.exp(-preds))  # sigmoid normalization to [0, 1]

        imp = model.get_score(importance_type="gain")
        sorted_imp = sorted(imp.items(), key=lambda x: -x[1])[:10]

        signal_list = [
            MLSignal(symbol=symbol, score=float(score), prediction=float(pred),
                     model_name=model_name)
            for symbol, score, pred in zip(features.index, scores, preds)
        ]
        signal_list.sort(key=lambda s: s.score, reverse=True)
        signal_list = signal_list[:top_k]

        return MLSignalResult(
            as_of=date.today(),
            signals=signal_list,
            model_name=model_name,
            n_features=features.shape[1],
            feature_names=list(features.columns),
            top_features=[(sym, sc) for sym, sc in sorted_imp],
        )

    # ---- full workflow ----

    def full_train(
        self,
        feature_history: dict[str, pd.DataFrame],
        forward_returns: dict[str, pd.Series],
        model_name: str | None = None,
        category: ModelCategory = "xgboost_rank",
    ) -> tuple[str, TrainingMetrics]:
        """End-to-end training: prepare data → train → save model."""
        X, y = self.prepare_training_data(feature_history, forward_returns)
        model, metrics = self.train_xgboost(X, y, category=category)
        name = model_name or f"xgboost_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
        self._registry.save(model, name, metadata={
            "features": list(X.columns),
            "n_samples": len(X),
            "metrics": {"train_score": metrics.train_score, "val_score": metrics.val_score},
            "trained_at": datetime.now(UTC).isoformat(),
        })
        logger.info("Model %s trained: train_r=%.4f, val_r=%.4f", name, metrics.train_score, metrics.val_score)
        return name, metrics
