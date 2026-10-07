"""driftshield.run_manager
==========================
Run orchestration and concurrency management for DriftShield.

Runs execution loops outside FastAPI's asynchronous event loop in dedicated
background threads. Enforces single-run mutable ownership, bounded capacity,
deterministic pacing via monotonic clock, clean pause/resume/stop lifecycles,
and startup recovery.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

from .config import DriftShieldConfig, LabelConfig, StreamConfig
from .contracts import CandidateState, EvaluationDecision, StreamEvent
from .engine import DriftShieldEngine, EngineSnapshot, EngineSummary, get_execution_environment
from .simulator import Simulator
from .storage import SQLiteStorage

logger = logging.getLogger("driftshield.run_manager")


class RunManagerError(Exception):
    """Base exception for run manager errors."""
    pass


class RunNotFoundError(RunManagerError):
    """Raised when a requested run_id is not found."""
    pass


class RunCapacityError(RunManagerError):
    """Raised when attempting to run concurrent simulations beyond capacity."""
    pass


class InvalidStateTransitionError(RunManagerError):
    """Raised when an invalid lifecycle control action is requested."""
    pass


class IdempotencyConflictError(RunManagerError):
    """Raised when an idempotency key is reused with conflicting configuration."""
    pass


class RunWorker:
    """
    Dedicated worker thread for executing a single stream simulation.
    """

    def __init__(
        self,
        engine: DriftShieldEngine,
        simulator: Simulator,
        events_per_second: float = 100.0,
        on_complete_callback: Optional[Any] = None,
    ) -> None:
        self.engine = engine
        self.simulator = simulator
        self.events_per_second = max(0.1, events_per_second)
        self.on_complete_callback = on_complete_callback

        self._thread: Optional[threading.Thread] = None
        self._stop_requested = threading.Event()
        self._pause_requested = threading.Event()
        self._step_lock = threading.Lock()
        self._exception: Optional[Exception] = None

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self._thread is not None:
            raise InvalidStateTransitionError("Run worker already started.")
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"Worker-{self.engine.run_id}",
            daemon=True,
        )
        self._thread.start()

    def pause(self) -> None:
        self._pause_requested.set()

    def resume(self) -> None:
        self._pause_requested.clear()

    def stop(self) -> None:
        self._stop_requested.set()
        # In case it is paused, unpause so loop can exit
        self._pause_requested.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

    def _run_loop(self) -> None:
        """Main execution thread loop."""
        try:
            events = self.simulator.events
            total_events = len(events)
            current_idx = self.engine.events_processed_count

            while current_idx < total_events and not self._stop_requested.is_set():
                # Handle pause
                while self._pause_requested.is_set() and not self._stop_requested.is_set():
                    time.sleep(0.05)

                if self._stop_requested.is_set():
                    break

                t_step_start = time.monotonic()
                event = events[current_idx]

                with self._step_lock:
                    self.engine.process_event(event)

                current_idx += 1

                # Deterministic pacing via monotonic clock
                if self.events_per_second > 0:
                    target_delay = 1.0 / self.events_per_second
                    elapsed = time.monotonic() - t_step_start
                    sleep_time = target_delay - elapsed
                    if sleep_time > 0:
                        time.sleep(sleep_time)

            # Execution loop finished
            with self._step_lock:
                if self._stop_requested.is_set():
                    self._handle_stop()
                else:
                    self.engine.finalize()

        except Exception as e:
            logger.exception("Error in run worker execution loop for run '%s'", self.engine.run_id)
            self._exception = e
            self.engine.state = "INTERRUPTED"
            self.engine.storage.update_run_state(self.engine.run_id, "INTERRUPTED", completed=True)
        finally:
            if self.on_complete_callback:
                self.on_complete_callback(self.engine.run_id)

    def _handle_stop(self) -> None:
        """Explicit stop policy: drain up to current sequence, finalize candidate as INCOMPLETE."""
        last_seq = (
            max(ev.sequence for ev in self.engine._processed_events.values())
            if self.engine._processed_events
            else 0
        )
        self.engine.drain_pending_labels(last_seq)
        self.engine.paired_evaluator.finalize(last_seq)
        self.engine.candidate_manager.finalize(last_seq)

        if self.engine.candidate_manager.active_candidate is not None:
            ac = self.engine.candidate_manager.active_candidate
            if ac.alert_id and ac.state == CandidateState.INCOMPLETE:
                self.engine.storage.update_incident_outcome(
                    run_id=self.engine.run_id,
                    incident_id=ac.alert_id,
                    outcome="INCOMPLETE",
                    candidate_id=ac.candidate_id,
                    extra_evidence={
                        "candidate_state": "INCOMPLETE",
                        "unique_training_labels": ac.unique_training_labels,
                        "target_training_labels": ac.target_training_labels,
                        "stopped_at_sequence": last_seq,
                    },
                )

        # Record metric windows up to stopped sequence
        if self.engine.evaluator is not None and self.engine.acquirer is not None:
            metrics = self.engine.evaluator.compute_metrics(
                label_acquisition=self.engine.acquirer.get_channel_stats(),
                evaluation_start_sequence=self.engine.evaluation_start_sequence,
                alerts=self.engine.monitor.alerts,
            )
            if metrics.full_synthetic is not None:
                self.engine.storage.record_metric_window(
                    run_id=self.engine.run_id,
                    start_sequence=self.engine.evaluation_start_sequence,
                    end_sequence=last_seq,
                    window_type="full_synthetic",
                    method="evaluation",
                    metric_name="error_rate",
                    metric_value=metrics.full_synthetic.error_rate,
                    sample_count=metrics.full_synthetic.total,
                    correct_count=metrics.full_synthetic.correct,
                    incorrect_count=metrics.full_synthetic.total - metrics.full_synthetic.correct,
                    denominator=metrics.full_synthetic.total,
                )
            if metrics.monitor_channel is not None:
                self.engine.storage.record_metric_window(
                    run_id=self.engine.run_id,
                    start_sequence=self.engine.evaluation_start_sequence,
                    end_sequence=last_seq,
                    window_type="random_monitoring",
                    method="monitoring",
                    metric_name="error_rate",
                    metric_value=metrics.monitor_channel.error_rate,
                    sample_count=metrics.monitor_channel.total,
                    correct_count=metrics.monitor_channel.correct,
                    incorrect_count=metrics.monitor_channel.total - metrics.monitor_channel.correct,
                    denominator=metrics.monitor_channel.total,
                )

        self.engine.state = "STOPPED"
        self.engine.storage.update_run_state(self.engine.run_id, "STOPPED", completed=True)


class RunManager:
    """
    Manages lifecycle, workers, capacity limits, and storage queries for runs.
    """

    def __init__(
        self,
        storage: Optional[SQLiteStorage] = None,
        output_dir: Path | str = "outputs",
        default_events_per_second: float = 100.0,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.storage = storage or SQLiteStorage(
            db_path=self.output_dir / "driftshield.db",
            artifacts_dir=self.output_dir / "artifacts",
        )
        self.default_events_per_second = default_events_per_second

        self._active_run_id: Optional[str] = None
        self._workers: Dict[str, RunWorker] = {}
        self._engines: Dict[str, DriftShieldEngine] = {}
        self._idempotency_map: Dict[str, Tuple[str, Dict[str, Any]]] = {}  # key -> (run_id, config_dict)
        self._lock = threading.Lock()

    def startup_recovery(self) -> None:
        """Mark any unfinished runs as INTERRUPTED once at startup."""
        conn = self.storage._get_connection()
        with conn:
            conn.execute(
                """
                UPDATE runs
                SET state = 'INTERRUPTED', updated_at = ?
                WHERE state IN ('INITIALIZING', 'WARMUP', 'RUNNING', 'PAUSED');
                """,
                (time.time(),),
            )

    def create_run(
        self,
        config: DriftShieldConfig,
        run_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        events_per_second: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Validate and persist a new run configuration.

        Supports creation idempotency:
        - Identical retry with same key returns the existing run.
        - Conflicting retry with same key raises IdempotencyConflictError (409).
        """
        with self._lock:
            cfg_dict = config.model_dump()
            if idempotency_key:
                if idempotency_key in self._idempotency_map:
                    existing_run_id, existing_cfg = self._idempotency_map[idempotency_key]
                    if existing_cfg == cfg_dict:
                        existing_run = self.storage.get_run(existing_run_id)
                        if existing_run:
                            return existing_run
                    raise IdempotencyConflictError(
                        f"Idempotency key '{idempotency_key}' was already used with different configuration."
                    )

            # Generate unique run ID if not explicitly specified
            if run_id is None:
                base_id = f"run-{config.stream.scenario}-{config.stream.seed}"
                if self.storage.get_run(base_id) is not None:
                    gen_run_id = f"{base_id}-replay-{uuid.uuid4().hex[:6]}"
                    if parent_run_id is None:
                        parent_run_id = base_id
                else:
                    gen_run_id = base_id
            else:
                gen_run_id = run_id
                if self.storage.get_run(gen_run_id) is not None:
                    raise IdempotencyConflictError(
                        f"Run '{gen_run_id}' already exists in database."
                    )

            engine = DriftShieldEngine(
                config=config,
                run_id=gen_run_id,
                parent_run_id=parent_run_id,
                storage=self.storage,
            )
            sim = Simulator(config=config.stream, label_delay=config.labels.label_delay)
            engine.initialize(simulator=sim)

            speed = events_per_second if events_per_second is not None else self.default_events_per_second
            worker = RunWorker(
                engine=engine,
                simulator=sim,
                events_per_second=speed,
                on_complete_callback=self._on_worker_completed,
            )

            self._engines[gen_run_id] = engine
            self._workers[gen_run_id] = worker

            if idempotency_key:
                self._idempotency_map[idempotency_key] = (gen_run_id, cfg_dict)

            run_record = self.storage.get_run(gen_run_id)
            if run_record is None:
                raise RunManagerError(f"Failed to persist run '{gen_run_id}' to SQLite database.")
            return run_record

    def control_run(
        self,
        run_id: str,
        action: str,
        events_per_second: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Execute lifecycle control on a run: start, pause, resume, stop.
        """
        with self._lock:
            run_rec = self.storage.get_run(run_id)
            if run_rec is None:
                raise RunNotFoundError(f"Run '{run_id}' not found.")

            current_db_state = run_rec["state"]
            worker = self._workers.get(run_id)
            engine = self._engines.get(run_id)

            action = action.lower().strip()

            if action == "start":
                if current_db_state not in ("INITIALIZING", "WARMUP"):
                    raise InvalidStateTransitionError(
                        f"Cannot start run '{run_id}' from state '{current_db_state}'."
                    )
                if self._active_run_id is not None and self._active_run_id != run_id:
                    active_worker = self._workers.get(self._active_run_id)
                    if active_worker and active_worker.is_alive:
                        raise RunCapacityError(
                            f"Active run '{self._active_run_id}' is currently running. "
                            "Capacity limit is 1 active run."
                        )

                if events_per_second is not None:
                    worker.events_per_second = max(0.1, events_per_second)

                self._active_run_id = run_id
                worker.start()
                new_state = "RUNNING"
                msg = "Run execution started."

            elif action == "pause":
                if current_db_state not in ("WARMUP", "RUNNING") or worker is None or not worker.is_alive:
                    raise InvalidStateTransitionError(
                        f"Cannot pause run '{run_id}' in state '{current_db_state}'."
                    )
                worker.pause()
                engine.state = "PAUSED"
                self.storage.update_run_state(run_id, "PAUSED")
                new_state = "PAUSED"
                msg = "Run execution paused cleanly between stream steps."

            elif action == "resume":
                if current_db_state != "PAUSED" or worker is None:
                    raise InvalidStateTransitionError(
                        f"Cannot resume run '{run_id}' in state '{current_db_state}'."
                    )
                if events_per_second is not None:
                    worker.events_per_second = max(0.1, events_per_second)
                worker.resume()
                engine.state = "RUNNING"
                self.storage.update_run_state(run_id, "RUNNING")
                new_state = "RUNNING"
                msg = "Run execution resumed."

            elif action == "stop":
                if current_db_state in ("COMPLETED", "STOPPED", "INTERRUPTED"):
                    raise InvalidStateTransitionError(
                        f"Run '{run_id}' is already in terminal state '{current_db_state}'."
                    )
                if worker is not None and worker.is_alive:
                    worker.stop()
                else:
                    if engine is not None:
                        engine.finalize()
                    self.storage.update_run_state(run_id, "STOPPED", completed=True)

                if self._active_run_id == run_id:
                    self._active_run_id = None
                new_state = "STOPPED"
                msg = "Run stopped; pending labels drained and candidate finalized as incomplete."

            else:
                raise InvalidStateTransitionError(f"Unknown control action '{action}'.")

            return {
                "run_id": run_id,
                "action": action,
                "previous_state": current_db_state,
                "current_state": new_state,
                "message": msg,
            }

    def _on_worker_completed(self, run_id: str) -> None:
        """Callback when worker thread exits."""
        with self._lock:
            if self._active_run_id == run_id:
                self._active_run_id = None

    def get_run_detail(self, run_id: str) -> Dict[str, Any]:
        """
        Get comprehensive run detail, merging live engine snapshot with stored history.
        """
        run_rec = self.storage.get_run(run_id)
        if run_rec is None:
            raise RunNotFoundError(f"Run '{run_id}' not found.")

        engine = self._engines.get(run_id)
        cfg = run_rec["config"]
        n_events = cfg.get("stream", {}).get("n_events", 2000)

        # Label accounting
        label_acct = self.storage.get_label_accounting(run_id)

        cand_state = "NONE"
        if engine is not None and run_rec["state"] in ("WARMUP", "RUNNING", "PAUSED"):
            snap = engine.get_snapshot()
            events_proc = snap.events_processed
            active_model_v = snap.active_model_version
            op_state = snap.state
            mon_cov = snap.monitoring_coverage
            cand_summary = engine.candidate_manager.get_summary()
            paired_summary = engine.paired_evaluator.get_summary()
            mon_summary = engine.monitor.get_summary()
            ac = engine.candidate_manager.active_candidate
            cand_state = ac.state.value if ac is not None else "NONE"
            metrics = None
        else:
            # Stored run detail
            events = self.storage.get_events(run_id)
            events_proc = len(events)
            model_versions = self.storage.get_model_versions(run_id)
            active_model_v = (
                model_versions[-1]["version_tag"] if model_versions else "v1.0-frozen"
            )
            op_state = run_rec["state"]
            metric_windows = self.storage.get_metric_windows(run_id)
            incidents = self.storage.get_incidents(run_id)

            # Reconstruct summaries from incidents
            candidates_list = []
            sessions_list = []
            for inc in incidents:
                c_id = inc.get("candidate_id")
                ev = inc.get("evidence") or {}
                outcome = inc.get("outcome") or "NONE"
                if c_id:
                    c_state = ev.get("candidate_state") or outcome
                    uniq_lbls = ev.get("unique_training_labels", 0)
                    tgt_lbls = ev.get("target_training_labels", cfg.get("adaptation", {}).get("target_training_labels", 200))
                    prog = round((uniq_lbls / tgt_lbls) * 100.0, 1) if tgt_lbls > 0 else 0.0
                    candidates_list.append({
                        "candidate_id": c_id,
                        "target_version": ev.get("promoted_model_version") or f"cand-{c_id}",
                        "state": c_state,
                        "unique_training_labels": uniq_lbls,
                        "target_training_labels": tgt_lbls,
                        "progress_percent": prog,
                        "epoch": inc.get("event_sequence", 0),
                        "freeze_sequence": ev.get("freeze_sequence"),
                    })
                    if outcome in ("PROMOTED", "REJECTED"):
                        sessions_list.append({
                            "eval_id": ev.get("eval_id") or f"eval-{c_id}",
                            "candidate_id": c_id,
                            "candidate_version": ev.get("promoted_model_version") or f"cand-{c_id}",
                            "decision": outcome,
                            "gain": ev.get("gain"),
                            "p_value": ev.get("p_value"),
                            "b": ev.get("b", 0),
                            "c": ev.get("c", 0),
                            "n": ev.get("n", 0),
                            "delivered_labels_count": ev.get("n", 0),
                            "target_events_count": cfg.get("adaptation", {}).get("evaluation_target_events", 500),
                            "progress_percent": 100.0 if ev.get("n") else 0.0,
                        })

            if candidates_list:
                cand_state = candidates_list[-1]["state"]
            elif incidents:
                cand_state = incidents[-1].get("outcome") or "NONE"
            else:
                cand_state = "NONE"

            mon_summary = {
                "alerts_count": len(incidents),
                "alerts": [
                    {
                        "alert_id": inc["incident_id"],
                        "arrival_sequence": inc["arrival_sequence"],
                        "description": inc["alert_type"],
                        "outcome": inc["outcome"],
                    }
                    for inc in incidents
                ],
            }
            cand_summary = {
                "total_candidates_spawned": len(candidates_list),
                "candidates": candidates_list,
            }
            paired_summary = {
                "completed_comparisons_count": len(sessions_list),
                "sessions": sessions_list,
            }

            warmup_size = cfg.get("labels", {}).get("warmup_size", 200)
            eval_events = max(0, events_proc - warmup_size)
            mon_acq = label_acct.get("monitor_acquisitions", 0)
            mon_cov = (mon_acq / eval_events) if eval_events > 0 else 0.0

            if metric_windows:
                metrics = {}
                for w in metric_windows:
                    w_type = w["window_type"]
                    sample_cnt = w["sample_count"]
                    denom = w["denominator"]
                    err_rate = w["metric_value"]
                    if "correct_count" in w.keys():
                        corr_cnt = w["correct_count"]
                        incorr_cnt = w["incorrect_count"]
                    else:
                        corr_cnt = denom - int(round(err_rate * denom)) if (err_rate is not None and denom > 0) else 0
                        incorr_cnt = denom - corr_cnt if denom > 0 else 0
                    metrics[w_type] = {
                        "sample_count": sample_cnt,
                        "correct_count": corr_cnt,
                        "incorrect_count": incorr_cnt,
                        "denominator": denom,
                        "error_rate": err_rate,
                    }
            else:
                metrics = None

        progress_pct = (events_proc / n_events) * 100.0 if n_events > 0 else 0.0

        return {
            "run_id": run_rec["run_id"],
            "parent_run_id": run_rec.get("parent_run_id"),
            "scenario": run_rec["scenario"],
            "seed": run_rec["seed"],
            "mode": run_rec["mode"],
            "schema_version": run_rec["schema_version"],
            "state": run_rec["state"],
            "operational_state": op_state,
            "candidate_state": cand_state,
            "active_model_version": active_model_v,
            "events_processed": events_proc,
            "total_events": n_events,
            "progress_percent": round(progress_pct, 2),
            "monitoring_coverage": round(mon_cov, 4),
            "created_at": run_rec["created_at"],
            "updated_at": run_rec["updated_at"],
            "completed_at": run_rec.get("completed_at"),
            "config": run_rec["config"],
            "environment": run_rec["environment"],
            "synthetic_data": True,
            "label_accounting": label_acct,
            "monitoring_summary": mon_summary,
            "candidate_summary": cand_summary,
            "paired_summary": paired_summary,
            "metrics": metrics,
        }

    def get_live_snapshot(self, run_id: str, snapshot_sequence: int = 1) -> Dict[str, Any]:
        """
        Capture consistent live point-in-time snapshot for WebSocket streaming.
        Bridges the worker thread safely without model mutation race conditions.
        """
        # Call get_run_detail with consistent synchronized read
        detail = self.get_run_detail(run_id)
        detail["snapshot_sequence"] = snapshot_sequence
        detail["timestamp"] = time.time()
        return detail

    def list_runs(self, page: int = 1, page_size: int = 20) -> Tuple[List[Dict[str, Any]], int]:
        """List paginated runs."""
        offset = max(0, (page - 1) * page_size)
        return self.storage.get_paginated_runs(limit=page_size, offset=offset)

    def list_incidents(
        self, run_id: str, page: int = 1, page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List paginated incidents for a run."""
        run_rec = self.storage.get_run(run_id)
        if run_rec is None:
            raise RunNotFoundError(f"Run '{run_id}' not found.")
        offset = max(0, (page - 1) * page_size)
        return self.storage.get_paginated_incidents(run_id=run_id, limit=page_size, offset=offset)

    def get_event_prediction(self, run_id: str, event_id: str) -> Dict[str, Any]:
        """Get event details and original recorded prediction."""
        record = self.storage.get_event_with_prediction(run_id, event_id)
        if record is None:
            raise RunNotFoundError(f"Event '{event_id}' for run '{run_id}' not found.")
        return record
