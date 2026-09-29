"""Registration, sign-in, and current-session endpoints."""
from fastapi import APIRouter, Depends, HTTPException
import platform_db as store
from fixmate.schemas import RegisterInput, LoginInput
from fixmate.security import _token, current_user

router = APIRouter()


@router.post("/api/auth/register")
def register(payload: RegisterInput):
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "Enter a valid email address")
    try:
        with store.connect() as db:
            cur = db.execute("INSERT INTO users(name,email,phone,password_hash,role,language) VALUES(?,?,?,?,?,?)",
                (payload.name.strip(), email, payload.phone.strip(), store.hash_password(payload.password), payload.role, payload.language))
            uid = cur.lastrowid
            if payload.role == "worker":
                db.execute("INSERT INTO workers(user_id,skills,verified,available) VALUES(?,?,0,0)", (uid, "[]"))
            row = db.execute("SELECT id,name,email,phone,role,language FROM users WHERE id=?", (uid,)).fetchone()
        user = dict(row)
        return {"token": _token(user), "user": user, "needs_worker_profile": payload.role == "worker"}
    except Exception as exc:
        if "UNIQUE constraint" in str(exc): raise HTTPException(409, "An account with this email already exists")
        raise


@router.post("/api/auth/login")
def login(payload: LoginInput):
    with store.connect() as db:
        row = db.execute("SELECT * FROM users WHERE email=?", (payload.email.strip().lower(),)).fetchone()
    if not row or not store.verify_password(payload.password, row["password_hash"]):
        raise HTTPException(401, "Email or password is incorrect")
    user = {key: row[key] for key in ("id", "name", "email", "phone", "role", "language")}
    return {"token": _token(user), "user": user}


@router.get("/api/me")
def me(user=Depends(current_user)):
    if user["role"] == "worker":
        with store.connect() as db:
            row = db.execute("SELECT * FROM workers WHERE user_id=?", (user["id"],)).fetchone()
        if row:
            user["worker_profile"] = dict(row)
    return user
