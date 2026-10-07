"""driftshield.api.routes
========================
FastAPI route definitions for DriftShield simulation controls and historical queries.
"""

from __future__ import annotations

import math
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..config import (
    AdaptationConfig,
    DriftShieldConfig,
    LabelConfig,
    MonitoringConfig,
    StreamConfig,
)
from ..run_manager import (
    IdempotencyConflictError,
    InvalidStateTransitionError,
    RunCapacityError,
    RunManager,
    RunNotFoundError,
)
from .schemas import (
    ControlRequest,
    ControlResponse,
    CreateRunRequest,
    EventPredictionResponse,
    HealthResponse,
    IncidentItemResponse,
    PaginatedIncidentsResponse,
    PaginatedRunsResponse,
    PredictionSubRecord,
    RunDetailResponse,
    RunSummaryResponse,
)

router = APIRouter()


def get_run_manager() -> RunManager:
    """Dependency placeholder; overridden by create_app dependency injection."""
    raise NotImplementedError("RunManager dependency not provided.")


# ---------------------------------------------------------------------------
# Health & Readiness
# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse)
@router.get("/ready", response_model=HealthResponse)
@router.get("/api/health", response_model=HealthResponse)
@router.get("/api/ready", response_model=HealthResponse)
def health_check(
    run_manager: RunManager = Depends(get_run_manager),
) -> HealthResponse:
    """Liveness and persistence readiness check."""
    try:
        # Verify storage connection
        conn = run_manager.storage._get_connection()
        conn.execute("SELECT 1;")
        storage_ok = True
    except Exception:
        storage_ok = False

    return HealthResponse(
        status="ok" if storage_ok else "degraded",
        storage_ready=storage_ok,
        active_run_id=run_manager._active_run_id,
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# Run Lifecycle & History
# ---------------------------------------------------------------------------


@router.post(
    "/api/runs",
    response_model=RunSummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_run(
    req: CreateRunRequest,
    run_manager: RunManager = Depends(get_run_manager),
) -> RunSummaryResponse:
    """
    Validate and persist a run configuration into durable SQLite storage.

    Supports creation idempotency via `idempotency_key`.
    """
    drift_start = (
        req.drift_start_sequence
        if req.drift_start_sequence is not None
        else req.n_events // 2
    )

    stream_kwargs = {
        "scenario": req.scenario,
        "n_events": req.n_events,
        "seed": req.seed,
        "drift_start_sequence": drift_start,
    }
    if req.gradual_window is not None:
        stream_kwargs["gradual_window"] = req.gradual_window
    if req.recurrence_interval is not None:
        stream_kwargs["recurrence_interval"] = req.recurrence_interval
    if req.rare_region_p is not None:
        stream_kwargs["rare_region_p"] = req.rare_region_p
    if req.adversary_dwell is not None:
        stream_kwargs["adversary_dwell"] = req.adversary_dwell

    cfg = DriftShieldConfig(
        stream=StreamConfig(**stream_kwargs),
        labels=LabelConfig(
            warmup_size=req.warmup_size,
            label_budget=req.label_budget,
            label_delay=req.label_delay,
        ),
        monitoring=MonitoringConfig(
            adwin_delta=req.adwin_delta,
        ),
        adaptation=AdaptationConfig(
            target_training_labels=req.target_training_labels,
            evaluation_target_events=req.evaluation_target_events,
        ),
        output_dir=str(run_manager.output_dir),
    )

    try:
        run_record = run_manager.create_run(
            config=cfg,
            run_id=req.run_id,
            parent_run_id=req.parent_run_id,
            idempotency_key=req.idempotency_key,
            events_per_second=req.events_per_second,
        )
        return RunSummaryResponse(**run_record)
    except IdempotencyConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Storage failure while creating run: {e}",
        )


@router.get(
    "/api/runs",
    response_model=PaginatedRunsResponse,
)
def list_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    run_manager: RunManager = Depends(get_run_manager),
) -> PaginatedRunsResponse:
    """Retrieve paginated historical simulation runs."""
    runs, total = run_manager.list_runs(page=page, page_size=page_size)
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    items = [RunSummaryResponse(**r) for r in runs]
    return PaginatedRunsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/api/runs/{run_id}",
    response_model=RunDetailResponse,
)
def get_run(
    run_id: str,
    run_manager: RunManager = Depends(get_run_manager),
) -> RunDetailResponse:
    """Retrieve full current state, progress, and metric aggregates for a run."""
    try:
        detail = run_manager.get_run_detail(run_id)
        return RunDetailResponse(**detail)
    except RunNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/api/runs/{run_id}/control",
    response_model=ControlResponse,
)
def control_run(
    run_id: str,
    req: ControlRequest,
    run_manager: RunManager = Depends(get_run_manager),
) -> ControlResponse:
    """
    Execute lifecycle controls on a run: start, pause, resume, or stop.
    """
    try:
        res = run_manager.control_run(
            run_id=run_id,
            action=req.action,
            events_per_second=req.events_per_second,
        )
        return ControlResponse(**res)
    except RunNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RunCapacityError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Control execution failure: {e}",
        )


@router.get(
    "/api/runs/{run_id}/incidents",
    response_model=PaginatedIncidentsResponse,
)
def list_incidents(
    run_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    run_manager: RunManager = Depends(get_run_manager),
) -> PaginatedIncidentsResponse:
    """Retrieve paginated incidents, drift alerts, and candidate decisions for a run."""
    try:
        incidents, total = run_manager.list_incidents(
            run_id=run_id, page=page, page_size=page_size
        )
        total_pages = math.ceil(total / page_size) if total > 0 else 1
        items = [IncidentItemResponse(**i) for i in incidents]
        return PaginatedIncidentsResponse(
            run_id=run_id,
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
    except RunNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/api/runs/{run_id}/events/{event_id}",
    response_model=EventPredictionResponse,
)
def get_event_prediction(
    run_id: str,
    event_id: str,
    run_manager: RunManager = Depends(get_run_manager),
) -> EventPredictionResponse:
    """Retrieve an ingested event with its original recorded model prediction."""
    try:
        rec = run_manager.get_event_prediction(run_id=run_id, event_id=event_id)
        pred = None
        if rec.get("prediction_id") is not None:
            pred = PredictionSubRecord(
                prediction_id=rec["prediction_id"],
                model_version=rec["model_version"],
                predicted_label=rec["predicted_label"],
                predicted_proba=rec["predicted_proba"],
                latency_ms=rec["latency_ms"],
                created_at=rec["prediction_created_at"],
            )

        return EventPredictionResponse(
            run_id=rec["run_id"],
            event_id=rec["event_id"],
            sequence=rec["sequence"],
            timestamp=rec["timestamp"],
            received_at=rec["received_at"],
            features=rec["features"],
            is_synthetic=bool(rec["is_synthetic"]),
            processing_status=rec["processing_status"],
            prediction=pred,
        )
    except RunNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
