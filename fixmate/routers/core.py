"""Health, service catalog, and PWA shell endpoints."""
from fastapi import APIRouter
from fastapi.responses import FileResponse
import platform_db as store
from fixmate.config import ROOT, MODEL_PATH
from fixmate import runtime

router = APIRouter()


@router.get("/")
def home():
    return FileResponse(ROOT / "app" / "index.html")


@router.get("/manifest.webmanifest")
def manifest():
    return FileResponse(ROOT / "app" / "manifest.webmanifest", media_type="application/manifest+json")


@router.get("/sw.js")
def service_worker():
    return FileResponse(ROOT / "app" / "sw.js", media_type="application/javascript")


@router.get("/api/health")
def health():
    return {"status": "ok", "service": "fixmate", "database": "sqlite", "allocation_model": MODEL_PATH.exists(),
            "forecast_model": bool(runtime.forecaster), "forecast_metrics": runtime.forecaster.metrics if runtime.forecaster else None}


@router.get("/api/services")
def list_services():
    with store.connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM services ORDER BY name")]
