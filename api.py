"""Backward-compatible ASGI entry point. Run with: uvicorn api:app --reload"""
from fixmate.main import app, create_app

__all__ = ["app", "create_app"]
