"""FastAPI application factory and router registration."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import platform_db as store
from fixmate.config import ROOT
from fixmate import runtime
from fixmate.routers import assistant, auth, bookings, core, insights, matching, workers


@asynccontextmanager
async def lifespan(_app):
    runtime.forecaster = runtime.DemandForecaster()
    yield
    runtime.forecaster = None


def create_app() -> FastAPI:
    app = FastAPI(
        title="FixMate Cooperative Services",
        version="1.0.0",
        lifespan=lifespan,
        description="Marketplace, cooperative administration, matching, and demand analytics.",
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )
    app.mount("/static", StaticFiles(directory=ROOT / "app"), name="static")
    for route_module in (core, auth, workers, bookings, assistant, insights, matching):
        app.include_router(route_module.router)
    return app


store.init_db()
app = create_app()
