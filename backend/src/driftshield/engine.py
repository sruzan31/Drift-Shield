"""driftshield.engine
==================
Reusable single-owner runtime engine for DriftShield stream processing.

Design & Invariant Rules
------------------------
1. Single Owner Model:
   - One Engine instance owns all mutable state (models, detectors, label acquirers,
     candidate lifecycle, and paired evaluation) for a single run.
   - All mutations are serialized through the engine; no concurrent model mutations.

2. Pure Prediction & Separation:
   - Predictions are locked in at event arrival before any label is disclosed.
   - Learner and monitoring components see only authorized, legitimate labels.
   - Ground-truth evaluation occurs via the decoupled Evaluator path.

3. Complete Lifecycle Orchestration:
   - Initialization -> Warm-up -> Freezing -> Error-change monitoring ->
     Candidate training -> Fresh paired evaluation -> Atomic promotion -> Drain -> Finalize.
   - Durable persistence across events, predictions, labels, alerts, model artifacts, and metrics.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
import json
from pathlib import Path
import platform
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pydantic
import river

from .adaptation import CandidateManager
from .baseline import BaselineClassifier
from .config import DriftShieldConfig
from .contracts import (
    CandidateState,
    DriftAlert,
    EvaluationDecision,
    PredictionRecord,
    StreamEvent,
)
from .evaluator import EvaluationMetrics, Evaluator
from .labeling import LabelAcquirer
from .monitoring import ErrorChangeMonitor
from .paired_evaluation import PairedEvaluationSession, PairedEvaluator
from .simulator import Simulator
from .storage import SQLiteStorage


def get_execution_environment() -> dict:
    """Record execution environment metadata."""
    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "river_version": getattr(river, "__version__", "unknown"),
        "numpy_version": np.__version__,
        "pydantic_version": pydantic.__version__,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@dataclass(frozen=True)
class EngineEventResult:
    """Result of processing a single stream event."""
    event_id: str
    sequence: int
    predicted_label: int
    predicted_proba: float
    model_version: str
    is_warmup: bool
    is_duplicate: bool = False
    alerts_triggered: List[DriftAlert] = field(default_factory=list)
    promotions_triggered: List[str] = field(default_factory=list)


@dataclass
class EngineSnapshot:
    """Point-in-time observational snapshot of the active engine."""
    run_id: str
    scenario: str
    state: str
    events_processed: int
    active_model_version: str
    warmup_complete: bool
    monitoring_coverage: float
    adwin_estimation: float
    adwin_width: int
    alerts_count: int
    candidates_count: int
    active_candidate_id: Optional[str]
    evaluations_completed: int
    last_decision: Optional[str]


@dataclass
class EngineSummary:
    """Consolidated summary returned upon engine finalization."""
    run_id: str
    scenario: str
    state: str
    total_events: int
    active_model_version: str
    evaluation_start_sequence: int
    metrics: Optional[Dict[str, Any]]
    monitoring_summary: Dict[str, Any]
    candidate_summary: Dict[str, Any]
    paired_summary: Dict[str, Any]
    environment: Dict[str, Any]


class DriftShieldEngine:
    """
    Core single-owner DriftShield execution engine.

    Parameters
    ----------
    config : DriftShieldConfig
        Validated configuration for stream, labels, monitoring, and adaptation.
    run_id : Optional[str]
        Unique run identifier. If None, generated automatically.
    storage : Optional[SQLiteStorage]
        Durable persistence backend. If None, instantiates SQLiteStorage in config.output_dir.
    """

    def __init__(
        self,
        config: DriftShieldConfig,
        run_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        storage: Optional[SQLiteStorage] = None,
        environment: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.config = config
        self.scenario = config.stream.scenario
        self.parent_run_id = parent_run_id
        self.environment = environment or get_execution_environment()

        # Output and storage initialization
        self.output_dir = Path(config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.storage = storage or SQLiteStorage(
            db_path=self.output_dir / "driftshield.db",
            artifacts_dir=self.output_dir / "artifacts",
        )

        if run_id is not None:
            self.run_id = run_id
        else:
            base_run_id = f"run-{self.scenario}-{config.stream.seed}"
            if self.storage.get_run(base_run_id) is not None:
                # Subsequent run in same DB: generate unique replay run ID and link parent
                import uuid
                self.run_id = f"{base_run_id}-replay-{uuid.uuid4().hex[:6]}"
                if self.parent_run_id is None:
                    self.parent_run_id = base_run_id
            else:
                self.run_id = base_run_id

        # Learning & Detection Components
        self.baseline = BaselineClassifier(self.config.labels)
        self.acquirer: Optional[LabelAcquirer] = None
        self.monitor = ErrorChangeMonitor(self.config.monitoring, model_version="v1.0-frozen")
        self.candidate_manager = CandidateManager(
            config=self.config.adaptation,
            preprocessor=self.baseline.scaler,
            active_model_version="v1.0-frozen",
        )

        # Paired Evaluator with promotion callback
        self.paired_evaluator = PairedEvaluator(
            config=self.config.adaptation,
            on_promotion_callback=self._on_promotion,
        )

        # Decoupled Evaluator (optional, receives hidden truth only if provided)
        self.evaluator: Optional[Evaluator] = None

        # State tracking
        self.state: str = "INITIALIZING"
        self.events_processed_count: int = 0
        self.freeze_sequence: Optional[int] = None
        self.evaluation_start_sequence: int = self.config.labels.warmup_size
        self._processed_events: Dict[str, StreamEvent] = {}
        self._processed_predictions: Dict[str, PredictionRecord] = {}
        self._delivered_labels: Dict[str, int] = {}

    def _on_promotion(self, session: PairedEvaluationSession) -> None:
        """Atomic model switch and detector reset on candidate promotion."""
        # 1. Switch active classifier model weights
        self.baseline.promote_candidate(
            candidate_lr_model=session.candidate_model._lr,
            new_model_version=session.target_candidate_version,
        )
        # 2. Update candidate manager active version
        self.candidate_manager.on_candidate_promoted(session.target_candidate_version)
        # 3. Reset ADWIN detector for the new model version
        self.monitor.reset(
            new_model_version=session.target_candidate_version,
            reset_sequence=session.completion_sequence or 0,
        )
        # 4. Save promoted model version artifact in durable storage
        self.storage.save_model_version(
            run_id=self.run_id,
            version_tag=session.target_candidate_version,
            activation_sequence=session.completion_sequence or 0,
            model_obj=self.baseline._lr,
            preprocessor_obj=self.baseline.scaler,
            parent_version_tag=session.active_model_version,
            metadata={
                "promotion_gain": session.gain,
                "promotion_p_value": session.p_value,
                "b": session.b,
                "c": session.c,
                "n": session.n,
                "eval_id": session.eval_id,
            },
        )

    def initialize(
        self,
        simulator: Optional[Simulator] = None,
        all_label_records: Optional[List[Any]] = None,
    ) -> None:
        # Create run in storage first so foreign keys reference valid run_id
        self.storage.create_run(
            run_id=self.run_id,
            parent_run_id=self.parent_run_id,
            scenario=self.scenario,
            seed=self.config.stream.seed,
            mode="simulation" if simulator else "stream",
            config=self.config.model_dump(),
            environment=self.environment,
            schema_version="v1.0",
        )
        self.state = "WARMUP"
        self.storage.update_run_state(self.run_id, "WARMUP")

        if simulator is not None:
            all_label_records = simulator.get_label_records()
            self.evaluator = Evaluator(
                simulator,
                warmup_size=self.config.labels.warmup_size,
                drift_sequence=simulator.drift_sequence,
            )
            # Record evaluator hidden truth into separate evaluator-only table
            for ev in simulator.events:
                hidden_lbl = simulator.get_hidden_label(ev.event_id)
                is_pre = (
                    simulator.drift_sequence is None
                    or ev.sequence < simulator.drift_sequence
                )
                self.storage.record_evaluator_truth(
                    run_id=self.run_id,
                    event_id=ev.event_id,
                    hidden_label=hidden_lbl,
                    is_pre_drift=is_pre,
                )

        if all_label_records is not None:
            self.acquirer = LabelAcquirer(self.config.labels, all_label_records)

    def process_event(self, event: StreamEvent) -> EngineEventResult:
        """
        Process a single stream event through the full pipeline.

        Enforces:
        - Schema & finiteness validation.
        - Idempotent duplicate check.
        - Prediction before label disclosure.
        - Sequential paired evaluation recording on random-monitoring events.
        - Legitimate label delivery, monitoring loss update, candidate training.
        - Baseline model freezing at warmup boundary.
        - Durable storage persistence.
        """
        # 1. Duplicate check
        if event.event_id in self._processed_events:
            prev_event = self._processed_events[event.event_id]
            if prev_event.sequence != event.sequence or prev_event.features != event.features:
                raise ValueError(
                    f"Conflicting duplicate event '{event.event_id}' with different sequence or features."
                )
            prev_pred = self._processed_predictions[event.event_id]
            return EngineEventResult(
                event_id=event.event_id,
                sequence=event.sequence,
                predicted_label=prev_pred.predicted_label,
                predicted_proba=prev_pred.predicted_proba,
                model_version=getattr(prev_pred, "model_version", "v1.0-frozen"),
                is_warmup=prev_pred.warmup,
                is_duplicate=True,
            )

        is_warmup = event.sequence < self.config.labels.warmup_size
        if is_warmup:
            self.baseline.register_warmup_features(event)

        if self.baseline.is_frozen:
            self.monitor.register_evaluated_event(event.sequence)

        # 2. Predict BEFORE revealing any label
        t0 = time.perf_counter()
        pred = self.baseline.predict(event)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        self._processed_events[event.event_id] = event
        self._processed_predictions[event.event_id] = pred
        self.events_processed_count += 1

        if self.evaluator is not None:
            self.evaluator.record_prediction(pred)

        # Record event and prediction in durable storage
        self.storage.record_event(self.run_id, event, processing_status="ACCEPTED")
        self.storage.record_prediction(self.run_id, pred, latency_ms=latency_ms)

        # 3. Step label acquirer
        delivered = []
        if self.acquirer is not None:
            delivered = self.acquirer.step(event.sequence, pred)
            for req in self.acquirer.pop_new_requests():
                self.storage.record_label_request(
                    run_id=self.run_id,
                    event_id=req["event_id"],
                    channel=req["channel"],
                    requested_sequence=req["requested_sequence"],
                    status=req["status"],
                    cost=req["cost"],
                    budget_debit=req["budget_debit"],
                )

        # If paired evaluation session is active, check if this event was acquired for random monitoring
        if (
            self.paired_evaluator.active_session is not None
            and not self.paired_evaluator.active_session.is_finished
        ):
            is_rand_mon = (
                self.acquirer.was_monitor_acquired(event.event_id)
                if self.acquirer
                else False
            )
            self.paired_evaluator.record_paired_event(
                event=event,
                active_predicted_label=pred.predicted_label,
                active_predicted_proba=pred.predicted_proba,
                is_random_monitor_selected=is_rand_mon,
            )

        alerts_triggered: List[DriftAlert] = []
        promotions_triggered: List[str] = []

        # 4. Process delivered labels
        for lbl in delivered:
            # Duplicate / conflict check in storage
            self.storage.record_label(
                run_id=self.run_id,
                event_id=lbl.event_id,
                true_label=lbl.true_label,
                source=lbl.source,
                channel=lbl.source,
                delivery_sequence=event.sequence,
                arrival_sequence=event.sequence,
                validation_status="VALID",
            )
            self._delivered_labels[lbl.event_id] = lbl.true_label

            if self.evaluator is not None:
                self.evaluator.deliver_label(lbl)

            # Train initial baseline before freeze
            if lbl.source == "warmup" and not self.baseline.is_frozen:
                self.baseline.learn(lbl.event_id, lbl.true_label)
            elif self.baseline.is_frozen:
                orig_pred = self._processed_predictions.get(lbl.event_id, pred)

                # Random monitoring channel
                if lbl.source in ("monitor", "both"):
                    # Feed label to active paired evaluation session
                    if (
                        self.paired_evaluator.active_session is not None
                        and not self.paired_evaluator.active_session.is_finished
                    ):
                        active_sess = self.paired_evaluator.active_session
                        decision = self.paired_evaluator.deliver_label(
                            event_id=lbl.event_id,
                            true_label=lbl.true_label,
                            delivery_sequence=event.sequence,
                        )
                        if decision == EvaluationDecision.PROMOTED:
                            promotions_triggered.append(self.baseline.model_version)
                            if active_sess.candidate_model.alert_id:
                                self.storage.update_incident_outcome(
                                    run_id=self.run_id,
                                    incident_id=active_sess.candidate_model.alert_id,
                                    outcome="PROMOTED",
                                    candidate_id=active_sess.candidate_id,
                                    extra_evidence={
                                        "decision": "PROMOTED",
                                        "gain": active_sess.gain,
                                        "p_value": active_sess.p_value,
                                        "b": active_sess.b,
                                        "c": active_sess.c,
                                        "n": active_sess.n,
                                        "promoted_model_version": active_sess.target_candidate_version,
                                        "promotion_sequence": active_sess.completion_sequence,
                                    },
                                )
                        elif decision == EvaluationDecision.REJECTED:
                            if active_sess.candidate_model.alert_id:
                                self.storage.update_incident_outcome(
                                    run_id=self.run_id,
                                    incident_id=active_sess.candidate_model.alert_id,
                                    outcome="REJECTED",
                                    candidate_id=active_sess.candidate_id,
                                    extra_evidence={
                                        "decision": "REJECTED",
                                        "gain": active_sess.gain,
                                        "p_value": active_sess.p_value,
                                        "b": active_sess.b,
                                        "c": active_sess.c,
                                        "n": active_sess.n,
                                    },
                                )
                            self.candidate_manager.on_candidate_rejected()

                    # Feed loss to ADWIN error-change monitor
                    alert = self.monitor.process_monitoring_label(
                        event_id=lbl.event_id,
                        event_sequence=orig_pred.sequence,
                        arrival_sequence=event.sequence,
                        original_prediction=orig_pred,
                        true_label=lbl.true_label,
                        source=lbl.source,
                    )
                    if alert is not None:
                        alerts_triggered.append(alert)
                        cand = self.candidate_manager.handle_alert(
                            alert,
                            current_sequence=event.sequence,
                            is_cap_reached=self.paired_evaluator.is_comparison_cap_reached,
                        )
                        outcome_str = "TRAINING_INITIATED" if cand else "IGNORED"
                        self.storage.record_incident(
                            run_id=self.run_id,
                            alert=alert,
                            candidate_id=cand.candidate_id if cand else None,
                            outcome=outcome_str,
                        )

                # Offer authorized label to candidate for post-epoch training
                absorbed = self.candidate_manager.train_step(
                    event_id=lbl.event_id,
                    event_sequence=orig_pred.sequence,
                    arrival_sequence=event.sequence,
                    features=orig_pred.features,
                    true_label=lbl.true_label,
                    source=lbl.source,
                )
                if absorbed and self.candidate_manager.active_candidate is not None:
                    ac = self.candidate_manager.active_candidate
                    if (
                        ac.state == CandidateState.READY_FOR_EVALUATION
                        and ac.freeze_sequence == event.sequence
                    ):
                        self.paired_evaluator.start_session(
                            candidate_model=ac,
                            active_model_version=self.baseline.model_version,
                            current_sequence=event.sequence,
                        )
                        if ac.alert_id:
                            self.storage.update_incident_outcome(
                                run_id=self.run_id,
                                incident_id=ac.alert_id,
                                outcome="TRAINING_COMPLETED",
                                candidate_id=ac.candidate_id,
                                extra_evidence={
                                    "candidate_state": "READY_FOR_EVALUATION",
                                    "freeze_sequence": ac.freeze_sequence,
                                    "unique_training_labels": ac.unique_training_labels,
                                },
                            )

        # 5. Step timeout checks on paired evaluator
        self.paired_evaluator.step(event.sequence)

        # 6. Check initial model freeze
        if (
            not self.baseline.is_frozen
            and event.sequence >= self.config.labels.warmup_size - 1 + self.config.labels.label_delay
        ):
            self.baseline.freeze()
            self.freeze_sequence = event.sequence
            self.evaluation_start_sequence = event.sequence + 1
            if self.evaluator is not None:
                self.evaluator.set_evaluation_start_sequence(self.evaluation_start_sequence)
            self.state = "RUNNING"
            self.storage.update_run_state(self.run_id, "RUNNING")
            # Save frozen initial model version artifact
            self.storage.save_model_version(
                run_id=self.run_id,
                version_tag="v1.0-frozen",
                activation_sequence=self.evaluation_start_sequence,
                model_obj=self.baseline._lr,
                preprocessor_obj=self.baseline.scaler,
                parent_version_tag=None,
                metadata={"warmup_size": self.config.labels.warmup_size},
            )

        return EngineEventResult(
            event_id=event.event_id,
            sequence=event.sequence,
            predicted_label=pred.predicted_label,
            predicted_proba=pred.predicted_proba,
            model_version=self.baseline.model_version,
            is_warmup=is_warmup,
            is_duplicate=False,
            alerts_triggered=alerts_triggered,
            promotions_triggered=promotions_triggered,
        )

    def drain_pending_labels(self, up_to_sequence: Optional[int] = None) -> List[Any]:
        """
        Drain all remaining pending delayed labels up to supplied sequence ceiling.
        """
        if self.acquirer is None:
            return []

        seq_ceiling = (
            up_to_sequence
            if up_to_sequence is not None
            else (
                self.events_processed_count
                + self.config.labels.label_delay
            )
        )
        remaining = self.acquirer.flush_pending_up_to(seq_ceiling)

        for lbl in remaining:
            self.storage.record_label(
                run_id=self.run_id,
                event_id=lbl.event_id,
                true_label=lbl.true_label,
                source=lbl.source,
                channel=lbl.source,
                delivery_sequence=lbl.delivery_sequence,
                arrival_sequence=lbl.delivery_sequence,
                validation_status="VALID",
            )
            self._delivered_labels[lbl.event_id] = lbl.true_label

            if self.evaluator is not None:
                self.evaluator.deliver_label(lbl)

            if self.baseline.is_frozen:
                orig_pred = self._processed_predictions.get(lbl.event_id)
                if orig_pred is not None:
                    if lbl.source in ("monitor", "both"):
                        if (
                            self.paired_evaluator.active_session is not None
                            and not self.paired_evaluator.active_session.is_finished
                        ):
                            dec = self.paired_evaluator.deliver_label(
                                event_id=lbl.event_id,
                                true_label=lbl.true_label,
                                delivery_sequence=lbl.delivery_sequence,
                            )
                            if dec == EvaluationDecision.REJECTED:
                                self.candidate_manager.on_candidate_rejected()

                        alert = self.monitor.process_monitoring_label(
                            event_id=lbl.event_id,
                            event_sequence=orig_pred.sequence,
                            arrival_sequence=lbl.delivery_sequence,
                            original_prediction=orig_pred,
                            true_label=lbl.true_label,
                            source=lbl.source,
                        )
                        if alert is not None:
                            cand = self.candidate_manager.handle_alert(
                                alert,
                                current_sequence=lbl.delivery_sequence,
                                is_cap_reached=self.paired_evaluator.is_comparison_cap_reached,
                            )
                            self.storage.record_incident(
                                run_id=self.run_id,
                                alert=alert,
                                candidate_id=cand.candidate_id if cand else None,
                                outcome="TRAINING_INITIATED" if cand else "IGNORED",
                            )

                    absorbed = self.candidate_manager.train_step(
                        event_id=lbl.event_id,
                        event_sequence=orig_pred.sequence,
                        arrival_sequence=lbl.delivery_sequence,
                        features=orig_pred.features,
                        true_label=lbl.true_label,
                        source=lbl.source,
                    )
                    if absorbed and self.candidate_manager.active_candidate is not None:
                        ac = self.candidate_manager.active_candidate
                        if (
                            ac.state == CandidateState.READY_FOR_EVALUATION
                            and ac.freeze_sequence == lbl.delivery_sequence
                        ):
                            self.paired_evaluator.start_session(
                                candidate_model=ac,
                                active_model_version=self.baseline.model_version,
                                current_sequence=lbl.delivery_sequence,
                            )
        return remaining

    def finalize(self) -> EngineSummary:
        """
        Finalize run execution, record metric windows, and update state to COMPLETED.
        """
        # Drain any remaining labels
        last_seq = (
            max(ev.sequence for ev in self._processed_events.values())
            if self._processed_events
            else 0
        )
        self.drain_pending_labels(last_seq + self.config.labels.label_delay)

        # Finalize adaptation and paired evaluation
        self.paired_evaluator.finalize(last_seq)
        self.candidate_manager.finalize(last_seq)

        # Update incident for incomplete candidate if any
        if self.candidate_manager.active_candidate is not None:
            ac = self.candidate_manager.active_candidate
            if ac.alert_id and ac.state == CandidateState.INCOMPLETE:
                self.storage.update_incident_outcome(
                    run_id=self.run_id,
                    incident_id=ac.alert_id,
                    outcome="INCOMPLETE",
                    candidate_id=ac.candidate_id,
                    extra_evidence={
                        "candidate_state": "INCOMPLETE",
                        "unique_training_labels": ac.unique_training_labels,
                        "target_training_labels": ac.target_training_labels,
                    },
                )

        # Compute metrics if evaluator is available
        metrics_dict = None
        if self.evaluator is not None and self.acquirer is not None:
            metrics = self.evaluator.compute_metrics(
                label_acquisition=self.acquirer.get_channel_stats(),
                evaluation_start_sequence=self.evaluation_start_sequence,
                alerts=self.monitor.alerts,
            )
            metrics_dict = metrics.to_dict()

            # Record metric windows in durable storage
            if metrics.full_synthetic is not None:
                self.storage.record_metric_window(
                    run_id=self.run_id,
                    start_sequence=self.evaluation_start_sequence,
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
                self.storage.record_metric_window(
                    run_id=self.run_id,
                    start_sequence=self.evaluation_start_sequence,
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

        self.state = "COMPLETED"
        self.storage.update_run_state(self.run_id, "COMPLETED", completed=True)

        return EngineSummary(
            run_id=self.run_id,
            scenario=self.scenario,
            state=self.state,
            total_events=self.events_processed_count,
            active_model_version=self.baseline.model_version,
            evaluation_start_sequence=self.evaluation_start_sequence,
            metrics=metrics_dict,
            monitoring_summary=self.monitor.get_summary(),
            candidate_summary=self.candidate_manager.get_summary(),
            paired_summary=self.paired_evaluator.get_summary(),
            environment=self.environment,
        )

    def get_snapshot(self) -> EngineSnapshot:
        """Retrieve live point-in-time snapshot."""
        cand_id = (
            self.candidate_manager.active_candidate.candidate_id
            if self.candidate_manager.active_candidate
            else None
        )
        last_dec = None
        if self.paired_evaluator.completed_sessions:
            last_dec = self.paired_evaluator.completed_sessions[-1].decision.value
        elif self.paired_evaluator.active_session:
            last_dec = self.paired_evaluator.active_session.decision.value

        return EngineSnapshot(
            run_id=self.run_id,
            scenario=self.scenario,
            state=self.state,
            events_processed=self.events_processed_count,
            active_model_version=self.baseline.model_version,
            warmup_complete=self.baseline.is_frozen,
            monitoring_coverage=self.monitor.monitoring_coverage,
            adwin_estimation=self.monitor.adwin_estimation,
            adwin_width=self.monitor.adwin_width,
            alerts_count=self.monitor.alerts_count,
            candidates_count=self.candidate_manager.candidate_counter,
            active_candidate_id=cand_id,
            evaluations_completed=self.paired_evaluator.completed_comparisons_count,
            last_decision=last_dec,
        )

    def export_artifacts(self, output_dir: Optional[Path | str] = None) -> Dict[str, Path]:
        """
        Export standard CSV and JSON artifacts.
        """
        out_path = Path(output_dir) if output_dir else self.output_dir
        out_path.mkdir(parents=True, exist_ok=True)
        scenario = self.scenario
        paths = {}

        # 1. Predictions CSV
        if self.evaluator is not None:
            csv_path = out_path / f"{scenario}_predictions.csv"
            rows = self.evaluator.get_scored_predictions()
            if rows:
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                    writer.writeheader()
                    writer.writerows(rows)
                paths["predictions_csv"] = csv_path

        # 2. Alerts CSV
        alerts_csv_path = out_path / f"{scenario}_alerts.csv"
        alert_rows = [a.to_dict() for a in self.monitor.alerts]
        alert_fieldnames = [
            "alert_id",
            "event_id",
            "event_sequence",
            "arrival_sequence",
            "detection_delay_from_event",
            "model_version",
            "loss",
            "adwin_delta",
            "adwin_estimation",
            "adwin_width",
            "adwin_variance",
            "adwin_total",
            "monitoring_labels_count",
            "monitoring_coverage",
            "description",
        ]
        with open(alerts_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=alert_fieldnames)
            writer.writeheader()
            if alert_rows:
                writer.writerows(alert_rows)
        paths["alerts_csv"] = alerts_csv_path

        # 3. Candidate CSV & JSON
        cand_csv, cand_json = self.candidate_manager.export(out_path, scenario)
        paths["candidate_csv"] = cand_csv
        paths["candidate_json"] = cand_json

        # 4. Paired Eval CSV & JSON
        paired_csv, paired_json = self.paired_evaluator.export(out_path, scenario)
        paths["paired_csv"] = paired_csv
        paths["paired_json"] = paired_json

        # 5. Metrics JSON
        if self.evaluator is not None and self.acquirer is not None:
            metrics = self.evaluator.compute_metrics(
                label_acquisition=self.acquirer.get_channel_stats(),
                evaluation_start_sequence=self.evaluation_start_sequence,
                alerts=self.monitor.alerts,
            )
            result = {
                "run_id": self.run_id,
                "scenario": scenario,
                "synthetic_data": True,
                "phase": 5,
                "monitoring_active": True,
                "candidate_adaptation_active": True,
                "paired_evaluation_active": True,
                "active_model_version": self.baseline.model_version,
                "limitations": [
                    "Online logistic regression with SGD; non-linear drift requires tree-based learners.",
                    "Paired comparison exact binomial p-values assume i.i.d. fixed-model observations; diagnostic under continuous drift.",
                    "At most 5 completed comparisons permitted per run.",
                    "Single-writer SQLite database persistence.",
                ],
                "environment": self.environment,
                "config": {
                    "stream": self.config.stream.model_dump(),
                    "labels": self.config.labels.model_dump(),
                    "monitoring": self.config.monitoring.model_dump(),
                    "adaptation": self.config.adaptation.model_dump(),
                },
                "monitoring_summary": self.monitor.get_summary(),
                "candidate_summary": self.candidate_manager.get_summary(),
                "paired_evaluation_summary": self.paired_evaluator.get_summary(),
                "metrics": metrics.to_dict(),
            }
            json_path = out_path / f"{scenario}_metrics.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            paths["metrics_json"] = json_path

        return paths
