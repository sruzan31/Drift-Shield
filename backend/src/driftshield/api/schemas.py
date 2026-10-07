"""driftshield.api.schemas
=========================
Pydantic API schemas for DriftShield REST control and query endpoints.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CreateRunRequest(BaseModel):
    """Payload for creating and persisting a new simulation run."""
    scenario: str = Field(
        default="stationary",
        description="Stream scenario: 'stationary', 'abrupt', 'gradual', 'recurring', 'rare_region', or 'adversary'.",
    )
    n_events: int = Field(
        default=2000,
        ge=10,
        le=100000,
        description="Total number of events in the stream.",
    )
    warmup_size: int = Field(
        default=200,
        ge=1,
        description="Number of warm-up events before initial model freeze.",
    )
    label_budget: int = Field(
        default=300,
        ge=0,
        description="Maximum budget for post-warmup label acquisitions.",
    )
    label_delay: int = Field(
        default=0,
        ge=0,
        description="Fixed logical event delay before label delivery.",
    )
    seed: int = Field(
        default=42,
        description="RNG seed for deterministic stream generation.",
    )
    drift_start_sequence: Optional[int] = Field(
        default=None,
        description="Sequence index where drift begins (defaults to n_events // 2).",
    )
    gradual_window: Optional[int] = Field(
        default=None,
        ge=10,
        description="Length of transition window for gradual drift.",
    )
    recurrence_interval: Optional[int] = Field(
        default=None,
        ge=10,
        description="Event period between recurring concept switches.",
    )
    rare_region_p: Optional[float] = Field(
        default=None,
        gt=0.0,
        le=0.5,
        description="Fraction of feature space affected by rare-region stealth drift.",
    )
    adversary_dwell: Optional[int] = Field(
        default=None,
        ge=50,
        description="Dwell interval in events between adversary rule switches.",
    )
    adwin_delta: float = Field(
        default=0.002,
        gt=0.0,
        lt=1.0,
        description="ADWIN delta confidence parameter.",
    )
    target_training_labels: int = Field(
        default=200,
        ge=5,
        description="Target unique post-epoch labels to train a candidate.",
    )
    evaluation_target_events: int = Field(
        default=500,
        ge=5,
        description="Target fresh random-monitoring comparison events.",
    )
    events_per_second: float = Field(
        default=100.0,
        ge=0.1,
        le=5000.0,
        description="Monotonic clock pacing speed for the simulation.",
    )
    run_id: Optional[str] = Field(
        default=None,
        description="Optional custom run identifier. If omitted, server generates one.",
    )
    parent_run_id: Optional[str] = Field(
        default=None,
        description="Optional parent run identifier for explicit replay lineage.",
    )
    idempotency_key: Optional[str] = Field(
        default=None,
        description="Optional client idempotency key to prevent duplicate creation.",
    )


class ControlRequest(BaseModel):
    """Payload for executing a lifecycle control action on a run."""
    action: str = Field(
        ...,
        description="Control action to perform: 'start', 'pause', 'resume', or 'stop'.",
    )
    events_per_second: Optional[float] = Field(
        default=None,
        ge=0.1,
        le=5000.0,
        description="Optional speed adjustment for start/resume.",
    )


class ControlResponse(BaseModel):
    """Response returned from a lifecycle control action."""
    run_id: str
    action: str
    previous_state: str
    current_state: str
    message: str


class LabelAccountingResponse(BaseModel):
    """Accurate physical label acquisitions and budget debits."""
    warmup_acquisitions: int
    monitor_acquisitions: int
    selective_acquisitions: int
    post_warmup_acquisitions: int
    total_unique_acquisitions: int
    budget_debits: int


class RunSummaryResponse(BaseModel):
    """High-level summary of a run in history listing."""
    run_id: str
    parent_run_id: Optional[str] = None
    scenario: str
    seed: int
    mode: str
    state: str
    created_at: float
    updated_at: float
    completed_at: Optional[float] = None
    config: Optional[Dict[str, Any]] = None


class ClassificationMetricResponse(BaseModel):
    """Consistent classification error metric structure."""
    sample_count: int = Field(..., description="Number of evaluated observations.")
    correct_count: int = Field(..., description="Evaluated correct predictions.")
    incorrect_count: int = Field(..., description="Evaluated incorrect predictions.")
    denominator: int = Field(..., description="Population used to calculate the metric.")
    error_rate: Optional[float] = Field(None, description="incorrect_count / denominator, or null if empty.")


class RunDetailResponse(BaseModel):
    """Comprehensive state and history snapshot for a single run."""
    run_id: str
    parent_run_id: Optional[str] = None
    scenario: str
    seed: int
    mode: str
    schema_version: str
    state: str
    operational_state: str
    candidate_state: Optional[str] = Field("NONE", description="Active candidate lifecycle state: TRAINING, READY_FOR_EVALUATION, EVALUATING, PROMOTED, REJECTED, INCOMPLETE, or NONE.")
    active_model_version: str
    events_processed: int
    total_events: int
    progress_percent: float
    monitoring_coverage: float = 0.0
    synthetic_data: bool = True
    created_at: float
    updated_at: float
    completed_at: Optional[float] = None
    config: Dict[str, Any]
    environment: Dict[str, Any]
    label_accounting: Dict[str, Any]
    monitoring_summary: Optional[Dict[str, Any]] = None
    candidate_summary: Optional[Dict[str, Any]] = None
    paired_summary: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, ClassificationMetricResponse]] = None


class WebSocketSnapshotMessage(BaseModel):
    """Real-time point-in-time snapshot sent over WS /api/runs/{run_id}/live."""
    run_id: str
    schema_version: str = "v1.0"
    snapshot_sequence: int = Field(..., description="Monotonically increasing snapshot counter.")
    operational_state: str = Field(..., description="Engine state: INITIALIZING, WARMUP, RUNNING, PAUSED, COMPLETED, STOPPED, INTERRUPTED.")
    candidate_state: Optional[str] = Field(None, description="Active candidate lifecycle state: TRAINING, READY_FOR_EVALUATION, EVALUATING, PROMOTED, REJECTED, INCOMPLETE, or NONE.")
    events_processed: int
    total_events: int
    progress_percent: float
    active_model_version: str
    monitoring_coverage: float
    label_accounting: Dict[str, Any]
    metrics: Optional[Dict[str, ClassificationMetricResponse]] = None
    monitoring_summary: Optional[Dict[str, Any]] = None
    candidate_summary: Optional[Dict[str, Any]] = None
    paired_summary: Optional[Dict[str, Any]] = None
    synthetic_data: bool = True
    timestamp: float


class PaginatedRunsResponse(BaseModel):
    """Paginated list of historical runs."""
    items: List[RunSummaryResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class IncidentItemResponse(BaseModel):
    """Single incident record."""
    incident_id: str
    run_id: str
    alert_type: str
    event_id: str
    event_sequence: int
    arrival_sequence: int
    detection_delay: int
    model_version: str
    candidate_id: Optional[str] = None
    outcome: Optional[str] = None
    evidence: Dict[str, Any]
    created_at: float


class PaginatedIncidentsResponse(BaseModel):
    """Paginated list of incidents for a run."""
    run_id: str
    items: List[IncidentItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class PredictionSubRecord(BaseModel):
    """Recorded prediction details."""
    prediction_id: int
    model_version: str
    predicted_label: int
    predicted_proba: float
    latency_ms: float
    created_at: float


class EventPredictionResponse(BaseModel):
    """Event details and original locked-in prediction."""
    run_id: str
    event_id: str
    sequence: int
    timestamp: float
    received_at: float
    features: Dict[str, float]
    is_synthetic: bool
    processing_status: str
    prediction: Optional[PredictionSubRecord] = None


class HealthResponse(BaseModel):
    """Process liveness and database readiness."""
    status: str = "ok"
    storage_ready: bool = True
    active_run_id: Optional[str] = None
    timestamp: float
