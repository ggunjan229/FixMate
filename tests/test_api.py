"""API-level acceptance checks for a customer/worker/admin service lifecycle."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
from datetime import datetime, timedelta, timezone

os.environ["FIXMATE_DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="fixmate-test-")) / "fixmate.db")

from fastapi.testclient import TestClient
import pytest
import platform_db as store
from api import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def sign_in(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_customer_worker_booking_payment_and_review_lifecycle(client):
    customer = sign_in(client, "customer@fixmate.local", "customer123")
    worker = sign_in(client, "ravi@fixmate.local", "worker123")
    scheduled = (datetime_now_utc() + __import__("datetime").timedelta(days=1)).isoformat()
    created = client.post("/api/bookings", headers=customer, json={
        "service": "Plumbing", "description": "Kitchen tap leak", "scheduled_at": scheduled,
        "address": "Sector 14, Gurugram", "latitude": 28.4595, "longitude": 77.0266,
        "emergency": False, "quantity": 1, "payment_method": "demo_digital"})
    assert created.status_code == 200, created.text
    booking = created.json()["booking"]
    assert booking["worker_name"] == "Ravi Kumar"
    assert created.json()["matching"]["method"]
    assert booking["match_method"]
    assert "distance" in booking["match_factors"]
    assert booking["eligible_workers_count"] >= 1
    assert created.json()["eligible_workers_count"] == booking["eligible_workers_count"]
    assert created.json()["matched_worker"]["worker_id"] == booking["worker_id"]
    assert booking["match_features"]["service_skill_match"] is True
    assert "trained_model_probability" in booking["match_features"]

    for status in ("accepted", "in_progress", "completed"):
        response = client.patch(f"/api/bookings/{booking['id']}/status?status={status}", headers=worker)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == status

    paid = client.post(f"/api/bookings/{booking['id']}/payment", headers=customer)
    assert paid.status_code == 200 and paid.json()["payment_status"] == "demo_recorded"
    assert "no money was moved" in paid.json()["note"]
    reviewed = client.post(f"/api/bookings/{booking['id']}/review", headers=customer,
                           json={"rating": 5, "comment": "Clear and helpful service"})
    assert reviewed.status_code == 200
    invoice = client.get(f"/api/bookings/{booking['id']}/invoice", headers=customer)
    assert invoice.status_code == 200 and "Service invoice" in invoice.text


def test_worker_verification_blocks_unverified_worker(client):
    customer = sign_in(client, "customer@fixmate.local", "customer123")
    admin = sign_in(client, "admin@fixmate.local", "FixMate!2026")
    user = client.post("/api/auth/register", json={"name":"New Worker","email":"new.worker@example.test",
        "phone":"9876509999","password":"test-worker-pass","role":"worker"})
    assert user.status_code == 200
    headers = {"Authorization": f"Bearer {user.json()['token']}"}
    profile = client.put("/api/workers/profile", headers=headers, json={"skills":["Plumbing"],
        "experience_years":3,"certifications":["ITI"],"hourly_rate":350,"price_type":"per_visit",
        "latitude":28.4595,"longitude":77.0266,"radius_km":10,"bio":"Local plumber"})
    assert profile.status_code == 200 and not profile.json()["verified"]
    scheduled = (datetime_now_utc() + __import__("datetime").timedelta(days=2)).isoformat()
    request = {"service":"Plumbing","scheduled_at":scheduled,"address":"Sector 14, Gurugram",
        "latitude":28.4595,"longitude":77.0266}
    # The verified demo worker may be selected; the new unverified profile must not be returned as a candidate.
    available = client.get("/api/workers?service=Plumbing")
    assert user.json()["user"]["id"] not in [w["worker_id"] for w in available.json()]
    admin_result = client.patch(f"/api/admin/workers/{user.json()['user']['id']}/verification?verified=true", headers=admin)
    assert admin_result.status_code == 200
    available = client.get("/api/workers?service=Plumbing")
    assert user.json()["user"]["id"] in [w["worker_id"] for w in available.json()]
    booked = client.post("/api/bookings", headers=customer, json=request)
    assert booked.status_code == 200


def test_forecast_and_role_protection(client):
    admin = sign_in(client, "admin@fixmate.local", "FixMate!2026")
    overview = client.get("/api/admin/overview", headers=admin)
    assert overview.status_code == 200
    assert overview.json()["counts"]["workers"] == overview.json()["counts"]["worker_profiles"] - overview.json()["counts"]["pending_verification"]
    assert overview.json()["counts"]["pending_verification"] == 1
    result = client.get("/api/forecast?service=Plumbing&locality=Sector%2014&horizon=7", headers=admin)
    assert result.status_code == 200, result.text
    forecast = result.json()
    assert len(forecast["daily"]) == 7
    assert forecast["evaluation"]["holdout_days"] == 90
    assert forecast["data_source"] == "synthetic_demo"
    assert forecast["workforce"]["workers_required_at_peak"] == forecast["peak_workers_required"]
    assert forecast["workforce"]["eligible_workers_available"] >= 0

    # Real requests are persisted and begin calibrating the demand forecast once
    # the area has enough dated history to be useful.
    with store.connect() as db:
        customer_id = db.execute("SELECT id FROM users WHERE role='customer'").fetchone()[0]
        worker_id = db.execute("SELECT id FROM users WHERE email='ravi@fixmate.local'").fetchone()[0]
        for day_offset in range(40, 0, -4):
            scheduled = (datetime.now(timezone.utc) - timedelta(days=day_offset)).isoformat()
            db.execute(
                """INSERT INTO bookings(customer_id,worker_id,service,scheduled_at,address,
                   latitude,longitude,quoted_amount) VALUES(?,?,?,?,?,?,?,?)""",
                (customer_id, worker_id, "Plumbing", scheduled, "Sector 14, Gurugram",
                 28.4639, 77.0464, 350),
            )
    calibrated = client.get(
        "/api/forecast?service=Plumbing&locality=Sector%2014&horizon=7", headers=admin
    )
    assert calibrated.status_code == 200, calibrated.text
    assert calibrated.json()["data_source"] == "synthetic_model_calibrated_with_platform_bookings"
    assert calibrated.json()["real_bookings_used"] == 10

    scan = client.post("/api/admin/workforce/scan", headers=admin)
    assert scan.status_code == 200, scan.text
    assert scan.json()["areas_scanned"] == 54
    assert any(
        alert["service"] == "Plumbing" and alert["locality"] == "Sector 14"
        for alert in scan.json()["alerts"]
    )
    customer = sign_in(client, "customer@fixmate.local", "customer123")
    assert client.get("/api/admin/overview", headers=customer).status_code == 403
    analytics = client.get("/api/admin/analytics", headers=admin)
    assert analytics.status_code == 200
    profile = analytics.json()["allocation_dataset"]
    assert profile["rows"] == 20000 and profile["bookings"] == 3000 and profile["workers"] == 1000
    assert profile["missing_cells"] == 0


def test_public_services_workers_health_and_assistant(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert len(client.get("/api/services").json()) == 9
    public = client.get("/api/workers?service=Plumbing").json()
    assert public and all(worker["verified"] and worker["available"] for worker in public)
    assert all("phone" not in worker and "email" not in worker for worker in public)
    answer = client.post("/api/assistant", json={"question":"How do I book a service?","language":"en"})
    assert answer.status_code == 200 and answer.json()["action"] == "book"


def test_existing_worker_allocation_model_endpoint(client):
    response = client.post("/rank-candidates", json={"booking_id":"B-demo","quantity":1,
        "scheduled_hour":16,"day_of_week":2,"candidates":[
          {"worker_id":"W-demo-1","experience_years":8,"certifications_count":2,"has_certifications":1,
           "distance_km":2,"worker_skill_price":420,"worker_skill_price_type":"per_visit","platform_tenure_days":900},
          {"worker_id":"W-demo-2","experience_years":3,"certifications_count":0,"has_certifications":0,
           "distance_km":8,"worker_skill_price":550,"worker_skill_price_type":"per_hour","platform_tenure_days":120}]})
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["rankedWorkers"]) == 2
    assert result["rankedWorkers"][0]["rank"] == 1
    assert result["modelVersion"]


def test_app_shell_and_pwa_assets(client):
    home = client.get("/")
    assert home.status_code == 200 and "FixMate" in home.text
    assert client.get("/manifest.webmanifest").status_code == 200
    assert "display" in client.get("/manifest.webmanifest").text
    assert client.get("/sw.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/icon.svg").status_code == 200


def datetime_now_utc():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
