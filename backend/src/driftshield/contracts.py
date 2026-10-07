"""
driftshield.contracts
=====================
Dataclass contracts shared across DriftShield modules.

Design rules
------------
* ``StreamEvent`` carries ONLY public information — features, metadata.
  The true label is intentionally absent so it cannot accidentally leak to
  the learner.
* ``PredictionRecord`` is immutable once constructed (frozen=True).
  The evaluator scores it later; the learner must never mutate it.
* ``LabelRecord`` is the authoritative label delivered to the evaluator.
  The ``delivery_sequence`` field controls when it becomes available.
* ``AcquiredLabel`` is the internal record used by the label-acquisition
  subsystem; it is not exposed to the learner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Public stream event (no hidden truth)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StreamEvent:
    """
    One observation emitted by the stream simulator.

    Fields
    ------
    event_id : str
        Globally unique identifier. Format: ``"evt-<sequence>"``.
    sequence : int
        Monotonically increasing integer starting from 0.
    timestamp : float
        Unix epoch seconds at event generation time.
    features : Dict[str, float]
        Numerical feature values.  Phase 1 always has
        ``{"feature_0": ..., "feature_1": ...}``.
    is_synthetic : bool
        Always ``True`` in Phase 1.  Callers must not interpret synthetic
        data as real-world measurements.
    """

    event_id: str
    sequence: int
    timestamp: float
    features: Dict[str, float]
    is_synthetic: bool = True

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id must be a non-empty string.")
        if self.sequence < 0:
            raise ValueError(f"sequence must be >= 0, got {self.sequence}.")
        if not self.features:
            raise ValueError("features must be a non-empty dict.")
        for k, v in self.features.items():
            if not isinstance(v, (int, float)):
                raise TypeError(
                    f"Feature '{k}' must be numeric, got {type(v).__name__}."
                )
            _check_finite(k, v)


# ---------------------------------------------------------------------------
# Prediction record (frozen after creation)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PredictionRecord:
    """
    The classifier's prediction for one ``StreamEvent``.

    Predictions are locked in *before* any label is revealed.
    The evaluator scores predictions retrospectively.

    Fields
    ------
    event_id : str
        Links back to the originating ``StreamEvent``.
    sequence : int
        Copied from the originating event for efficient ordering.
    timestamp : float
        Copied from the originating event.
    predicted_label : int
        Hard prediction — 0 or 1.
    predicted_proba : float
        Estimated probability that the true label is 1.  In [0, 1].
    features : Dict[str, float]
        Feature snapshot at prediction time (for audit/debugging).
    warmup : bool
        ``True`` if this prediction was made during the warm-up window.
        Warm-up predictions are EXCLUDED from reported metrics.
    """

    event_id: str
    sequence: int
    timestamp: float
    predicted_label: int
    predicted_proba: float
    features: Dict[str, float]
    warmup: bool = False
    model_version: str = "v1.0-frozen"

    def __post_init__(self) -> None:
        if self.predicted_label not in (0, 1):
            raise ValueError(
                f"predicted_label must be 0 or 1, got {self.predicted_label}."
            )
        if not (0.0 <= self.predicted_proba <= 1.0):
            raise ValueError(
                f"predicted_proba must be in [0, 1], got {self.predicted_proba}."
            )


# ---------------------------------------------------------------------------
# Label record (delivered by the simulator to the evaluator)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LabelRecord:
    """
    The ground-truth label for one event, delivered with optional delay.

    The evaluator uses this to score ``PredictionRecord``s.
    The learner NEVER receives a ``LabelRecord`` directly; it only receives
    labels via the ``LabelAcquirer`` which filters by budget.

    Fields
    ------
    event_id : str
        Links to the originating ``StreamEvent``.
    true_label : int
        Ground-truth class — 0 or 1.
    delivery_sequence : int
        The stream sequence at which this label becomes available.
        If ``label_delay == 0``, ``delivery_sequence == sequence``.
    """

    event_id: str
    true_label: int
    delivery_sequence: int

    def __post_init__(self) -> None:
        if self.true_label not in (0, 1):
            raise ValueError(
                f"true_label must be 0 or 1, got {self.true_label}."
            )
        if self.delivery_sequence < 0:
            raise ValueError(
                f"delivery_sequence must be >= 0, got {self.delivery_sequence}."
            )


# ---------------------------------------------------------------------------
# Internal label-acquisition record
# ---------------------------------------------------------------------------


@dataclass
class AcquiredLabel:
    """
    Internal record used by the label-acquisition subsystem.

    Not exposed to the learner.  Tracks which budget pool was responsible.

    Fields
    ------
    event_id : str
    true_label : int
    delivery_sequence : int
    source : str
        One of ``"warmup"``, ``"monitor"``, ``"low_margin"``, or ``"both"``.
    """

    event_id: str
    true_label: int
    delivery_sequence: int
    source: str


# ---------------------------------------------------------------------------
# Monitoring and Alert Contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DriftAlert:
    """
    Record emitted when the error-change monitor detects statistical evidence of change.

    Fields
    ------
    alert_id : str
        Globally unique identifier. Format: "alert-<sequence>".
    event_id : str
        Triggering observation's event ID.
    event_sequence : int
        Triggering observation's sequence index in the stream.
    arrival_sequence : int
        Sequence index at which the label arrived and was evaluated by monitor.
    detection_delay_from_event : int
        arrival_sequence - event_sequence (the label delivery delay).
    model_version : str
        Active model version at prediction time.
    loss : int
        Binary 0/1 error loss on the triggering monitoring observation.
    adwin_delta : float
        Configured ADWIN delta confidence parameter.
    adwin_estimation : float
        ADWIN estimated error rate at the moment of alert.
    adwin_width : int
        ADWIN sliding window width at the moment of alert.
    adwin_variance : Optional[float]
        ADWIN variance statistic if available.
    adwin_total : Optional[float]
        ADWIN cumulative total statistic if available.
    monitoring_labels_count : int
        Cumulative monitoring labels processed up to this alert.
    monitoring_coverage : float
        Proportion of post-freeze events covered by random monitoring.
    description : str
        Standard description: "evidence of error change".
    """

    alert_id: str
    event_id: str
    event_sequence: int
    arrival_sequence: int
    detection_delay_from_event: int
    model_version: str
    loss: int
    adwin_delta: float
    adwin_estimation: float
    adwin_width: int
    monitoring_labels_count: int
    monitoring_coverage: float
    adwin_variance: Optional[float] = None
    adwin_total: Optional[float] = None
    description: str = "evidence of error change"

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "event_id": self.event_id,
            "event_sequence": self.event_sequence,
            "arrival_sequence": self.arrival_sequence,
            "detection_delay_from_event": self.detection_delay_from_event,
            "model_version": self.model_version,
            "loss": self.loss,
            "adwin_delta": self.adwin_delta,
            "adwin_estimation": self.adwin_estimation,
            "adwin_width": self.adwin_width,
            "adwin_variance": self.adwin_variance,
            "adwin_total": self.adwin_total,
            "monitoring_labels_count": self.monitoring_labels_count,
            "monitoring_coverage": self.monitoring_coverage,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# Adaptation & Candidate Contracts
# ---------------------------------------------------------------------------


class CandidateState(str, Enum):
    """Lifecycle state of an adaptation candidate model."""
    IDLE = "IDLE"
    TRAINING = "TRAINING"
    READY_FOR_EVALUATION = "READY_FOR_EVALUATION"
    INCOMPLETE = "INCOMPLETE"
    EVALUATING = "EVALUATING"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class CandidateTrainingRecord:
    """Record of a single label absorbed during candidate training."""
    candidate_id: str
    event_id: str
    event_sequence: int
    arrival_sequence: int
    true_label: int
    source: str
    cumulative_training_labels: int

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "event_id": self.event_id,
            "event_sequence": self.event_sequence,
            "arrival_sequence": self.arrival_sequence,
            "true_label": self.true_label,
            "source": self.source,
            "cumulative_training_labels": self.cumulative_training_labels,
        }


@dataclass
class CandidateSummary:
    """Consolidated summary of a candidate model's lifecycle and training."""
    candidate_id: str
    active_model_version: str
    alert_id: str
    actionable_alert_sequence: int
    epoch: int
    state: str
    unique_training_labels: int
    target_training_labels: int
    creation_sequence: int
    freeze_sequence: Optional[int] = None
    state_transitions: List[Dict] = field(default_factory=list)
    training_event_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "active_model_version": self.active_model_version,
            "alert_id": self.alert_id,
            "actionable_alert_sequence": self.actionable_alert_sequence,
            "epoch": self.epoch,
            "state": self.state,
            "unique_training_labels": self.unique_training_labels,
            "target_training_labels": self.target_training_labels,
            "creation_sequence": self.creation_sequence,
            "freeze_sequence": self.freeze_sequence,
            "state_transitions": self.state_transitions,
            "training_event_ids": self.training_event_ids,
        }


# ---------------------------------------------------------------------------
# Paired Evaluation & Promotion Contracts (Phase 4B)
# ---------------------------------------------------------------------------


class EvaluationDecision(str, Enum):
    """Statistical decision outcome for paired candidate evaluation."""
    PENDING = "PENDING"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"
    INCOMPLETE = "INCOMPLETE"


@dataclass
class PairedPredictionRecord:
    """
    Record of locked-in predictions from active model and candidate on a single evaluation event.

    Recorded at event arrival BEFORE revealing the label.
    """
    eval_id: str
    event_id: str
    event_sequence: int
    active_model_version: str
    candidate_id: str
    active_predicted_label: int
    active_predicted_proba: float
    candidate_predicted_label: int
    candidate_predicted_proba: float
    features: Dict[str, float] = field(default_factory=dict)
    true_label: Optional[int] = None
    delivery_sequence: Optional[int] = None
    is_delivered: bool = False
    active_correct: Optional[bool] = None
    candidate_correct: Optional[bool] = None
    disagreement_type: Optional[str] = None

    def to_dict(self) -> dict:
        row = {
            "eval_id": self.eval_id,
            "event_id": self.event_id,
            "event_sequence": self.event_sequence,
            "active_model_version": self.active_model_version,
            "candidate_id": self.candidate_id,
            "active_predicted_label": self.active_predicted_label,
            "active_predicted_proba": self.active_predicted_proba,
            "candidate_predicted_label": self.candidate_predicted_label,
            "candidate_predicted_proba": self.candidate_predicted_proba,
            "true_label": self.true_label if self.is_delivered else "",
            "delivery_sequence": self.delivery_sequence if self.is_delivered else "",
            "is_delivered": int(self.is_delivered),
            "active_correct": int(self.active_correct) if self.active_correct is not None else "",
            "candidate_correct": int(self.candidate_correct) if self.candidate_correct is not None else "",
            "disagreement_type": self.disagreement_type or "",
        }
        for k, v in self.features.items():
            row[f"feat_{k}"] = v
        return row


@dataclass
class PairedEvaluationSummary:
    """Consolidated summary of a paired candidate evaluation session."""
    eval_id: str
    candidate_id: str
    active_model_version: str
    target_candidate_version: str
    freeze_sequence: int
    selection_start_sequence: int
    selection_end_sequence: Optional[int]
    completion_sequence: Optional[int]
    target_events_n: int
    selected_events_count: int
    delivered_labels_count: int
    b: int
    c: int
    n: int
    gain: Optional[float]
    p_value: Optional[float]
    min_gain_threshold: float
    max_pvalue_threshold: float
    decision: str
    decision_reason: str
    active_model_promoted_to: Optional[str] = None
    cost_monitoring_labels_used: int = 0
    selected_event_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "eval_id": self.eval_id,
            "candidate_id": self.candidate_id,
            "active_model_version": self.active_model_version,
            "target_candidate_version": self.target_candidate_version,
            "freeze_sequence": self.freeze_sequence,
            "selection_start_sequence": self.selection_start_sequence,
            "selection_end_sequence": self.selection_end_sequence,
            "completion_sequence": self.completion_sequence,
            "target_events_n": self.target_events_n,
            "selected_events_count": self.selected_events_count,
            "delivered_labels_count": self.delivered_labels_count,
            "b": self.b,
            "c": self.c,
            "n": self.n,
            "gain": self.gain,
            "p_value": self.p_value,
            "min_gain_threshold": self.min_gain_threshold,
            "max_pvalue_threshold": self.max_pvalue_threshold,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "active_model_promoted_to": self.active_model_promoted_to,
            "cost_monitoring_labels_used": self.cost_monitoring_labels_used,
            "selected_event_ids": self.selected_event_ids,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_finite(name: str, value: float) -> None:
    """Raise ValueError for NaN or infinite feature values."""
    import math

    if math.isnan(value) or math.isinf(value):
        raise ValueError(
            f"Feature '{name}' has non-finite value: {value}. "
            "DriftShield requires all features to be finite real numbers."
        )
