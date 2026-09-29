"""Worker profile, discovery, availability, and matching endpoints."""
from fastapi import APIRouter, Depends, Query
import json
import platform_db as store
from fixmate.schemas import WorkerProfile
from fixmate.security import require_role
from fixmate.services.matching import list_workers, public_worker, distance_km

router = APIRouter()


@router.put("/api/workers/profile")
def save_worker_profile(payload: WorkerProfile, user=Depends(require_role("worker"))):
    with store.connect() as db:
        db.execute("""UPDATE workers SET skills=?,experience_years=?,certifications=?,hourly_rate=?,price_type=?,
          latitude=?,longitude=?,radius_km=?,bio=? WHERE user_id=?""",
          (json.dumps(sorted(set(s.strip().title() for s in payload.skills if s.strip()))), payload.experience_years,
           json.dumps(payload.certifications), payload.hourly_rate, payload.price_type, payload.latitude,
           payload.longitude, payload.radius_km, payload.bio, user["id"]))
        row = db.execute("SELECT verified FROM workers WHERE user_id=?", (user["id"],)).fetchone()
    return {"saved": True, "verified": bool(row["verified"]), "message": "Profile submitted for cooperative verification." if not row["verified"] else "Profile updated."}


@router.get("/api/workers")
def search_workers(service: str | None = None, latitude: float | None = None, longitude: float | None = None,
                   limit: int = Query(30, ge=1, le=100)):
    with store.connect() as db:
        workers = list_workers(db)
    if service: workers = [w for w in workers if service.lower() in [s.lower() for s in w["skills"]]]
    for w in workers:
        w["distance_km"] = round(distance_km(latitude, longitude, w["latitude"], w["longitude"]), 2) if latitude is not None and longitude is not None else None
    return [public_worker(w) for w in workers[:limit]]


@router.get("/api/workers/me")
def my_worker_profile(user=Depends(require_role("worker"))):
    with store.connect() as db:
        result = [w for w in list_workers(db, include_pending=True) if w["worker_id"] == user["id"]]
    return result[0] if result else None


@router.patch("/api/workers/me/availability")
def set_availability(available: bool, user=Depends(require_role("worker"))):
    with store.connect() as db:
        db.execute("UPDATE workers SET available=? WHERE user_id=? AND verified=1", (int(available), user["id"]))
    return {"available": available}
