"""Session token creation and role-based request dependencies."""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import time
from fastapi import Depends, Header, HTTPException
import platform_db as store
from fixmate.config import TOKEN_SECRET


def _token(user: dict) -> str:
    payload = {"sub": user["id"], "role": user["role"], "exp": int(time.time()) + 60 * 60 * 24 * 7}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(TOKEN_SECRET, body.encode(), hashlib.sha256).digest()
    return body + "." + base64.urlsafe_b64encode(sig).decode().rstrip("=")


def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in to continue")
    try:
        body, signature = authorization[7:].split(".", 1)
        expected = base64.urlsafe_b64encode(hmac.new(TOKEN_SECRET, body.encode(), hashlib.sha256).digest()).decode().rstrip("=")
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if payload["exp"] < time.time():
            raise ValueError("expired")
        with store.connect() as db:
            row = db.execute("SELECT id,name,email,phone,role,language FROM users WHERE id=?", (payload["sub"],)).fetchone()
        if not row:
            raise ValueError("missing user")
        return dict(row)
    except (ValueError, KeyError, json.JSONDecodeError):
        raise HTTPException(401, "Session expired. Please sign in again")


def require_role(*roles: str):
    def check(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "This account cannot access that action")
        return user
    return check
