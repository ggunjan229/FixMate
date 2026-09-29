"""Booking lifecycle, review, payment record, and invoice endpoints."""
from datetime import datetime, timedelta, timezone
import html
import json
import secrets
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
import platform_db as store
from forecasting import SERVICES
from fixmate.schemas import BookingInput, ReviewInput
from fixmate.security import current_user, require_role
from fixmate.services.matching import list_workers, rank_workers, public_worker
from fixmate.services.booking_serialization import booking_to_dict

router = APIRouter()


@router.post("/api/bookings")
def create_booking(payload: BookingInput, user=Depends(require_role("customer"))):
    if payload.service not in SERVICES: raise HTTPException(422, "Unknown service")
    try:
        scheduled = datetime.fromisoformat(payload.scheduled_at.replace("Z", "+00:00"))
    except ValueError: raise HTTPException(422, "Choose a valid appointment time")
    if scheduled < datetime.now(timezone.utc) - timedelta(minutes=5): raise HTTPException(422, "Appointment must be in the future")
    request = payload
    with store.connect() as db:
        workers = [w for w in list_workers(db) if payload.service.lower() in [s.lower() for s in w["skills"]]]
        # Prevent overlapping work windows (estimated as a two-hour service slot).
        requested_epoch = scheduled.timestamp()
        busy = db.execute("SELECT worker_id,scheduled_at FROM bookings WHERE status IN ('requested','accepted','in_progress')").fetchall()
        blocked_workers = set()
        for busy_row in busy:
            try:
                busy_time = datetime.fromisoformat(busy_row["scheduled_at"].replace("Z", "+00:00"))
                if abs(busy_time.timestamp()-requested_epoch) < 2*60*60:
                    blocked_workers.add(busy_row["worker_id"])
            except ValueError:
                continue
        workers = [w for w in workers if w["worker_id"] not in blocked_workers]
        ranked = rank_workers(workers, request)
        if not ranked: raise HTTPException(409, "No verified available worker covers this location yet. Try a wider service area or another time.")
        selected = ranked[0]
        base = db.execute("SELECT base_rate FROM services WHERE name=?", (payload.service,)).fetchone()
        amount = round(max(float(base["base_rate"]), selected["hourly_rate"]) * payload.quantity, 2)
        cur = db.execute("""INSERT INTO bookings(customer_id,worker_id,service,description,scheduled_at,address,latitude,
          longitude,emergency,quantity,status,payment_method,quoted_amount,model_score,match_method,match_factors,
          eligible_workers_count,match_features) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (user["id"], selected["worker_id"], payload.service, payload.description, scheduled.isoformat(), payload.address,
           payload.latitude, payload.longitude, int(payload.emergency), payload.quantity, "requested", payload.payment_method,
           amount, selected["score"], selected["score_method"], json.dumps(selected["score_factors"]),
           len(ranked), json.dumps(selected["candidate_features"])))
        booking = db.execute("""SELECT b.*,u.name AS worker_name FROM bookings b LEFT JOIN users u ON u.id=b.worker_id WHERE b.id=?""", (cur.lastrowid,)).fetchone()
    return {"booking": booking_to_dict(booking), "matched_worker": public_worker(selected),
            "eligible_workers_count": len(ranked),
            "matching": {"score": selected["score"], "method": selected["score_method"],
                         "factors": selected["score_factors"],
                         "candidate_features": selected["candidate_features"]}}


@router.get("/api/bookings")
def list_bookings(user=Depends(current_user)):
    with store.connect() as db:
        if user["role"] == "admin":
            rows = db.execute("""SELECT b.*,c.name customer_name,w.name worker_name FROM bookings b JOIN users c ON c.id=b.customer_id LEFT JOIN users w ON w.id=b.worker_id ORDER BY b.emergency DESC,b.created_at DESC LIMIT 200""").fetchall()
        elif user["role"] == "customer":
            rows = db.execute("""SELECT b.*,w.name worker_name FROM bookings b LEFT JOIN users w ON w.id=b.worker_id WHERE b.customer_id=? ORDER BY b.created_at DESC""", (user["id"],)).fetchall()
        else:
            rows = db.execute("""SELECT b.*,c.name customer_name FROM bookings b JOIN users c ON c.id=b.customer_id WHERE b.worker_id=? ORDER BY b.emergency DESC,b.created_at DESC""", (user["id"],)).fetchall()
    return [booking_to_dict(row) for row in rows]


@router.patch("/api/bookings/{booking_id}/status")
def update_booking(booking_id: int, status: Literal["accepted", "in_progress", "completed", "cancelled"], user=Depends(current_user)):
    transitions = {"requested": {"accepted", "cancelled"}, "accepted": {"in_progress", "cancelled"},
                   "in_progress": {"completed", "cancelled"}}
    with store.connect() as db:
        row = db.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        if not row: raise HTTPException(404, "Booking not found")
        if user["role"] == "worker" and row["worker_id"] != user["id"]: raise HTTPException(403, "This booking is assigned to another worker")
        if user["role"] == "customer" and (row["customer_id"] != user["id"] or status != "cancelled"):
            raise HTTPException(403, "Customers can only cancel their own booking")
        if user["role"] not in ("worker", "customer", "admin"): raise HTTPException(403, "Not allowed")
        if status not in transitions.get(row["status"], set()): raise HTTPException(409, f"Cannot move booking from {row['status']} to {status}")
        db.execute("UPDATE bookings SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, booking_id))
        changed = db.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
    return booking_to_dict(changed)


@router.post("/api/bookings/{booking_id}/review")
def add_review(booking_id: int, payload: ReviewInput, user=Depends(require_role("customer"))):
    with store.connect() as db:
        row = db.execute("SELECT * FROM bookings WHERE id=? AND customer_id=?", (booking_id, user["id"])).fetchone()
        if not row: raise HTTPException(404, "Booking not found")
        if row["status"] != "completed": raise HTTPException(409, "Reviews are available after a completed service")
        try:
            db.execute("INSERT INTO reviews(booking_id,customer_id,worker_id,rating,comment) VALUES(?,?,?,?,?)",
                       (booking_id, user["id"], row["worker_id"], payload.rating, payload.comment.strip()))
        except Exception as exc:
            if "UNIQUE constraint" in str(exc): raise HTTPException(409, "This booking already has a review")
            raise
    return {"saved": True}


@router.post("/api/bookings/{booking_id}/payment")
def record_payment(booking_id: int, user=Depends(require_role("customer"))):
    with store.connect() as db:
        row = db.execute("SELECT * FROM bookings WHERE id=? AND customer_id=?", (booking_id, user["id"])).fetchone()
        if not row: raise HTTPException(404, "Booking not found")
        if row["status"] != "completed": raise HTTPException(409, "Payment is recorded after the service is complete")
        if row["payment_status"] != "unpaid": raise HTTPException(409, "Payment has already been recorded")
        status = "demo_recorded" if row["payment_method"] == "demo_digital" else "cash_confirmed"
        ref = "DEMO-" + secrets.token_hex(4).upper()
        db.execute("INSERT INTO payments(booking_id,amount,method,status,reference) VALUES(?,?,?,?,?)",
                   (booking_id, row["quoted_amount"], row["payment_method"], status, ref))
        db.execute("UPDATE bookings SET payment_status=? WHERE id=?", (status, booking_id))
    return {"payment_status": status, "reference": ref, "note": "Demo ledger only; no money was moved." if status == "demo_recorded" else "Cash payment confirmed by customer."}


@router.get("/api/bookings/{booking_id}/invoice", response_class=HTMLResponse)
def invoice(booking_id: int, user=Depends(current_user)):
    with store.connect() as db:
        row = db.execute("""SELECT b.*,c.name customer_name,c.phone customer_phone,w.name worker_name,w.phone worker_phone
            FROM bookings b JOIN users c ON c.id=b.customer_id LEFT JOIN users w ON w.id=b.worker_id WHERE b.id=?""", (booking_id,)).fetchone()
    if not row: raise HTTPException(404, "Booking not found")
    b = dict(row)
    if user["role"] != "admin" and user["id"] not in (b["customer_id"], b["worker_id"]): raise HTTPException(403, "Invoice is private")
    # All values in HTML text are escaped by encoding through json + replacing angle brackets.
    def esc(s): return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    return HTMLResponse(f"""<!doctype html><meta charset=utf-8><title>FixMate invoice #{booking_id}</title><style>body{{font:16px system-ui;max-width:680px;margin:48px auto;padding:24px;color:#173c35}}h1{{color:#d86642}}.row{{display:flex;justify-content:space-between;border-bottom:1px solid #ddd;padding:12px 0}}button{{padding:12px 18px;background:#173c35;color:white;border:0;border-radius:8px}}@media print{{button{{display:none}}}}</style><h1>FixMate · Service invoice</h1><p>Cooperative service record · #{booking_id}</p><div class=row><b>Service</b><span>{esc(b['service'])}</span></div><div class=row><b>Customer</b><span>{esc(b['customer_name'])}</span></div><div class=row><b>Worker</b><span>{esc(b['worker_name'])}</span></div><div class=row><b>Appointment</b><span>{esc(b['scheduled_at'])}</span></div><div class=row><b>Address</b><span>{esc(b['address'])}</span></div><div class=row><b>Status</b><span>{esc(b['status'])}</span></div><div class=row><b>Payment</b><span>{esc(b['payment_status'])} · {esc(b['payment_method'])}</span></div><div class=row><b>Amount (INR)</b><strong>₹{float(b['quoted_amount']):,.2f}</strong></div><p>Final amount may be agreed directly before work begins. Digital checkout is a demonstration ledger and does not move funds.</p><button onclick="print()">Print / Save PDF</button>""")
