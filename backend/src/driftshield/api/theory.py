"""driftshield.api.theory
========================
Theory Lab REST API endpoints and isolated background runner for DriftShield Phase 6B.

Supports:
- T4 Rare-Region Detection Experiment (idealized p, q, deadline D, delta guarantees)
- T5 Finite-Domain Exact Adaptation Experiment (N inputs, noiseless membership oracle)

Invariants:
- Bounded concurrency with worker thread pool isolated from the practical simulation engine.
- Workload and parameter limit validation before acceptance.
- Server-generated experiment IDs and durable SQLite persistence.
- Genuine execution status tracking (QUEUED, RUNNING, COMPLETED, FAILED, INTERRUPTED).
- Startup recovery marking unfinished runs as INTERRUPTED.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import logging
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Literal, Optional, Tuple, Union
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..storage import SQLiteStorage
from ..theory.finite_domain import (
    FiniteDomainConfig,
    FiniteDomainExperiment,
    ScenarioType,
)
from ..theory.rare_region import (
    RareRegionConfig,
    RareRegionExperiment,
)
from .routes import get_run_manager

logger = logging.getLogger("driftshield.api.theory")

theory_router = APIRouter(prefix="/api/theory", tags=["Theory Lab"])

# Workload and Capacity Constants
MAX_CONCURRENT_THEORY = 2
MAX_QUEUED_THEORY = 10
MAX_RARE_REGION_TRIALS = 100_000
MAX_RARE_REGION_DEADLINE = 100_000
MAX_RARE_REGION_WORKLOAD = 50_000_000  # trials * deadline
MAX_FINITE_DOMAIN_SIZE = 10_000


# =====================================================================
# Request & Response Schemas
# =====================================================================

class CreateRareRegionRequest(BaseModel):
    """Payload for launching a T4 Rare-Region detection experiment."""
    mode: Literal["rare-region"] = "rare-region"
    p: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="Disagreement mass / rare region size",
    )
    q: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
        description="Independent random label query probability per event",
    )
    deadline: int = Field(
        default=100,
        ge=0,
        le=MAX_RARE_REGION_DEADLINE,
        description="Observation deadline D in stream events",
    )
    delta: float = Field(
        default=0.05,
        gt=0.0,
        lt=1.0,
        description="Target miss probability delta",
    )
    trials: int = Field(
        default=10_000,
        ge=1,
        le=MAX_RARE_REGION_TRIALS,
        description="Number of independent trials",
    )
    seed: int = Field(
        default=42,
        description="Master seed for feature generation",
    )
    query_seed: Optional[int] = Field(
        default=None,
        description="Optional distinct seed for query RNG",
    )
    no_change: bool = Field(
        default=False,
        description="Run no-change baseline (f1 = f0) to verify zero false alarms",
    )

    @field_validator("trials")
    @classmethod
    def validate_workload(cls, v: int, info) -> int:
        deadline = info.data.get("deadline", 100)
        workload = v * deadline
        if workload > MAX_RARE_REGION_WORKLOAD:
            raise ValueError(
                f"Total workload (trials {v} * deadline {deadline} = {workload}) "
                f"exceeds maximum allowed limit of {MAX_RARE_REGION_WORKLOAD}."
            )
        return v


class CreateFiniteDomainRequest(BaseModel):
    """Payload for launching a T5 Finite-Domain exact adaptation experiment."""
    mode: Literal["finite-domain"] = "finite-domain"
    n_domain: int = Field(
        default=32,
        ge=1,
        le=MAX_FINITE_DOMAIN_SIZE,
        description="Finite domain size N (distinct inputs)",
    )
    scenario: ScenarioType = Field(
        default=ScenarioType.NO_CHANGE,
        description="Drift scenario: no-change, single-last, multiple, or custom",
    )
    changed_indices: Optional[List[int]] = Field(
        default=None,
        description="Explicit indices where f1(x) != f0(x). If None, determined by scenario.",
    )
    query_order: Optional[List[int]] = Field(
        default=None,
        description="Explicit permutation of domain indices to query.",
    )
    seed: int = Field(
        default=42,
        description="Random seed for randomized query order or scenario generation",
    )


CreateTheoryRequest = Union[CreateRareRegionRequest, CreateFiniteDomainRequest]


class TheoryExperimentSummary(BaseModel):
    """Summary of a Theory Lab experiment record."""
    model_config = ConfigDict(extra="ignore")

    experiment_id: str
    mode: str
    status: str
    seed: int
    config: Dict[str, Any]
    artifacts_dir: str
    summary_artifact_path: Optional[str] = None
    data_artifact_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: float
    updated_at: float
    completed_at: Optional[float] = None


class TheoryExperimentDetail(TheoryExperimentSummary):
    """Detailed theory experiment including full results dictionary."""
    results: Optional[Dict[str, Any]] = None


class PaginatedTheoryExperimentsResponse(BaseModel):
    """Paginated list of Theory Lab experiments."""
    items: List[TheoryExperimentSummary]
    total: int
    limit: int
    offset: int


# =====================================================================
# Isolated Theory Experiment Runner & Manager
# =====================================================================

class TheoryExperimentRunner:
    """
    Dedicated manager and worker pool for Theory Lab experiments.
    Isolates CPU-bound mathematical trials from the practical simulation engine.
    Bounds both concurrent worker execution and pending queue capacity.
    """

    def __init__(
        self,
        storage: SQLiteStorage,
        output_dir: Path | str = "outputs",
        max_workers: int = MAX_CONCURRENT_THEORY,
        max_queued: int = MAX_QUEUED_THEORY,
    ) -> None:
        self.storage = storage
        self.output_dir = Path(output_dir)
        self.theory_artifacts_dir = self.output_dir / "theory_artifacts"
        self.theory_artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.max_workers = max_workers
        self.max_queued = max_queued
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="theory-worker",
        )
        self._lock = threading.Lock()
        self._running_count = 0
        self._queued_count = 0

    def get_capacity_status(self) -> Dict[str, int]:
        with self._lock:
            return {
                "running": self._running_count,
                "queued": self._queued_count,
                "max_concurrent": self.max_workers,
                "max_queued": self.max_queued,
            }

    def enqueue_experiment(
        self,
        req: CreateTheoryRequest,
    ) -> TheoryExperimentSummary:
        """Validate capacity, generate ID, persist initial record, and submit to worker."""
        with self._lock:
            if self._queued_count >= self.max_queued:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Theory Lab execution capacity exceeded: "
                        f"pending queue is full ({self._queued_count}/{self.max_queued} pending, {self._running_count}/{self.max_workers} running). "
                        f"Please wait for current experiments to complete."
                    ),
                )
            self._queued_count += 1

        try:
            # Generate unique server ID
            suffix = uuid.uuid4().hex[:6]
            exp_id = f"exp-{req.mode[:4]}-{req.seed}-{suffix}"
            exp_artifacts_dir = self.theory_artifacts_dir / exp_id
            exp_artifacts_dir.mkdir(parents=True, exist_ok=True)

            config_dict = req.model_dump()

            record = self.storage.create_theory_experiment(
                experiment_id=exp_id,
                mode=req.mode,
                seed=req.seed,
                config_dict=config_dict,
                artifacts_dir=str(exp_artifacts_dir),
            )

            # Submit background task
            self.executor.submit(
                self._execute_worker,
                exp_id,
                req.mode,
                config_dict,
                exp_artifacts_dir,
            )

            return TheoryExperimentSummary(**record)
        except Exception:
            with self._lock:
                self._queued_count = max(0, self._queued_count - 1)
            raise

    def _execute_worker(
        self,
        experiment_id: str,
        mode: str,
        config_dict: Dict[str, Any],
        artifacts_dir: Path,
    ) -> None:
        """Worker thread executing the mathematical experiment."""
        with self._lock:
            self._queued_count = max(0, self._queued_count - 1)
            self._running_count += 1

        self.storage.update_theory_experiment_status(experiment_id, "RUNNING")
        logger.info("Theory experiment '%s' (%s) started execution.", experiment_id, mode)

        try:
            if mode == "rare-region":
                cfg = RareRegionConfig(**config_dict)
                exp = RareRegionExperiment(cfg)
                result = exp.run()
                csv_path, json_path = exp.export(result, artifacts_dir)
                results_dict = json.loads(json_path.read_text(encoding="utf-8"))
                # Include trial records count and high-level structure
                results_dict["result_type"] = "rare-region"
                results_dict["trials_count"] = result.trials_count
                results_dict["trials_sample"] = [
                    t.model_dump() for t in result.trials[:100]  # Store first 100 in SQLite
                ]

                self.storage.save_theory_experiment_results(
                    experiment_id=experiment_id,
                    results_dict=results_dict,
                    summary_artifact_path=str(json_path),
                    data_artifact_path=str(csv_path),
                )

            elif mode == "finite-domain":
                cfg = FiniteDomainConfig(**config_dict)
                exp = FiniteDomainExperiment(cfg)
                result = exp.run()
                csv_path, json_path = exp.export(result, artifacts_dir)
                results_dict = json.loads(json_path.read_text(encoding="utf-8"))
                results_dict["result_type"] = "finite-domain"
                results_dict["total_domain_size"] = result.total_domain_size
                results_dict["queries_completed"] = result.queries_completed
                results_dict["is_complete"] = result.is_complete
                results_dict["unique_label_cost"] = result.unique_label_cost
                results_dict["discovered_change_indices"] = result.discovered_change_indices
                results_dict["total_discovered_changes"] = result.total_discovered_changes
                results_dict["evaluator_true_changed_indices"] = result.evaluator_true_changed_indices
                results_dict["evaluator_all_labels_correct"] = result.evaluator_all_labels_correct
                results_dict["records"] = [r.model_dump() for r in result.records]

                self.storage.save_theory_experiment_results(
                    experiment_id=experiment_id,
                    results_dict=results_dict,
                    summary_artifact_path=str(json_path),
                    data_artifact_path=str(csv_path),
                )

            else:
                raise ValueError(f"Unknown theory mode: {mode}")

            logger.info("Theory experiment '%s' completed successfully.", experiment_id)

        except Exception as exc:
            logger.exception("Theory experiment '%s' failed: %s", experiment_id, exc)
            self.storage.update_theory_experiment_status(
                experiment_id=experiment_id,
                status="FAILED",
                error_message=str(exc),
            )
        finally:
            with self._lock:
                self._running_count = max(0, self._running_count - 1)


# Singleton runner holder
_theory_runner: Optional[TheoryExperimentRunner] = None


def get_theory_runner(
    run_manager=Depends(get_run_manager),
) -> TheoryExperimentRunner:
    """Dependency provider for TheoryExperimentRunner sharing storage."""
    global _theory_runner
    if _theory_runner is None or _theory_runner.storage != run_manager.storage:
        _theory_runner = TheoryExperimentRunner(
            storage=run_manager.storage,
            output_dir=run_manager.output_dir,
        )
    return _theory_runner


# =====================================================================
# REST Endpoints
# =====================================================================

@theory_router.post(
    "/experiments",
    response_model=TheoryExperimentSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_experiment(
    req: CreateTheoryRequest,
    runner: TheoryExperimentRunner = Depends(get_theory_runner),
) -> TheoryExperimentSummary:
    """
    Validate, enqueue, and launch a Theory Lab experiment.

    Accepts T4 Rare-Region (mode='rare-region') or T5 Finite-Domain (mode='finite-domain').
    """
    return runner.enqueue_experiment(req)


@theory_router.get(
    "/experiments",
    response_model=PaginatedTheoryExperimentsResponse,
)
def list_experiments(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    runner: TheoryExperimentRunner = Depends(get_theory_runner),
) -> PaginatedTheoryExperimentsResponse:
    """List historical Theory Lab experiments."""
    rows, total = runner.storage.list_theory_experiments(limit=limit, offset=offset)
    items = [TheoryExperimentSummary(**r) for r in rows]
    return PaginatedTheoryExperimentsResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@theory_router.get(
    "/experiments/{experiment_id}",
    response_model=TheoryExperimentDetail,
)
def get_experiment(
    experiment_id: str,
    runner: TheoryExperimentRunner = Depends(get_theory_runner),
) -> TheoryExperimentDetail:
    """Retrieve metadata, parameters, and current status of a Theory Lab experiment."""
    rec = runner.storage.get_theory_experiment(experiment_id)
    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Theory experiment '{experiment_id}' not found.",
        )
    return TheoryExperimentDetail(**rec)


@theory_router.get(
    "/experiments/{experiment_id}/results",
)
def get_experiment_results(
    experiment_id: str,
    runner: TheoryExperimentRunner = Depends(get_theory_runner),
) -> Dict[str, Any]:
    """Retrieve consolidated theoretical and empirical results for a completed experiment."""
    rec = runner.storage.get_theory_experiment(experiment_id)
    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Theory experiment '{experiment_id}' not found.",
        )
    if rec["status"] != "COMPLETED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Experiment '{experiment_id}' is in '{rec['status']}' state. Results unavailable.",
        )
    return rec.get("results") or {}


@theory_router.get(
    "/experiments/{experiment_id}/export",
)
def export_experiment(
    experiment_id: str,
    format: Literal["json", "csv"] = Query(default="json"),
    runner: TheoryExperimentRunner = Depends(get_theory_runner),
):
    """
    Download durable artifacts (summary JSON or trials/audit CSV) for a completed experiment.
    """
    rec = runner.storage.get_theory_experiment(experiment_id)
    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Theory experiment '{experiment_id}' not found.",
        )
    if rec["status"] != "COMPLETED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Experiment '{experiment_id}' is in '{rec['status']}' state. Export unavailable.",
        )

    if format == "json":
        path = rec.get("summary_artifact_path")
        if not path or not Path(path).exists():
            return JSONResponse(content=rec.get("results") or {})
        return FileResponse(
            path=path,
            media_type="application/json",
            filename=f"{experiment_id}_summary.json",
        )
    else:  # csv
        path = rec.get("data_artifact_path")
        if not path or not Path(path).exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Data artifact CSV not found on disk for '{experiment_id}'.",
            )
        filename = (
            f"{experiment_id}_trials.csv"
            if rec["mode"] == "rare-region"
            else f"{experiment_id}_audit_records.csv"
        )
        return FileResponse(
            path=path,
            media_type="text/csv",
            filename=filename,
        )
