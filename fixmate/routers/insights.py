"""Forecast, cooperative administration, and worker summary endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
import platform_db as store
import analysis as data_analysis
from forecasting import LOCALITIES, SERVICES
from fixmate import runtime
from fixmate.security import require_role
from fixmate.services.matching import list_workers
from fixmate.services.booking_serialization import booking_to_dict
from fixmate.services.workforce_planning import (
    _observed_areas,
    forecast_area,
    scan_all_areas,
    sync_scarcity_alert,
)

router = APIRouter()


@router.get("/api/forecast")
def forecast(
    service: str = "Plumbing",
    locality: str = Query("Sector 14", min_length=1, max_length=100),
    horizon: int = Query(30, ge=1, le=90),
    latitude: float | None = Query(None, ge=-90, le=90),
    longitude: float | None = Query(None, ge=-180, le=180),
    user=Depends(require_role("admin")),
):
    if not runtime.forecaster: raise HTTPException(503, "Forecast model is warming up")
    try:
        with store.connect() as db:
            result = forecast_area(db, runtime.forecaster, service, locality, horizon, latitude, longitude)
            sync_scarcity_alert(db, result)
        return result
    except ValueError as exc: raise HTTPException(422, str(exc))


@router.post("/api/admin/workforce/scan")
def scan_workforce(user=Depends(require_role("admin"))):
    """Refresh area-by-area staffing alerts for the admin operations dashboard."""
    if not runtime.forecaster:
        raise HTTPException(503, "Forecast model is warming up")
    with store.connect() as db:
        areas_scanned = len(_observed_areas(db)) * len(SERVICES)
        alerts = scan_all_areas(db, runtime.forecaster)
    return {"alerts": alerts, "areas_scanned": areas_scanned}


@router.patch("/api/admin/alerts/{alert_id}/recruitment")
def update_recruitment_status(
    alert_id: int,
    status: str,
    user=Depends(require_role("admin")),
):
    allowed = {"not_started", "planned", "recruiting", "filled"}
    if status not in allowed:
        raise HTTPException(422, f"Status must be one of: {', '.join(sorted(allowed))}")
    with store.connect() as db:
        alert = db.execute("SELECT id FROM admin_alerts WHERE id=?", (alert_id,)).fetchone()
        if not alert:
            raise HTTPException(404, "Staffing alert not found")
        alert_status = "closed" if status == "filled" else "open"
        db.execute(
            """UPDATE admin_alerts SET recruitment_status=?,status=?,updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (status, alert_status, alert_id),
        )
    return {"alert_id": alert_id, "recruitment_status": status}


@router.get("/api/admin/overview")
def admin_overview(user=Depends(require_role("admin"))):
    with store.connect() as db:
        counts = {"workers": db.execute("SELECT COUNT(*) FROM workers WHERE verified=1").fetchone()[0],
          "worker_profiles": db.execute("SELECT COUNT(*) FROM workers").fetchone()[0],
          "pending_verification": db.execute("SELECT COUNT(*) FROM workers WHERE verified=0").fetchone()[0],
          "customers": db.execute("SELECT COUNT(*) FROM users WHERE role='customer'").fetchone()[0],
          "bookings": db.execute("SELECT COUNT(*) FROM bookings").fetchone()[0],
          "active_bookings": db.execute("SELECT COUNT(*) FROM bookings WHERE status IN ('requested','accepted','in_progress')").fetchone()[0],
          "completed": db.execute("SELECT COUNT(*) FROM bookings WHERE status='completed'").fetchone()[0],
          "cooperative_earnings": db.execute("SELECT COALESCE(SUM(quoted_amount),0) FROM bookings WHERE status='completed'").fetchone()[0]}
        workers = list_workers(db, include_pending=True)
        bookings = db.execute("""SELECT b.*,c.name customer_name,w.name worker_name FROM bookings b JOIN users c ON c.id=b.customer_id LEFT JOIN users w ON w.id=b.worker_id ORDER BY b.created_at DESC LIMIT 50""").fetchall()
    return {"counts": counts, "workers": workers, "bookings": [booking_to_dict(r) for r in bookings],
            "forecast_services": SERVICES, "forecast_localities": LOCALITIES}


@router.get("/api/admin/analytics")
def admin_analytics(user=Depends(require_role("admin"))):
    with store.connect() as db:
        by_service = [dict(r) for r in db.execute("SELECT service,COUNT(*) AS bookings,COALESCE(SUM(status='completed'),0) AS completed FROM bookings GROUP BY service ORDER BY bookings DESC")]
        by_status = [dict(r) for r in db.execute("SELECT status,COUNT(*) AS bookings FROM bookings GROUP BY status ORDER BY bookings DESC")]
        worker_load = [dict(r) for r in db.execute("""SELECT u.name,COUNT(b.id) AS completed_jobs FROM workers w JOIN users u ON u.id=w.user_id
            LEFT JOIN bookings b ON b.worker_id=u.id AND b.status='completed' WHERE w.verified=1 GROUP BY u.id ORDER BY completed_jobs DESC""")]
        review = db.execute("SELECT COUNT(*) AS count,ROUND(AVG(rating),2) AS average FROM reviews").fetchone()
        monthly = [dict(r) for r in db.execute("SELECT substr(created_at,1,7) AS month,COUNT(*) AS bookings FROM bookings GROUP BY month ORDER BY month DESC LIMIT 6")]
    loads = [row["completed_jobs"] for row in worker_load]
    return {"allocation_dataset": data_analysis.allocation_dataset_profile(),
            "platform": {"bookings_by_service": by_service, "booking_status": by_status,
              "monthly_bookings": list(reversed(monthly)), "worker_completed_jobs": worker_load,
              "completed_work_gini": data_analysis.gini(loads), "worker_count_for_gini": len(loads),
              "reviews": dict(review)},
            "forecast_model": runtime.forecaster.metrics if runtime.forecaster else None}


@router.patch("/api/admin/workers/{worker_id}/verification")
def verify_worker(worker_id: int, verified: bool, user=Depends(require_role("admin"))):
    with store.connect() as db:
        row = db.execute("SELECT user_id FROM workers WHERE user_id=?", (worker_id,)).fetchone()
        if not row: raise HTTPException(404, "Worker not found")
        db.execute("UPDATE workers SET verified=?,available=? WHERE user_id=?", (int(verified), int(verified), worker_id))
    return {"worker_id": worker_id, "verified": verified}


@router.get("/api/worker/summary")
def worker_summary(user=Depends(require_role("worker"))):
    with store.connect() as db:
        profile = db.execute("SELECT verified,available,welfare_status FROM workers WHERE user_id=?", (user["id"],)).fetchone()
        bookings = db.execute("SELECT COUNT(*) total,SUM(status='completed') completed,COALESCE(SUM(CASE WHEN status='completed' THEN quoted_amount ELSE 0 END),0) earnings FROM bookings WHERE worker_id=?", (user["id"],)).fetchone()
    return {"profile": dict(profile) if profile else {}, "bookings": dict(bookings)}
