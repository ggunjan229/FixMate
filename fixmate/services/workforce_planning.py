"""Connect area-level demand forecasts to real bookings and eligible workers."""
from __future__ import annotations

from collections import Counter
from datetime import date

from forecasting import LOCALITIES, LOCALITY_COORDINATES, SERVICES
from fixmate.services.matching import distance_km, list_workers

AREA_HISTORY_RADIUS_KM = 6.0


def _booking_history(db, service: str, latitude: float, longitude: float) -> list[dict]:
    """Count real requests by creation day within the requested service area."""
    counts: Counter[str] = Counter()
    rows = db.execute(
        """SELECT created_at, latitude, longitude FROM bookings
           WHERE service = ? AND status != 'cancelled'""",
        (service,),
    ).fetchall()
    for row in rows:
        if distance_km(latitude, longitude, row["latitude"], row["longitude"]) > AREA_HISTORY_RADIUS_KM:
            continue
        # Demand means incoming requests, not a potentially future appointment date.
        request_day = str(row["created_at"])[:10]
        try:
            if date.fromisoformat(request_day) < date.today():
                counts[request_day] += 1
        except ValueError:
            continue
    return [{"date": day, "jobs": count} for day, count in counts.items()]


def _eligible_workers(db, service: str, latitude: float, longitude: float) -> list[dict]:
    candidates = []
    for worker in list_workers(db):
        has_skill = service.casefold() in {skill.casefold() for skill in worker["skills"]}
        distance = distance_km(latitude, longitude, worker["latitude"], worker["longitude"])
        if has_skill and distance <= worker["radius_km"]:
            candidates.append(worker)
    return candidates


def forecast_area(
    db, forecaster, service: str, locality: str, horizon: int,
    latitude: float | None = None, longitude: float | None = None,
) -> dict:
    """Forecast any named area from coordinates; old demo-locality calls still work."""
    if service not in SERVICES:
        raise ValueError("Choose a valid service category")
    if not locality or len(locality.strip()) > 100:
        raise ValueError("Area name must contain 1 to 100 characters")
    if latitude is None and longitude is None:
        if locality not in LOCALITY_COORDINATES:
            raise ValueError("Provide latitude and longitude for an area outside the demo localities")
        latitude, longitude = LOCALITY_COORDINATES[locality]
    elif latitude is None or longitude is None:
        raise ValueError("Provide both latitude and longitude")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Coordinates are outside the valid latitude/longitude range")

    history = _booking_history(db, service, latitude, longitude)
    result = forecaster.predict(service, locality, horizon, booking_history=history)
    candidates = _eligible_workers(db, service, latitude, longitude)
    required = result["peak_workers_required"]
    available = len(candidates)
    gap = max(0, required - available)
    result["area"] = {
        "name": locality, "latitude": latitude, "longitude": longitude,
        "booking_history_radius_km": AREA_HISTORY_RADIUS_KM,
    }
    result["workforce"] = {
        "workers_required_at_peak": required,
        "eligible_workers_available": available,
        "recruitment_gap": gap,
        "shortage": gap > 0,
        "basis": "Peak forecast jobs per day divided by 1.5 jobs per worker-shift.",
        "worker_names": [worker["name"] for worker in candidates],
    }
    return result


def _observed_areas(db) -> list[tuple[str, float, float]]:
    """Add coordinate areas where customers or completed worker profiles exist."""
    areas = [(name, coords[0], coords[1]) for name, coords in LOCALITY_COORDINATES.items()]
    rows = db.execute(
        """SELECT latitude, longitude FROM bookings
           UNION ALL SELECT latitude, longitude FROM workers WHERE skills != '[]'"""
    ).fetchall()
    for row in rows:
        lat, lon = float(row["latitude"]), float(row["longitude"])
        if any(distance_km(lat, lon, area_lat, area_lon) <= AREA_HISTORY_RADIUS_KM
               for _, area_lat, area_lon in areas):
            continue
        areas.append((f"Area {lat:.3f}, {lon:.3f}", lat, lon))
    return areas


def sync_scarcity_alert(db, forecast: dict) -> None:
    """Create/update an in-app admin alert for the forecast's staffing window."""
    start = forecast["daily"][0]["date"]
    end = forecast["daily"][-1]["date"]
    gap = forecast["workforce"]["recruitment_gap"]
    values = (
        forecast["service"], forecast["locality"], start, end,
        forecast["predicted_jobs"], forecast["workforce"]["workers_required_at_peak"],
        forecast["workforce"]["eligible_workers_available"], gap, forecast["data_source"],
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
    areas = _observed_areas(db)
    for service in SERVICES:
        for locality, latitude, longitude in areas:
            result = forecast_area(db, forecaster, service, locality, horizon, latitude, longitude)
            sync_scarcity_alert(db, result)

    rows = db.execute(
        """SELECT * FROM admin_alerts WHERE status IN ('open', 'recruiting')
           ORDER BY worker_gap DESC, forecast_start, service LIMIT 100"""
    ).fetchall()
    return [dict(row) for row in rows]
