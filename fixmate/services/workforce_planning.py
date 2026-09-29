"""Connect demand forecasts to the cooperative's real, eligible worker roster."""
from __future__ import annotations

from collections import Counter
from datetime import date

import platform_db as store
from forecasting import LOCALITIES, LOCALITY_COORDINATES, SERVICES
from fixmate.services.matching import distance_km, list_workers


def _booking_history(db, service: str, locality: str) -> list[dict]:
    """Count non-cancelled past requests whose coordinates fall near a demo locality."""
    latitude, longitude = LOCALITY_COORDINATES[locality]
    counts: Counter[str] = Counter()
    rows = db.execute(
        """SELECT scheduled_at, latitude, longitude FROM bookings
           WHERE service = ? AND status != 'cancelled'""",
        (service,),
    ).fetchall()

    for row in rows:
        if distance_km(latitude, longitude, row["latitude"], row["longitude"]) > 6:
            continue
        scheduled_day = str(row["scheduled_at"])[:10]
        try:
            if date.fromisoformat(scheduled_day) < date.today():
                counts[scheduled_day] += 1
        except ValueError:
            continue

    return [{"date": day, "jobs": count} for day, count in counts.items()]


def _eligible_workers(db, service: str, locality: str) -> list[dict]:
    latitude, longitude = LOCALITY_COORDINATES[locality]
    candidates = []
    for worker in list_workers(db):
        has_skill = service.casefold() in {skill.casefold() for skill in worker["skills"]}
        distance = distance_km(latitude, longitude, worker["latitude"], worker["longitude"])
        if has_skill and distance <= worker["radius_km"]:
            candidates.append(worker)
    return candidates


def forecast_area(db, forecaster, service: str, locality: str, horizon: int) -> dict:
    history = _booking_history(db, service, locality)
    result = forecaster.predict(service, locality, horizon, booking_history=history)
    candidates = _eligible_workers(db, service, locality)
    required = result["peak_workers_required"]
    available = len(candidates)
    gap = max(0, required - available)
    result["workforce"] = {
        "workers_required_at_peak": required,
        "eligible_workers_available": available,
        "recruitment_gap": gap,
        "shortage": gap > 0,
        "basis": "Peak forecast jobs per day divided by 1.5 jobs per worker-shift.",
        "worker_names": [worker["name"] for worker in candidates],
    }
    return result


def sync_scarcity_alert(db, forecast: dict) -> None:
    """Create/update an in-app admin alert for the forecast's staffing window."""
    start = forecast["daily"][0]["date"]
    end = forecast["daily"][-1]["date"]
    gap = forecast["workforce"]["recruitment_gap"]
    values = (
        forecast["service"], forecast["locality"], start, end,
        forecast["predicted_jobs"], forecast["workforce"]["workers_required_at_peak"],
        forecast["workforce"]["eligible_workers_available"], gap,
        forecast["data_source"],
    )
    if gap:
        db.execute(
            """INSERT INTO admin_alerts
               (service, locality, forecast_start, forecast_end, predicted_jobs,
                workers_required, available_workers, worker_gap, data_source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(service, locality, forecast_start, forecast_end) DO UPDATE SET
                 predicted_jobs=excluded.predicted_jobs,
                 workers_required=excluded.workers_required,
                 available_workers=excluded.available_workers,
                 worker_gap=excluded.worker_gap,
                 data_source=excluded.data_source,
                 status=CASE WHEN admin_alerts.status IN ('closed', 'resolved')
                             THEN 'open' ELSE admin_alerts.status END,
                 updated_at=CURRENT_TIMESTAMP""",
            values,
        )
    else:
        db.execute(
            """UPDATE admin_alerts SET status='resolved', worker_gap=0,
               workers_required=?, available_workers=?, predicted_jobs=?, data_source=?,
               updated_at=CURRENT_TIMESTAMP
               WHERE service=? AND locality=? AND forecast_start=? AND forecast_end=?
                 AND status != 'closed'""",
            (
                forecast["workforce"]["workers_required_at_peak"],
                forecast["workforce"]["eligible_workers_available"],
                forecast["predicted_jobs"], forecast["data_source"],
                forecast["service"], forecast["locality"], start, end,
            ),
        )


def scan_all_areas(db, forecaster, horizon: int = 30) -> list[dict]:
    db.execute(
        """UPDATE admin_alerts SET status='resolved', updated_at=CURRENT_TIMESTAMP
           WHERE status='open' AND forecast_end < ?""",
        (date.today().isoformat(),),
    )
    alerts = []
    for service in SERVICES:
        for locality in LOCALITIES:
            area_forecast = forecast_area(db, forecaster, service, locality, horizon)
            sync_scarcity_alert(db, area_forecast)
            if area_forecast["workforce"]["shortage"]:
                alerts.append(area_forecast)

    rows = db.execute(
        """SELECT * FROM admin_alerts WHERE status IN ('open', 'recruiting')
           ORDER BY worker_gap DESC, forecast_start, service LIMIT 50"""
    ).fetchall()
    return [dict(row) for row in rows]
