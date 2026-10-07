"""
driftshield.evaluator
=====================
Independent evaluator for DriftShield Phase 1.

The evaluator is the *only* module that has access to the hidden truth.
It scores ``PredictionRecord`` objects retrospectively — after they have
been locked in — by joining them with delivered labels.

Evaluation channels
-------------------
1. **Full synthetic evaluation** — scores EVERY post-warmup prediction
   against the simulator hidden truth. No label acquisition required.
   The denominator is always ``n_events - warmup_size``.
   Broken down by pre-drift / post-drift when a drift sequence is known.

2. **Random monitoring channel** — scores only predictions for which a
   monitor-channel label was delivered. Denominator = monitor labels acquired.

3. **Selective channel** — scores only predictions for which a selective
   (low-margin) label was delivered. Clearly identified as selectively sampled.
   Denominator = selective labels acquired.

Strict ordering guarantees
--------------------------
* Predictions are locked in at ``record_prediction()`` time.
* Hidden truth is never passed to the learner or to ``LabelAcquirer``.
* Future labels cannot change past predictions (frozen dataclass + scored_ids set).
* Warm-up predictions are excluded from all reported metrics.

Null vs. zero
-------------
When a category has no scored examples, ``error_rate`` is ``None`` (serialized
as ``null``), not ``0.0``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .contracts import AcquiredLabel, PredictionRecord
from .simulator import Simulator


# ---------------------------------------------------------------------------
# Per-segment metrics
# ---------------------------------------------------------------------------


@dataclass
class SegmentMetrics:
    """
    Metrics for one evaluation segment (e.g., pre-drift, post-drift,
    or a channel subset).

    ``error_rate`` is ``None`` when ``total == 0``.
    """

    label: str           # human-readable segment name
    total: int = 0       # total predictions in this segment
    correct: int = 0     # correct predictions
    sampled: bool = False  # True if this is a selectively sampled channel

    @property
    def error_rate(self) -> Optional[float]:
        if self.total == 0:
            return None
        return 1.0 - self.correct / self.total

    @property
    def accuracy(self) -> Optional[float]:
        if self.total == 0:
            return None
        return self.correct / self.total

    @property
    def incorrect(self) -> int:
        return max(0, self.total - self.correct)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "total": self.total,
            "correct": self.correct,
            "incorrect": self.incorrect,
            "sample_count": self.total,
            "correct_count": self.correct,
            "incorrect_count": self.incorrect,
            "denominator": self.total,
            "error_rate": self.error_rate,
            "accuracy": self.accuracy,
            "selectively_sampled": self.sampled,
        }


# ---------------------------------------------------------------------------
# Top-level metrics
# ---------------------------------------------------------------------------


@dataclass
class EvaluationMetrics:
    """
    Full evaluation metrics from the evaluator.

    Attributes
    ----------
    warmup_size : int
    evaluation_start_sequence : int
    warmup_predictions : int
    initialization_predictions : int

    full_synthetic : SegmentMetrics
        All post-initialization predictions scored against simulator truth.
    pre_drift : SegmentMetrics or None
        Pre-drift subset (abrupt scenario only).
    post_drift : SegmentMetrics or None
        Post-drift subset (abrupt scenario only).

    monitor_channel : SegmentMetrics
        Predictions scored via acquired monitor labels.
    selective_channel : SegmentMetrics
        Predictions scored via acquired selective labels (marked sampled=True).

    label_acquisition : dict
        Per-channel label counts from the acquirer.
    """

    warmup_size: int = 0
    evaluation_start_sequence: int = 0
    warmup_predictions: int = 0
    initialization_predictions: int = 0

    full_synthetic: SegmentMetrics = field(
        default_factory=lambda: SegmentMetrics(label="full_synthetic")
    )
    pre_drift: Optional[SegmentMetrics] = None
    post_drift: Optional[SegmentMetrics] = None

    monitor_channel: SegmentMetrics = field(
        default_factory=lambda: SegmentMetrics(label="monitor")
    )
    selective_channel: SegmentMetrics = field(
        default_factory=lambda: SegmentMetrics(label="selective", sampled=True)
    )

    label_acquisition: dict = field(default_factory=dict)
    _explicit_label_acquisition_count: Optional[int] = None
    monitoring_alerts: List[dict] = field(default_factory=list)
    monitoring_evaluation: Optional[dict] = None

    # Legacy single-value properties (backward compat)
    @property
    def total_predictions(self) -> int:
        return self.full_synthetic.total

    @property
    def scored_predictions(self) -> int:
        return self.full_synthetic.total  # always fully scored

    @property
    def error_rate(self) -> Optional[float]:
        return self.full_synthetic.error_rate

    @property
    def label_acquisition_count(self) -> int:
        if self._explicit_label_acquisition_count is not None:
            return self._explicit_label_acquisition_count
        acq = self.label_acquisition
        return acq.get("monitor", {}).get("acquired", 0) + acq.get("selective", {}).get("acquired", 0)

    def to_dict(self) -> dict:
        d = {
            "warmup_size": self.warmup_size,
            "evaluation_start_sequence": self.evaluation_start_sequence,
            "warmup_predictions": self.warmup_predictions,
            "initialization_predictions": self.initialization_predictions,
            "full_synthetic_evaluation": self.full_synthetic.to_dict(),
            "monitor_channel": self.monitor_channel.to_dict(),
            "selective_channel": self.selective_channel.to_dict(),
            "label_acquisition": self.label_acquisition,
        }
        if self.pre_drift is not None:
            d["pre_drift"] = self.pre_drift.to_dict()
        if self.post_drift is not None:
            d["post_drift"] = self.post_drift.to_dict()
        if self.monitoring_evaluation is not None:
            d["monitoring_evaluation"] = self.monitoring_evaluation
        if self.monitoring_alerts:
            d["monitoring_alerts"] = self.monitoring_alerts
        # Legacy keys for backward-compat with existing tests
        d["error_rate"] = self.error_rate
        d["total_predictions"] = self.total_predictions
        d["scored_predictions"] = self.scored_predictions
        d["label_acquisition_count"] = self.label_acquisition_count
        return d


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


class Evaluator:
    """
    Scores predictions against hidden truth without leaking truth to the learner.

    Parameters
    ----------
    simulator : Simulator
        Used to look up hidden true labels by event_id.
    warmup_size : int
        Configured warm-up size.
    drift_sequence : int, optional
        If set, enables pre/post-drift breakdown.
    evaluation_start_sequence : int, optional
        The exact sequence index of the first prediction evaluated post-freeze.
        If None, defaults to warmup_size.
    """

    def __init__(
        self,
        simulator: Simulator,
        warmup_size: int,
        drift_sequence: Optional[int] = None,
        evaluation_start_sequence: Optional[int] = None,
    ) -> None:
        self._simulator = simulator
        self._warmup_size = warmup_size
        self._drift_sequence = drift_sequence
        self._evaluation_start_sequence = evaluation_start_sequence

        # All predictions keyed by event_id (locked in at record time)
        self._predictions: Dict[str, PredictionRecord] = {}

        # Delivered labels keyed by event_id, by channel
        # "warmup" labels go to _warmup_labels only (not scored as post-warmup)
        self._monitor_labels: Dict[str, int] = {}    # event_id -> true label
        self._selective_labels: Dict[str, int] = {}  # event_id -> true label
        self._warmup_labels: Dict[str, int] = {}

        # Prevent double-scoring
        self._scored_ids: set = set()

        # Counters for warmup predictions
        self._n_warmup: int = 0

    def set_evaluation_start_sequence(self, seq: int) -> None:
        """Set the sequence index where post-freeze evaluation begins."""
        self._evaluation_start_sequence = seq

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_prediction(self, pred: PredictionRecord) -> None:
        """
        Register a prediction.

        Must be called BEFORE any ``deliver_label()`` for the same event to
        preserve the invariant that future labels cannot affect past predictions.

        Raises
        ------
        ValueError
            If the same event_id is recorded twice.
        """
        if pred.event_id in self._predictions:
            raise ValueError(
                f"Duplicate prediction for event_id '{pred.event_id}'."
            )
        self._predictions[pred.event_id] = pred
        if pred.warmup:
            self._n_warmup += 1

    def deliver_label(self, acquired: AcquiredLabel) -> None:
        """
        Deliver an acquired label to the evaluator.

        The label is validated against simulator truth, then stored in the
        appropriate channel dict. The learner never sees these labels.

        Parameters
        ----------
        acquired : AcquiredLabel

        Raises
        ------
        ValueError
            If the label contradicts simulator truth (should never happen).
        """
        event_id = acquired.event_id

        # Verify truth consistency
        expected = self._simulator.get_hidden_label(event_id)
        if acquired.true_label != expected:
            raise ValueError(
                f"Label mismatch for event '{event_id}': "
                f"acquired {acquired.true_label} but simulator says {expected}."
            )

        # Route to channel store
        if acquired.source == "warmup":
            self._warmup_labels[event_id] = acquired.true_label
        elif acquired.source == "monitor":
            self._monitor_labels[event_id] = acquired.true_label
        elif acquired.source in ("selective", "both", "low_margin"):
            self._selective_labels[event_id] = acquired.true_label

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def compute_metrics(
        self,
        label_acquisition: Optional[dict] = None,
        label_acquisition_count: Optional[int] = None,
        evaluation_start_sequence: Optional[int] = None,
        alerts: Optional[List[Any]] = None,
    ) -> EvaluationMetrics:
        """
        Compute all evaluation metrics.

        Full synthetic evaluation uses simulator truth for all post-freeze
        predictions starting at evaluation_start_sequence.
        Independent alarm evaluation scores ADWIN alerts against synthetic drift ground truth.

        Parameters
        ----------
        label_acquisition : dict, optional
            Channel stats dict from LabelAcquirer.get_channel_stats().
        label_acquisition_count : int, optional
            Explicit total count for backward compatibility.
        evaluation_start_sequence : int, optional
            Explicit evaluation start sequence boundary.
        alerts : list of DriftAlert, optional
            Emitted drift alerts from the ErrorChangeMonitor.

        Returns
        -------
        EvaluationMetrics
        """
        start_seq = (
            evaluation_start_sequence
            if evaluation_start_sequence is not None
            else (
                self._evaluation_start_sequence
                if self._evaluation_start_sequence is not None
                else self._warmup_size
            )
        )

        full = SegmentMetrics(label="full_synthetic")
        pre = SegmentMetrics(label="pre_drift") if self._drift_sequence is not None else None
        post = SegmentMetrics(label="post_drift") if self._drift_sequence is not None else None
        monitor = SegmentMetrics(label="monitor")
        selective = SegmentMetrics(label="selective", sampled=True)

        n_init = 0
        for event_id, pred in self._predictions.items():
            if pred.sequence < start_seq:
                n_init += 1
                continue  # initialization/warmup excluded from evaluation

            # Hidden truth — evaluator has direct access to simulator
            true_label = self._simulator.get_hidden_label(event_id)
            is_correct = int(pred.predicted_label == true_label)

            # Full synthetic
            full.total += 1
            full.correct += is_correct

            # Pre/post drift split
            if pre is not None and pred.sequence < self._drift_sequence:
                pre.total += 1
                pre.correct += is_correct
            if post is not None and pred.sequence >= self._drift_sequence:
                post.total += 1
                post.correct += is_correct

            # Monitor channel (only events that received a monitor label)
            if event_id in self._monitor_labels:
                monitor.total += 1
                monitor.correct += is_correct

            # Selective channel (only events that received a selective label)
            if event_id in self._selective_labels:
                selective.total += 1
                selective.correct += is_correct

        # Score monitoring alerts independently against simulator truth
        mon_eval = None
        alerts_list = alerts or []
        if alerts is not None:
            mon_eval = self._evaluate_scenario_detections(alerts_list)

        return EvaluationMetrics(
            warmup_size=self._warmup_size,
            evaluation_start_sequence=start_seq,
            warmup_predictions=self._n_warmup,
            initialization_predictions=n_init,
            full_synthetic=full,
            pre_drift=pre if pre is not None else None,
            post_drift=post if post is not None else None,
            monitor_channel=monitor,
            selective_channel=selective,
            label_acquisition=label_acquisition or {},
            _explicit_label_acquisition_count=label_acquisition_count,
            monitoring_alerts=[a.to_dict() if hasattr(a, "to_dict") else a for a in alerts_list],
            monitoring_evaluation=mon_eval,
        )

    def get_all_predictions(self, start_sequence: Optional[int] = None) -> List[Dict]:
        """
        Return all post-initialization predictions with simulator truth attached.

        Each dict has: event_id, sequence, timestamp, predicted_label,
        predicted_proba, true_label (from simulator), correct,
        monitor_label (if acquired), selective_label (if acquired), features.

        Used for CSV export.
        """
        start_seq = (
            start_sequence
            if start_sequence is not None
            else (
                self._evaluation_start_sequence
                if self._evaluation_start_sequence is not None
                else self._warmup_size
            )
        )
        rows = []
        for event_id, pred in self._predictions.items():
            if pred.sequence < start_seq:
                continue
            true_label = self._simulator.get_hidden_label(event_id)
            row = {
                "event_id": pred.event_id,
                "sequence": pred.sequence,
                "timestamp": pred.timestamp,
                "model_version": getattr(pred, "model_version", "v1.0-frozen"),
                "predicted_label": pred.predicted_label,
                "predicted_proba": pred.predicted_proba,
                "true_label": true_label,
                "correct": int(pred.predicted_label == true_label),
                "monitor_acquired": 1 if event_id in self._monitor_labels else 0,
                "selective_acquired": 1 if event_id in self._selective_labels else 0,
            }
            for k, v in pred.features.items():
                row[f"feat_{k}"] = v
            rows.append(row)
        return sorted(rows, key=lambda r: r["sequence"])

    # Legacy method name — kept for backward compatibility with existing tests
    def get_scored_predictions(self) -> List[Dict]:
        """
        Backward-compatible alias for get_all_predictions().

        Returns the same structure. The ``true_label`` field now always
        contains the simulator truth (never None for post-warmup events).
        """
        return self.get_all_predictions()

    def compute_error_rate_from_records(self) -> Optional[float]:
        """
        Recompute error rate directly from saved records.

        Used in tests to verify that the evaluator's internal computation
        matches a naive re-calculation. Returns None if no post-warmup
        predictions exist.
        """
        rows = self.get_all_predictions()
        if not rows:
            return None
        correct_count = sum(r["correct"] for r in rows)
        return 1.0 - correct_count / len(rows)

    def _evaluate_scenario_detections(self, alerts_list: List[Any]) -> Dict[str, Any]:
        """
        Evaluate detector alarms against simulator ground truth with scenario-aware matching.
        """
        info = getattr(self._simulator, "evaluator_drift_info", {})
        scenario = info.get("scenario", "abrupt" if self._drift_sequence is not None else "stationary")
        total_alerts = len(alerts_list)
        first_alert = alerts_list[0] if alerts_list else None

        base_result: Dict[str, Any] = {
            "scenario": scenario,
            "total_alerts": total_alerts,
            "first_alert_event_sequence": first_alert.event_sequence if first_alert else None,
            "first_alert_arrival_sequence": first_alert.arrival_sequence if first_alert else None,
        }

        if scenario == "stationary":
            base_result.update({
                "false_alarms": total_alerts,
                "missed_detection": False,
                "detection_delay_events": None,
                "detection_delay_from_drift_event": None,
                "detection_delay_labeled_observations": None,
            })
            return base_result

        drift_start = info.get("drift_start_sequence", self._drift_sequence)
        if drift_start is None:
            base_result.update({
                "false_alarms": total_alerts,
                "missed_detection": False,
                "detection_delay_events": None,
                "detection_delay_from_drift_event": None,
                "detection_delay_labeled_observations": None,
            })
            return base_result

        # Identify pre-drift / early alarms
        pre_alerts = [a for a in alerts_list if a.event_sequence < drift_start]
        post_alerts = [a for a in alerts_list if a.event_sequence >= drift_start]
        base_result["false_alarms"] = len(pre_alerts)
        base_result["missed_detection"] = (len(post_alerts) == 0)

        first_post = post_alerts[0] if post_alerts else None
        if first_post:
            base_result["detection_delay_events"] = first_post.arrival_sequence - drift_start
            base_result["detection_delay_from_drift_event"] = first_post.event_sequence - drift_start
            base_result["detection_delay_labeled_observations"] = sum(
                1 for eid in self._monitor_labels.keys()
                if self._predictions[eid].sequence >= drift_start
                and (self._predictions[eid].sequence + self._simulator.label_delay <= first_post.arrival_sequence)
            )
        else:
            base_result["detection_delay_events"] = None
            base_result["detection_delay_from_drift_event"] = None
            base_result["detection_delay_labeled_observations"] = None

        if scenario == "gradual":
            onset = info.get("onset_sequence", drift_start)
            midpoint = info.get("midpoint_sequence", drift_start)
            completion = info.get("completion_sequence", drift_start)

            early_alerts = [a for a in alerts_list if a.event_sequence < onset]
            transition_alerts = [a for a in alerts_list if onset <= a.event_sequence <= completion]
            post_trans_alerts = [a for a in alerts_list if a.event_sequence > completion]

            base_result.update({
                "onset_sequence": onset,
                "midpoint_sequence": midpoint,
                "completion_sequence": completion,
                "early_alerts_count": len(early_alerts),
                "transition_alerts_count": len(transition_alerts),
                "post_transition_alerts_count": len(post_trans_alerts),
                "delay_from_onset_events": (first_post.arrival_sequence - onset) if first_post else None,
                "delay_from_midpoint_events": (first_post.arrival_sequence - midpoint) if first_post else None,
                "delay_from_completion_events": (first_post.arrival_sequence - completion) if first_post else None,
            })

        elif scenario == "recurring":
            transitions = info.get("transition_sequences", [drift_start])
            interval = info.get("recurrence_interval", 500)

            matched_transitions = {}
            duplicate_alerts = []
            boundary_crossing_alerts = []

            for a in post_alerts:
                # Find which transition regime k: [T_k, T_k+1)
                regime_k = (a.event_sequence - drift_start) // interval
                trans_seq = drift_start + regime_k * interval

                # Check if label arrival crossed into next regime
                arrival_regime_k = (a.arrival_sequence - drift_start) // interval
                if arrival_regime_k > regime_k:
                    boundary_crossing_alerts.append({
                        "event_sequence": a.event_sequence,
                        "arrival_sequence": a.arrival_sequence,
                        "event_regime": int(regime_k),
                        "arrival_regime": int(arrival_regime_k),
                    })

                if regime_k not in matched_transitions:
                    matched_transitions[int(regime_k)] = {
                        "transition_sequence": trans_seq,
                        "alert_event_sequence": a.event_sequence,
                        "alert_arrival_sequence": a.arrival_sequence,
                        "delay_events": a.arrival_sequence - trans_seq,
                    }
                else:
                    duplicate_alerts.append({
                        "event_sequence": a.event_sequence,
                        "arrival_sequence": a.arrival_sequence,
                        "regime": int(regime_k),
                    })

            missed_transitions = [
                k for k, t_seq in enumerate(transitions)
                if k not in matched_transitions
            ]

            base_result.update({
                "transition_sequences": transitions,
                "recurrence_interval": interval,
                "matched_transitions_count": len(matched_transitions),
                "matched_transitions": matched_transitions,
                "missed_transitions": missed_transitions,
                "duplicate_alerts_count": len(duplicate_alerts),
                "duplicate_alerts": duplicate_alerts,
                "boundary_crossing_alerts_count": len(boundary_crossing_alerts),
                "boundary_crossing_alerts": boundary_crossing_alerts,
            })

        elif scenario == "rare_region":
            base_result["rare_region_p"] = info.get("rare_region_p", 0.05)

        elif scenario == "adversary":
            base_result["adversary_dwell"] = info.get("adversary_dwell", 300)
            base_result["adversary_switches"] = info.get("adversary_switches", [])

        return base_result

