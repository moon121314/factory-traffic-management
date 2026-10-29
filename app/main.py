import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware  # <-- ADDED

import app.models  # noqa: F401
from app.api.commands import router as commands_router
from app.api.controller_events import router as controller_events_router
from app.api.health import router as health_router
from app.api.junctions import router as junctions_router
from app.api.sensor_events import router as sensor_events_router
from app.config import settings
from app.controller.rest_simulator import (
    RestControllerClient, SimulatorControllerClient,
)
from app.db import Base, SessionLocal, engine
from app.domain.clock import SystemClock
from app.services import controller_service, recovery_service, scheduler_service

logger = logging.getLogger(__name__)


def _make_controller_client():
    if settings.controller_mode == "rest":
        return RestControllerClient(settings.controller_base_url)
    return SimulatorControllerClient()


async def _scheduler_loop(stop_event: asyncio.Event) -> None:
    clock = SystemClock()
    client = _make_controller_client()

    while not stop_event.is_set():
        try:
            async with SessionLocal() as session:
                await scheduler_service.tick(session, clock)
        except Exception:
            logger.exception("scheduler tick failed")

        try:
            async with SessionLocal() as session:
                await controller_service.dispatch_pending(session, clock, client)
        except Exception:
            logger.exception("controller dispatch failed")

        try:
            async with SessionLocal() as session:
                await controller_service.poll_timeouts(session, clock)
        except Exception:
            logger.exception("controller timeout poll failed")

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=settings.scheduler_tick_seconds,
            )
        except asyncio.TimeoutError:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    client = _make_controller_client()
    async with SessionLocal() as session:
        await recovery_service.recover_all(session, SystemClock(), client)

    stop_event = asyncio.Event()
    task = asyncio.create_task(_scheduler_loop(stop_event))

    try:
        yield
    finally:
        stop_event.set()
        try:
            await task
        except Exception:
            logger.exception("background loop raised during shutdown")
        await engine.dispose()


app = FastAPI(
    title="Factory Traffic Management System",
    version="0.1.0",
    lifespan=lifespan,
)

# --- ADDED CORS MIDDLEWARE HERE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ---------------------------------

app.include_router(health_router)
app.include_router(junctions_router)
app.include_router(sensor_events_router)
app.include_router(commands_router)
app.include_router(controller_events_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "ftms", "docs": "/docs", "mode": settings.log_level}