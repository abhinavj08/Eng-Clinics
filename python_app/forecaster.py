"""
AI Power Generation Forecaster.
Uses scikit-learn Random Forest Regressor to predict solar panel
power output for the next 1-6 hours based on historical telemetry.
"""

import time
import datetime
import numpy as np
from typing import Dict, Any, Optional, List

try:
    import pandas as pd
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    HAS_ML = True
except ImportError:
    HAS_ML = False

import database

class PowerForecaster:
    def __init__(self):
        self.model: Optional[Any] = None
        self.is_trained = False
        self.train_score: Dict[str, float] = {}
        self.last_train_time = 0
        self.min_samples = 60   # Need at least 60 records to train
        self.retrain_interval = 120  # Retrain every 2 minutes if new data

    def _build_features(self, df) -> Optional[Any]:
        """Extract time-based and rolling statistical features."""
        if df is None or df.empty or len(df) < 10:
            return None

        feat = pd.DataFrame()
        feat["hour"] = df["datetime"].dt.hour + df["datetime"].dt.minute / 60.0
        feat["hour_sin"] = np.sin(2 * np.pi * feat["hour"] / 24.0)
        feat["hour_cos"] = np.cos(2 * np.pi * feat["hour"] / 24.0)

        feat["power"] = df["power"].values
        feat["voltage"] = df["voltage"].values
        feat["current"] = df["current"].values
        feat["temp"] = df["temp_c"].values
        feat["humidity"] = df["humidity"].values
        feat["light"] = df["light"].values

        # Rolling statistics (window=5 samples)
        for col in ["power", "voltage", "light"]:
            feat[f"{col}_roll5_mean"] = df[col].rolling(5, min_periods=1).mean().values
            feat[f"{col}_roll5_std"] = df[col].rolling(5, min_periods=1).std().fillna(0).values

        # Lag features
        for lag in [1, 3, 5]:
            feat[f"power_lag{lag}"] = df["power"].shift(lag).fillna(0).values
            feat[f"light_lag{lag}"] = df["light"].shift(lag).fillna(0).values

        # Power-to-light ratio
        feat["pl_ratio"] = np.where(feat["light"] > 10,
                                    feat["power"] / feat["light"], 0)

        return feat

    def train(self, force=False) -> bool:
        """Train (or retrain) the Random Forest model on all available data."""
        if not HAS_ML:
            return False

        now = time.time()
        if not force and self.is_trained and (now - self.last_train_time < self.retrain_interval):
            return True  # Already trained recently

        df = database.all_samples_df()
        if df is None or len(df) < self.min_samples:
            return False

        feat = self._build_features(df)
        if feat is None:
            return False

        # Target: power at current timestep
        y = feat["power"].values

        # Features: everything except raw power
        feature_cols = [c for c in feat.columns if c != "power"]
        X = feat[feature_cols].values

        # Train/test split (last 20% for validation)
        split = int(len(X) * 0.8)
        X_train, X_test = X[:split], X[split:]
        y_train, y_test = y[:split], y[split:]

        if len(X_train) < 20 or len(X_test) < 5:
            return False

        self.model = RandomForestRegressor(
            n_estimators=50,
            max_depth=10,
            min_samples_leaf=3,
            random_state=42,
            n_jobs=-1
        )
        self.model.fit(X_train, y_train)

        # Evaluate
        y_pred = self.model.predict(X_test)
        self.train_score = {
            "mae": round(mean_absolute_error(y_test, y_pred), 2),
            "rmse": round(np.sqrt(mean_squared_error(y_test, y_pred)), 2),
            "r2": round(r2_score(y_test, y_pred), 4),
            "n_train": len(X_train),
            "n_test": len(X_test)
        }

        self.is_trained = True
        self.last_train_time = now
        self._feature_cols = feature_cols
        return True

    def predict_future(self, hours_ahead: int = 3) -> Optional[Any]:
        """
        Generate power forecast for the next `hours_ahead` hours
        at 15-minute intervals.
        Returns a DataFrame with columns: time, predicted_power
        """
        if not self.is_trained or self.model is None or not HAS_ML:
            return None

        df = database.all_samples_df()
        if df is None or len(df) < 10:
            return None

        feat = self._build_features(df)
        if feat is None:
            return None

        # Use last row as base state
        last_row = feat.iloc[-1:].copy()
        now = datetime.datetime.now()

        forecasts = []
        steps = hours_ahead * 4  # 15-minute intervals

        for step in range(1, steps + 1):
            future_dt = now + datetime.timedelta(minutes=15 * step)
            h = future_dt.hour + future_dt.minute / 60.0

            row = last_row.copy()
            row["hour"] = h
            row["hour_sin"] = np.sin(2 * np.pi * h / 24.0)
            row["hour_cos"] = np.cos(2 * np.pi * h / 24.0)

            X_pred = row[self._feature_cols].values.reshape(1, -1)
            pred_power = max(0, float(self.model.predict(X_pred)[0]))

            forecasts.append({
                "time": future_dt.strftime("%H:%M"),
                "hour_decimal": round(h, 2),
                "predicted_power_mw": round(pred_power, 1)
            })

        return pd.DataFrame(forecasts)

    def get_feature_importance(self) -> Optional[Dict[str, float]]:
        """Return top feature importances for explainability."""
        if not self.is_trained or self.model is None:
            return None

        importances = self.model.feature_importances_
        pairs = sorted(
            zip(self._feature_cols, importances),
            key=lambda x: x[1], reverse=True
        )
        return {name: round(float(imp), 4) for name, imp in pairs[:10]}
