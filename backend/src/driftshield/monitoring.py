"""driftshield.monitoring
======================
Practical error-change monitoring using River ADWIN.

Design & Invariant Rules
------------------------
1. Input Source:
   ADWIN receives ONLY binary 0/1 losses from randomly sampled monitoring events
   (source in ("monitor", "both")) predicted AFTER model initialization and freezing.
   Selective-only labels (low-margin), hidden simulator truth, true drift schedules,
   and un-monitored predictions MUST NEVER be fed to the detector.

2. Exactly-Once Loss Computation:
   For each monitoring observation:
   - Retrieve the original locked-in prediction by event_id.
   - Join its legitimately delivered label.
   - Compute loss = int(predicted_label != true_label).
   - Update ADWIN exactly once. Duplicate deliveries are strictly rejected.

3. Temporal Order & Latency:
   Monitoring observations are fed in chronological arrival order.
   The event sequence and the label arrival sequence are tracked separately
   so that label delivery delay is visible in alert records.

4. Alert Semantics:
   Alerts represent statistical "evidence of error change" on the random-monitoring
   channel, not a universal guarantee or global false-alarm certificate.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

import river.drift

from .config import MonitoringConfig
from .contracts import DriftAlert, PredictionRecord


class ErrorChangeMonitor:
    """
    Online error-change detector wrapping River ADWIN.

    Parameters
    ----------
    config : MonitoringConfig
        ADWIN hyperparameters (delta, clock, max_buckets, min_window_length, grace_period).
    model_version : str
        Active model version tag (default: "v1.0-frozen").
    """

    def __init__(
        self,
        config: Optional[MonitoringConfig] = None,
        model_version: str = "v1.0-frozen",
    ) -> None:
        self.config = config or MonitoringConfig()
        self.model_version = model_version

        # Instantiate River ADWIN
        self._adwin = river.drift.ADWIN(
            delta=self.config.adwin_delta,
            clock=self.config.adwin_clock,
            max_buckets=self.config.adwin_max_buckets,
            min_window_length=self.config.adwin_min_window_length,
            grace_period=self.config.adwin_grace_period,
        )

        # Invariant enforcement and tracking
        self._processed_event_ids: Set[str] = set()
        self._monitoring_labels_count: int = 0
        self._total_evaluated_events_seen: int = 0
        self._alerts: List[DriftAlert] = []
        self._loss_history: List[Dict] = []

    @property
    def alerts(self) -> List[DriftAlert]:
        """List of all emitted drift alerts."""
        return list(self._alerts)

    @property
    def alerts_count(self) -> int:
        return len(self._alerts)

    @property
    def monitoring_labels_count(self) -> int:
        """Total number of random monitoring labels fed to ADWIN."""
        return self._monitoring_labels_count

    @property
    def total_evaluated_events_seen(self) -> int:
        return self._total_evaluated_events_seen

    @property
    def monitoring_coverage(self) -> float:
        """Proportion of evaluated post-freeze events that received random monitoring."""
        if self._total_evaluated_events_seen == 0:
            return 0.0
        return self._monitoring_labels_count / self._total_evaluated_events_seen

    @property
    def adwin_estimation(self) -> float:
        """Current estimated mean error rate inside ADWIN."""
        return float(self._adwin.estimation)

    @property
    def adwin_width(self) -> int:
        """Current window width of ADWIN."""
        return int(self._adwin.width)

    @property
    def adwin_variance(self) -> Optional[float]:
        """Current variance in ADWIN window if available."""
        var = getattr(self._adwin, "variance", None)
        return float(var) if var is not None else None

    @property
    def adwin_total(self) -> Optional[float]:
        """Cumulative sum in ADWIN window if available."""
        tot = getattr(self._adwin, "total", None)
        return float(tot) if tot is not None else None

    def register_evaluated_event(self, sequence: int) -> None:
        """Register that a post-freeze stream event occurred (for coverage tracking)."""
        self._total_evaluated_events_seen += 1

    def process_monitoring_label(
        self,
        event_id: str,
        event_sequence: int,
        arrival_sequence: int,
        original_prediction: PredictionRecord,
        true_label: int,
        source: str,
    ) -> Optional[DriftAlert]:
        """
        Process an acquired label.

        Only processes labels from the random monitoring channel ("monitor" or "both").
        Selective-only labels ("selective", "low_margin") and warm-up labels are ignored.

        Parameters
        ----------
        event_id : str
        event_sequence : int
        arrival_sequence : int
        original_prediction : PredictionRecord
            The original locked-in prediction for this event.
        true_label : int
        source : str
            Channel attribution from LabelAcquirer.

        Returns
        -------
        Optional[DriftAlert]
            DriftAlert if ADWIN detected an error change on this observation, else None.

        Raises
        ------
        ValueError
            If the same monitoring event is submitted more than once.
        """
        # Selective-only and warmup labels MUST NOT feed the error-change detector
        if source not in ("monitor", "both"):
            return None

        # Duplicate delivery prevention
        if event_id in self._processed_event_ids:
            raise ValueError(
                f"Duplicate monitoring label update for event_id '{event_id}'. "
                "Each monitoring observation must update ADWIN exactly once."
            )

        # Invariant check: prediction must match event_id
        if original_prediction.event_id != event_id:
            raise ValueError(
                f"Prediction event_id mismatch: expected '{event_id}', got '{original_prediction.event_id}'."
            )

        # Invariant check: warm-up predictions excluded
        if original_prediction.warmup:
            return None

        # Invariant check: delayed labels from older model versions must not update new ADWIN
        pred_version = getattr(original_prediction, "model_version", self.model_version)
        if pred_version != self.model_version:
            # Old-version label: scores its original model in evaluation, but does not feed new ADWIN
            return None

        # Compute binary 0/1 error loss on the original locked-in prediction
        loss = int(original_prediction.predicted_label != true_label)

        # Update ADWIN
        self._adwin.update(loss)
        self._processed_event_ids.add(event_id)
        self._monitoring_labels_count += 1

        self._loss_history.append({
            "event_id": event_id,
            "event_sequence": event_sequence,
            "arrival_sequence": arrival_sequence,
            "predicted_label": original_prediction.predicted_label,
            "true_label": true_label,
            "loss": loss,
            "adwin_estimation": self.adwin_estimation,
            "adwin_width": self.adwin_width,
            "model_version": self.model_version,
        })

        if self._adwin.drift_detected:
            alert = DriftAlert(
                alert_id=f"alert-{arrival_sequence}-{self.alerts_count + 1}",
                event_id=event_id,
                event_sequence=event_sequence,
                arrival_sequence=arrival_sequence,
                detection_delay_from_event=arrival_sequence - event_sequence,
                model_version=self.model_version,
                loss=loss,
                adwin_delta=self.config.adwin_delta,
                adwin_estimation=self.adwin_estimation,
                adwin_width=self.adwin_width,
                adwin_variance=self.adwin_variance,
                adwin_total=self.adwin_total,
                monitoring_labels_count=self._monitoring_labels_count,
                monitoring_coverage=self.monitoring_coverage,
                description="evidence of error change",
            )
            self._alerts.append(alert)
            return alert

        return None

    def reset(self, new_model_version: str, reset_sequence: int) -> None:
        """
        Reset the ADWIN detector for a newly promoted model version.

        Parameters
        ----------
        new_model_version : str
            Tag for the newly active model version (e.g. 'v2.0-promoted').
        reset_sequence : int
            Stream sequence at which promotion and detector reset occurred.
        """
        self.model_version = new_model_version
        self._adwin = river.drift.ADWIN(
            delta=self.config.adwin_delta,
            clock=self.config.adwin_clock,
            max_buckets=self.config.adwin_max_buckets,
            min_window_length=self.config.adwin_min_window_length,
            grace_period=self.config.adwin_grace_period,
        )

    def get_summary(self) -> dict:
        """Return diagnostic summary of monitor state."""
        return {
            "model_version": self.model_version,
            "adwin_config": self.config.model_dump(),
            "monitoring_labels_count": self._monitoring_labels_count,
            "total_evaluated_events_seen": self._total_evaluated_events_seen,
            "monitoring_coverage": self.monitoring_coverage,
            "current_adwin_estimation": self.adwin_estimation,
            "current_adwin_width": self.adwin_width,
            "current_adwin_variance": self.adwin_variance,
            "current_adwin_total": self.adwin_total,
            "alerts_count": self.alerts_count,
            "alerts": [a.to_dict() for a in self._alerts],
        }
