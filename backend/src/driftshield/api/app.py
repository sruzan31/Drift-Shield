"""driftshield.api.app
======================
FastAPI application factory, lifespan management, and CORS configuration.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..run_manager import (
    IdempotencyConflictError,
    InvalidStateTransitionError,
    RunCapacityError,
    RunManager,
    RunNotFoundError,
)
from ..storage import SQLiteStorage
from .routes import get_run_manager, router
from .theory import theory_router
from .websocket import ws_router

logger = logging.getLogger("driftshield.api")


def create_app(
    storage: Optional[SQLiteStorage] = None,
    run_manager: Optional[RunManager] = None,
    output_dir: Path | str = "outputs",
) -> FastAPI:
    """
    Create and configure the DriftShield FastAPI application.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    shared_storage = storage or SQLiteStorage(
        db_path=out_dir / "driftshield.db",
        artifacts_dir=out_dir / "artifacts",
    )
    manager = run_manager or RunManager(storage=shared_storage, output_dir=out_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: mark unfinished runs and theory experiments as INTERRUPTED once
        logger.info("DriftShield API starting up. Running startup recovery checks...")
        manager.startup_recovery()
        shared_storage.startup_recovery_theory()
        yield
        # Shutdown
        logger.info("DriftShield API shutting down.")

    app = FastAPI(
        title="DriftShield API",
        description="Localhost control and historical query interface for DriftShield ML monitoring.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Explicit localhost CORS origins per Section 12
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost",
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:8000",
            "http://127.0.0.1",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8000",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # Dependency override
    app.dependency_overrides[get_run_manager] = lambda: manager

    # Mount routes
    app.include_router(router)
    app.include_router(ws_router)
    app.include_router(theory_router)

    # Error Handlers
    @app.exception_handler(RunNotFoundError)
    async def run_not_found_handler(request: Request, exc: RunNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "RunNotFound", "detail": str(exc)},
        )

    @app.exception_handler(RunCapacityError)
    async def run_capacity_handler(request: Request, exc: RunCapacityError):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": "RunCapacityExceeded", "detail": str(exc)},
        )

    @app.exception_handler(IdempotencyConflictError)
    async def idempotency_conflict_handler(request: Request, exc: IdempotencyConflictError):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": "IdempotencyConflict", "detail": str(exc)},
        )

    @app.exception_handler(InvalidStateTransitionError)
    async def invalid_transition_handler(request: Request, exc: InvalidStateTransitionError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "InvalidStateTransition", "detail": str(exc)},
        )

    return app


# Default app instance for running via `uvicorn driftshield.api.app:app`
app = create_app()
