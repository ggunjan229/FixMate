"""Reproducible synthetic demand model for the demo; not a substitute for pilot data."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import math
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

SERVICES = ["Plumbing", "Electrical", "Carpentry", "Painting", "Cleaning", "Caregiving", "Driving", "Gardening", "Technician"]
LOCALITIES = ["Sector 14", "Sector 21", "DLF Phase 2", "Old Gurugram", "Sohna Road", "Sector 45"]
# Approximate demo centroids used consistently by forecasts and worker coverage checks.
LOCALITY_COORDINATES = {
    "Sector 14": (28.4639, 77.0464),
    "Sector 21": (28.5077, 77.0649),
    "DLF Phase 2": (28.4898, 77.0864),
    "Old Gurugram": (28.4664, 77.0320),
    "Sohna Road": (28.4200, 77.0410),
    "Sector 45": (28.4437, 77.0584),
}
BASE = {"Plumbing": 5.0, "Electrical": 4.0, "Carpentry": 2.0, "Painting": 2.0,
        "Cleaning": 8.0, "Caregiving": 3.0, "Driving": 4.0, "Gardening": 3.0, "Technician": 3.0}


def _features(day: date, locality: str, service: str) -> list[float]:
    dow, month = day.weekday(), day.month
    day_of_year = day.timetuple().tm_yday
    summer = 1 if month in (4, 5, 6) else 0
    monsoon = 1 if month in (6, 7, 8, 9) else 0
    temp = 27 + 9 * math.sin((month - 3) * math.pi / 6)
    rain = 18.0 if monsoon else 2.0
    return [LOCALITIES.index(locality), SERVICES.index(service), dow, int(dow >= 5), month,
            summer, monsoon, day_of_year, temp, rain]


def _expected(day: date, locality: str, service: str) -> float:
    f = _features(day, locality, service)
    base = BASE[service] * (1 + 0.10 * f[0]) * (1.28 if f[3] else 1.0)
    if service == "Plumbing": base *= 1 + 0.75 * f[6]
    if service == "Electrical": base *= 1 + 0.30 * f[6]
    if service == "Gardening": base *= 1 + 0.55 * f[5]
    if service == "Technician": base *= 1 + 0.45 * f[5]
    return max(0.2, base)


def _dataset(seed: int = 42, days: int = 1095):
    rng = np.random.default_rng(seed)
    start = date(2023, 1, 1)
    x, y = [], []
    for offset in range(days):
        day = start + timedelta(days=offset)
        for locality in LOCALITIES:
            for service in SERVICES:
                expected = _expected(day, locality, service)
                # The latent annual cycle and random variation are explicitly simulated.
                seasonal = 1 + 0.15 * math.sin((day.timetuple().tm_yday - 80) * 2 * math.pi / 365)
                count = rng.poisson(max(0.1, expected * seasonal))
                x.append(_features(day, locality, service)); y.append(count)
    return np.asarray(x, dtype=np.float32), np.asarray(y, dtype=np.float32)


class DemandForecaster:
    def __init__(self):
        x, y = _dataset()
        # Hold out the last 90 days: no random row split or future-to-past leakage.
        cutoff = (1095 - 90) * len(LOCALITIES) * len(SERVICES)
        self.model = HistGradientBoostingRegressor(max_iter=100, max_leaf_nodes=20, l2_regularization=2.0,
                                                   learning_rate=0.08, random_state=42)
        self.model.fit(x[:cutoff], y[:cutoff])
        predicted = np.maximum(0, self.model.predict(x[cutoff:]))
        residual = y[cutoff:] - predicted
        self.metrics = {"mae": round(float(mean_absolute_error(y[cutoff:], predicted)), 3),
                        "rmse": round(float(np.sqrt(mean_squared_error(y[cutoff:], predicted))), 3),
                        "holdout_days": 90, "validation": "last 90 days; chronological holdout"}
        self.error_band = float(np.quantile(np.abs(residual), 0.9))

    def predict(self, service: str, locality: str, horizon: int = 30, booking_history=None):
        if service not in SERVICES or not locality:
            raise ValueError("Choose a listed service and provide an area name")
        horizon = min(max(int(horizon), 1), 90)
        start = date.today()
        calibration = self._history_calibration(service, locality, booking_history or [])
        daily = []
        for offset in range(horizon):
            day = start + timedelta(days=offset)
            if locality in LOCALITIES:
                prior = float(self.model.predict(np.asarray([_features(day, locality, service)], dtype=np.float32))[0])
            else:
                # The synthetic model has no geography outside its six demo localities.
                # Use their average only as a clearly labelled cold-start prior.
                features = np.asarray([_features(day, known, service) for known in LOCALITIES], dtype=np.float32)
                prior = float(np.mean(self.model.predict(features)))
            point = max(0.0, prior)
            point *= calibration["factor"]
            daily.append({"date": day.isoformat(), "predicted_jobs": round(point, 1),
                          "lower": round(max(0, point - self.error_band), 1),
                          "upper": round(point + self.error_band, 1)})
        total = sum(row["predicted_jobs"] for row in daily)
        peak_daily_jobs = max((row["predicted_jobs"] for row in daily), default=0)
        return {"service": service, "locality": locality, "horizon_days": horizon,
                "predicted_jobs": round(total, 1), "workers_suggested": math.ceil(total / 1.5),
                "peak_daily_jobs": round(peak_daily_jobs, 1),
                "peak_workers_required": math.ceil(peak_daily_jobs / 1.5),
                "daily": daily, "evaluation": self.metrics,
                "data_source": calibration["data_source"],
                "real_bookings_used": calibration["real_bookings_used"],
                "data_note": calibration["data_note"]}

    def _history_calibration(self, service: str, locality: str, history: list[dict]) -> dict:
        """Calibrate the synthetic prior with real platform bookings once history is usable."""
        today = date.today()
        first_day = today - timedelta(days=56)
        observed = {}
        for row in history:
            try:
                day = date.fromisoformat(str(row["date"])[:10])
                count = max(0, int(row["jobs"]))
            except (KeyError, TypeError, ValueError):
                continue
            if first_day <= day < today:
                observed[day] = observed.get(day, 0) + count

        booking_count = sum(observed.values())
        has_coverage = bool(observed) and (max(observed) - min(observed)).days >= 27
        if booking_count < 10 or not has_coverage:
            return {
                "factor": 1.0,
                "data_source": "synthetic_demo",
                "real_bookings_used": booking_count,
                "data_note": (
                    f"Synthetic forecast prior. {booking_count} matching real bookings are recorded; "
                    "at least 10 bookings spanning 28 days are needed for history calibration."
                ),
            }

        model_values = []
        observed_values = []
        for offset in range(56):
            day = first_day + timedelta(days=offset)
            count = observed.get(day, 0)
            if locality in LOCALITIES:
                feature_rows = np.asarray([_features(day, locality, service)], dtype=np.float32)
            else:
                feature_rows = np.asarray([_features(day, known, service) for known in LOCALITIES], dtype=np.float32)
            model_values.append(max(0.1, float(np.mean(self.model.predict(feature_rows)))))
            observed_values.append(count)
        model_mean = float(np.mean(model_values))
        observed_mean = float(np.mean(observed_values))
        factor = min(2.0, max(0.5, observed_mean / model_mean))
        return {
            "factor": factor,
            "data_source": "synthetic_model_calibrated_with_platform_bookings",
            "real_bookings_used": booking_count,
            "data_note": (
                f"Synthetic ML forecast calibrated using {booking_count} real, non-cancelled "
                f"{service} bookings mapped to {locality} over the last 56 days."
            ),
        }
