"""Worker eligibility, geospatial coverage, and explainable candidate ranking."""
from __future__ import annotations

import json
import math
from datetime import datetime

from fixmate.config import MODEL_PATH
from fixmate.schemas import BookingInput

_allocation_artifact = None


def _worker_row(row) -> dict:
    worker = dict(row)
    worker["skills"] = json.loads(worker.pop("skills_json", "[]"))
    worker["certifications"] = json.loads(worker.pop("certifications_json", "[]"))
    worker["verified"] = bool(worker["verified"])
    worker["available"] = bool(worker["available"])
    worker["rating"] = round(float(worker.pop("rating_avg", 0) or 0), 1)
    worker["review_count"] = int(worker.pop("review_count", 0) or 0)
    worker["active_jobs"] = int(worker.get("active_jobs", 0) or 0)
    worker["platform_tenure_days"] = int(worker.get("platform_tenure_days", 0) or 0)
    return worker


def list_workers(db, include_pending: bool = False) -> list[dict]:
    """Load worker profiles and current activity, with eligibility filters applied."""
    eligibility = "" if include_pending else "WHERE w.verified=1 AND w.available=1"
    rows = db.execute(
        f"""SELECT u.id AS worker_id,u.name,u.phone,u.email,u.role,
            w.skills AS skills_json,w.experience_years,
            w.certifications AS certifications_json,w.verified,w.available,
            w.hourly_rate,w.price_type,w.society,w.latitude,w.longitude,
            w.radius_km,w.bio,w.welfare_status,
            CAST(julianday('now') - julianday(u.created_at) AS INTEGER) AS platform_tenure_days,
            COALESCE(AVG(r.rating),0) AS rating_avg,COUNT(r.id) AS review_count,
            (SELECT COUNT(*) FROM bookings b WHERE b.worker_id=u.id
             AND b.status IN ('requested','accepted','in_progress')) AS active_jobs
            FROM workers w JOIN users u ON u.id=w.user_id
            LEFT JOIN reviews r ON r.worker_id=u.id
            {eligibility} GROUP BY u.id"""
    ).fetchall()
    return [_worker_row(row) for row in rows]


def public_worker(worker: dict) -> dict:
    """Remove private contact details from public/customer-facing worker data."""
    return {key: value for key, value in worker.items() if key not in ("phone", "email")}


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two latitude/longitude points."""
    earth_radius_km = 6371.0
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon / 2) ** 2
    )
    return 2 * earth_radius_km * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))


def _transparent_score(worker: dict, distance: float, emergency: bool) -> tuple[float, dict]:
    factors = {
        "availability": 1.0,
        "skill": 1.0,
        "distance": max(0.0, 1 - distance / max(worker["radius_km"], 1)),
        "experience": min(1.0, worker["experience_years"] / 12),
        "certifications": min(1.0, len(worker["certifications"]) / 3),
        "rating": min(1.0, worker["rating"] / 5),
        "workload_fairness": 1 / (1 + 0.35 * worker.get("active_jobs", 0)),
    }
    distance_weight = 0.35 if emergency else 0.20
    rating_weight = 0.10 if emergency else 0.15
    workload_weight = 0.05 if emergency else 0.10
    score = (
        (0.22 if emergency else 0.25) * factors["skill"]
        + distance_weight * factors["distance"]
        + 0.15 * factors["availability"]
        + rating_weight * factors["rating"]
        + 0.08 * factors["experience"]
        + 0.05 * factors["certifications"]
        + workload_weight * factors["workload_fairness"]
    )
    return score, factors


def _load_allocation_model():
    global _allocation_artifact
    if _allocation_artifact is None and MODEL_PATH.exists():
        import joblib

        _allocation_artifact = joblib.load(MODEL_PATH)
    return _allocation_artifact


def _model_scores(candidates: list[dict], request: BookingInput) -> list[float] | None:
    """Score all candidates together so within-booking relative features are meaningful."""
    try:
        import pandas as pd
        import my_ml_core

        artifact = _load_allocation_model()
        if artifact is None:
            return None
        scheduled = datetime.fromisoformat(request.scheduled_at.replace("Z", "+00:00"))
        rows = [
            {
                my_ml_core.GROUP_COLUMN: "live-booking",
                "worker_id": str(worker["worker_id"]),
                "quantity": request.quantity,
                "scheduled_hour": scheduled.hour,
                "day_of_week": scheduled.weekday(),
                "experience_years": worker["experience_years"],
                "certifications_count": len(worker["certifications"]),
                "has_certifications": int(bool(worker["certifications"])),
                "distance_km": worker["distance_km"],
                "worker_skill_price": worker["hourly_rate"],
                "worker_skill_price_type": worker["price_type"],
                "platform_tenure_days": worker["platform_tenure_days"],
            }
            for worker in candidates
        ]
        frame = my_ml_core.add_relative_features(pd.DataFrame(rows))
        probabilities = artifact["pipeline"].predict_proba(
            frame[artifact["feature_columns"]]
        )[:, 1]
        return [float(probability) for probability in probabilities]
    except Exception:
        # A missing/incompatible model must not stop a customer from booking.
        return None


def rank_workers(workers: list[dict], request: BookingInput) -> list[dict]:
    """Filter out-of-radius candidates and rank the remaining workers fairly."""
    scheduled = datetime.fromisoformat(request.scheduled_at.replace("Z", "+00:00"))
    candidates = []
    for worker in workers:
        distance = distance_km(
            request.latitude, request.longitude,
            worker["latitude"], worker["longitude"],
        )
        if distance > worker["radius_km"]:
            continue
        fallback_score, factors = _transparent_score(worker, distance, request.emergency)
        candidates.append({**worker, "distance_km": round(distance, 2),
                           "_fallback_score": fallback_score, "score_factors": factors})

    model_scores = _model_scores(candidates, request) if candidates else None
    model_name = (_allocation_artifact or {}).get("model_name", "model")
    for index, candidate in enumerate(candidates):
        fallback_score = candidate.pop("_fallback_score")
        factors = candidate["score_factors"]
        if model_scores is None:
            final_score = fallback_score
            method = "transparent_fair_match_v1"
            probability = None
        else:
            probability = model_scores[index]
            final_score = 0.70 * probability + 0.30 * fallback_score
            factors["trained_model_probability"] = probability
            method = f"hybrid_{model_name}_fairness_v1"
        candidate.update(
            score=round(final_score, 4),
            score_method=method,
            score_factors={key: round(value, 3) for key, value in factors.items()},
            estimated_amount=round(candidate["hourly_rate"] * request.quantity, 2),
            candidate_features={
                "service_skill_match": True,
                "verified": candidate["verified"],
                "available": candidate["available"],
                "distance_km": candidate["distance_km"],
                "service_radius_km": candidate["radius_km"],
                "average_rating": candidate["rating"],
                "experience_years": candidate["experience_years"],
                "certification_count": len(candidate["certifications"]),
                "hourly_rate": candidate["hourly_rate"],
                "price_type": candidate["price_type"],
                "platform_tenure_days": candidate["platform_tenure_days"],
                "active_bookings": candidate["active_jobs"],
                "trained_model_probability": round(probability, 4) if probability is not None else None,
                "fairness_score": round(fallback_score, 4),
                "final_score": round(final_score, 4),
                "appointment_quantity": request.quantity,
                "appointment_hour": scheduled.hour,
                "appointment_weekday": scheduled.weekday(),
                "emergency_priority": request.emergency,
            },
        )

    return sorted(
        candidates,
        key=lambda worker: (worker["score"], worker["rating"], -worker["distance_km"]),
        reverse=True,
    )


def rank_candidate_payload(payload: dict) -> dict:
    """Score supplied candidate rows for the existing standalone ranking API."""
    import pandas as pd
    import my_ml_core

    candidates = payload.get("candidates", [])
    if not candidates:
        raise ValueError("candidates list must not be empty")
    artifact = _load_allocation_model()
    if artifact is None:
        raise FileNotFoundError("Allocation model missing. Train with python train.py")

    rows = [
        {
            my_ml_core.GROUP_COLUMN: str(payload.get("booking_id", "demo")),
            "worker_id": candidate.get("worker_id", f"W{index}"),
            "quantity": payload.get("quantity", 1),
            "scheduled_hour": payload.get("scheduled_hour", 16),
            "day_of_week": payload.get("day_of_week", 0),
            **{key: value for key, value in candidate.items() if key != "worker_id"},
        }
        for index, candidate in enumerate(candidates)
    ]
    frame = my_ml_core.add_relative_features(pd.DataFrame(rows))
    scores = artifact["pipeline"].predict_proba(frame[artifact["feature_columns"]])[:, 1]
    ranked = sorted(
        (
            {"worker_id": str(row["worker_id"]), "score": round(float(score), 4)}
            for row, score in zip(rows, scores)
        ),
        key=lambda candidate: candidate["score"],
        reverse=True,
    )
    return {
        "rankedWorkers": [{**row, "rank": index + 1} for index, row in enumerate(ranked)],
        "modelVersion": artifact.get("model_name", "unknown"),
    }
