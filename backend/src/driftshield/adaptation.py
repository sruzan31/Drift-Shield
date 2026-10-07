"""driftshield.adaptation
======================
Candidate model training and lifecycle management after an error-change alert.

Design & Invariant Rules
------------------------
1. Initiation & Epoch Definition:
   An eligible ADWIN alert initiates one fresh River LogisticRegression candidate.
   The adaptation epoch is defined as the current event sequence when the alert
   became actionable (alert.arrival_sequence), NOT the older triggering event sequence.

2. Training Data Eligibility:
   Only authorized labels from events STRICTLY AFTER the epoch (event_sequence > epoch)
   may train the candidate.
   Delayed labels from earlier events (event_sequence <= epoch) continue to score
   their original predictions in evaluation, but MUST NEVER train the candidate.

3. Representation & State Invariance:
   The candidate reuses the run's frozen preprocessor (fitted during warm-up)
   without updating scaler statistics. The candidate classifier weights are
   initialized independently. The active deployed model remains frozen and unchanged.

4. Target & Freezing:
   The candidate trains until reaching a predeclared target of unique labels
   (default: 200 unique labels). Overlapping channel labels (monitor + selective)
   are deduplicated by event_id and count once.
   Upon reaching 200 labels, the candidate freezes and transitions to
   READY_FOR_EVALUATION.

5. Single-Candidate Concurrency:
   At most one candidate may train at any time. Additional alerts received
   during active training do not reset progress or create concurrent candidates.

6. Incomplete Runs:
   If the stream terminates or label budget is exhausted before reaching 200 labels,
   the candidate transitions to INCOMPLETE with exact recorded counts.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from river import linear_model, optim, preprocessing

from .config import AdaptationConfig
from .contracts import CandidateState, CandidateSummary, CandidateTrainingRecord, DriftAlert


class CandidateModel:
    """
    Individual candidate classifier undergoing post-alert training.

    Parameters
    ----------
    candidate_id : str
    active_model_version : str
    alert_id : str
    actionable_alert_sequence : int
        The arrival sequence at which the triggering alert occurred.
    epoch : int
        The adaptation boundary; only events with sequence > epoch are eligible for training.
    preprocessor : preprocessing.StandardScaler
        The run's frozen preprocessor.
    config : AdaptationConfig
    """

    def __init__(
        self,
        candidate_id: str,
        active_model_version: str,
        alert_id: str,
        actionable_alert_sequence: int,
        epoch: int,
        preprocessor: preprocessing.StandardScaler,
        config: AdaptationConfig,
    ) -> None:
        self.candidate_id = candidate_id
        self.active_model_version = active_model_version
        self.alert_id = alert_id
        self.actionable_alert_sequence = actionable_alert_sequence
        self.epoch = epoch
        self.preprocessor = preprocessor
        self.config = config
        self.target_training_labels = config.target_training_labels

        # Fresh River LogisticRegression initialized independently
        self._lr = linear_model.LogisticRegression(
            optimizer=optim.SGD(lr=config.learning_rate),
            l2=config.l2,
            intercept_lr=config.learning_rate,
        )

        self.state: CandidateState = CandidateState.TRAINING
        self.unique_training_labels: int = 0
        self.creation_sequence: int = actionable_alert_sequence
        self.freeze_sequence: Optional[int] = None
        self.is_frozen: bool = False

        self._trained_event_ids: Set[str] = set()
        self.training_records: List[CandidateTrainingRecord] = []
        self.state_transitions: List[Dict[str, Any]] = [
            {
                "from_state": CandidateState.IDLE.value,
                "to_state": CandidateState.TRAINING.value,
                "sequence": actionable_alert_sequence,
                "reason": f"Initiated by alert '{alert_id}' at sequence {actionable_alert_sequence}",
            }
        ]

    @property
    def weights(self) -> Dict[str, float]:
        """Dictionary of candidate model weights."""
        return dict(self._lr.weights)

    def transition_to(self, new_state: CandidateState, sequence: int, reason: str = "") -> None:
        """Record a state transition."""
        old_state = self.state
        self.state = new_state
        self.state_transitions.append({
            "from_state": old_state.value,
            "to_state": new_state.value,
            "sequence": sequence,
            "reason": reason,
        })

    def can_train_on(self, event_sequence: int, event_id: str) -> bool:
        """
        Check if an event is eligible for candidate training.

        Requirements:
        1. Candidate must be actively TRAINING.
        2. Event sequence must be strictly after epoch (event_sequence > epoch).
        3. Event ID must not have been trained already (deduplication).
        """
        if self.state != CandidateState.TRAINING or self.is_frozen:
            return False
        if event_sequence <= self.epoch:
            return False
        if event_id in self._trained_event_ids:
            return False
        return True

    def learn(
        self,
        event_id: str,
        event_sequence: int,
        arrival_sequence: int,
        features: Dict[str, float],
        true_label: int,
        source: str,
    ) -> bool:
        """
        Train the candidate on an eligible authorized label.

        Returns True if the label was absorbed, False otherwise.
        """
        if not self.can_train_on(event_sequence, event_id):
            return False

        # Scale features using frozen preprocessor
        scaled_x = self.preprocessor.transform_one(features)

        # Update candidate SGD weights
        self._lr.learn_one(scaled_x, true_label)
        self._trained_event_ids.add(event_id)
        self.unique_training_labels += 1

        record = CandidateTrainingRecord(
            candidate_id=self.candidate_id,
            event_id=event_id,
            event_sequence=event_sequence,
            arrival_sequence=arrival_sequence,
            true_label=true_label,
            source=source,
            cumulative_training_labels=self.unique_training_labels,
        )
        self.training_records.append(record)

        # Check for training completion
        if self.unique_training_labels >= self.target_training_labels:
            self.is_frozen = True
            self.freeze_sequence = arrival_sequence
            self.transition_to(
                CandidateState.READY_FOR_EVALUATION,
                sequence=arrival_sequence,
                reason=f"Reached target {self.target_training_labels} unique post-epoch training labels",
            )

        return True

    def predict_proba_one(self, features: Dict[str, float]) -> float:
        """Predict class-1 probability for features snapshot."""
        scaled_x = self.preprocessor.transform_one(features)
        proba = self._lr.predict_proba_one(scaled_x)
        return float(proba.get(1, 0.5) if proba else 0.5)

    def predict_one(self, features: Dict[str, float]) -> int:
        """Predict hard binary label (0 or 1) for features snapshot."""
        p1 = self.predict_proba_one(features)
        return int(p1 >= 0.5)

    def to_summary(self) -> CandidateSummary:
        """Generate summary contract."""
        return CandidateSummary(
            candidate_id=self.candidate_id,
            active_model_version=self.active_model_version,
            alert_id=self.alert_id,
            actionable_alert_sequence=self.actionable_alert_sequence,
            epoch=self.epoch,
            state=self.state.value,
            unique_training_labels=self.unique_training_labels,
            target_training_labels=self.target_training_labels,
            creation_sequence=self.creation_sequence,
            freeze_sequence=self.freeze_sequence,
            state_transitions=list(self.state_transitions),
            training_event_ids=[r.event_id for r in self.training_records],
        )


class CandidateManager:
    """
    Manages candidate training lifecycle across a stream run.

    Enforces:
    - Cooldown between candidate attempts.
    - Single active candidate policy (across TRAINING and EVALUATING states).
    - Post-epoch training data filtering.
    - Ignored alerts audit logging.
    """

    def __init__(
        self,
        config: Optional[AdaptationConfig] = None,
        preprocessor: Optional[preprocessing.StandardScaler] = None,
        active_model_version: str = "v1.0-frozen",
    ) -> None:
        self.config = config or AdaptationConfig()
        self.preprocessor = preprocessor or preprocessing.StandardScaler()
        self.active_model_version = active_model_version

        self.active_candidate: Optional[CandidateModel] = None
        self.completed_candidates: List[CandidateModel] = []
        self.candidate_counter: int = 0
        self.last_candidate_sequence: Optional[int] = None
        self.ignored_alerts_count: int = 0
        self.ignored_alerts: List[Dict[str, Any]] = []

    def handle_alert(
        self,
        alert: DriftAlert,
        current_sequence: int,
        is_cap_reached: bool = False,
    ) -> Optional[CandidateModel]:
        """
        Handle an error-change alert.

        If eligible, instantiates and starts a new candidate model.
        Logs reason for any ignored alert.
        """
        # Rule 1: Comparison cap check
        if is_cap_reached:
            self.ignored_alerts_count += 1
            self.ignored_alerts.append({
                "alert_id": alert.alert_id,
                "sequence": current_sequence,
                "reason": f"Comparison cap reached (max {self.config.max_comparisons} completed comparisons)",
            })
            return None

        # Rule 2: Single active candidate policy (active if TRAINING or EVALUATING)
        if self.active_candidate is not None and self.active_candidate.state in (
            CandidateState.TRAINING,
            CandidateState.READY_FOR_EVALUATION,
            CandidateState.EVALUATING,
        ):
            self.ignored_alerts_count += 1
            self.ignored_alerts.append({
                "alert_id": alert.alert_id,
                "sequence": current_sequence,
                "reason": f"Active candidate '{self.active_candidate.candidate_id}' in state {self.active_candidate.state.value}",
            })
            return None

        # Rule 3: Cooldown check
        if (
            self.last_candidate_sequence is not None
            and (current_sequence - self.last_candidate_sequence < self.config.cooldown_events)
        ):
            self.ignored_alerts_count += 1
            self.ignored_alerts.append({
                "alert_id": alert.alert_id,
                "sequence": current_sequence,
                "reason": f"Cooldown active ({current_sequence - self.last_candidate_sequence}/{self.config.cooldown_events} events)",
            })
            return None

        # Rule 4: Error threshold check
        if alert.adwin_estimation < self.config.min_error_rate_threshold:
            self.ignored_alerts_count += 1
            self.ignored_alerts.append({
                "alert_id": alert.alert_id,
                "sequence": current_sequence,
                "reason": f"ADWIN error rate {alert.adwin_estimation:.4f} < threshold {self.config.min_error_rate_threshold:.4f}",
            })
            return None

        # Start fresh candidate
        self.candidate_counter += 1
        candidate_id = f"cand-{self.candidate_counter}"
        epoch = alert.arrival_sequence  # current event sequence when alert became actionable

        candidate = CandidateModel(
            candidate_id=candidate_id,
            active_model_version=self.active_model_version,
            alert_id=alert.alert_id,
            actionable_alert_sequence=alert.arrival_sequence,
            epoch=epoch,
            preprocessor=self.preprocessor,
            config=self.config,
        )

        self.active_candidate = candidate
        self.last_candidate_sequence = current_sequence
        return candidate

    def train_step(
        self,
        event_id: str,
        event_sequence: int,
        arrival_sequence: int,
        features: Dict[str, float],
        true_label: int,
        source: str,
    ) -> bool:
        """
        Offer an authorized label to the active candidate for training.

        Returns True if the label was absorbed by candidate.
        """
        if self.active_candidate is None or self.active_candidate.state != CandidateState.TRAINING:
            return False

        absorbed = self.active_candidate.learn(
            event_id=event_id,
            event_sequence=event_sequence,
            arrival_sequence=arrival_sequence,
            features=features,
            true_label=true_label,
            source=source,
        )

        if self.active_candidate.state == CandidateState.READY_FOR_EVALUATION:
            if self.active_candidate not in self.completed_candidates:
                self.completed_candidates.append(self.active_candidate)

        return absorbed

    def on_candidate_promoted(self, new_model_version: str) -> None:
        """Update active model version following a successful promotion."""
        self.active_model_version = new_model_version
        self.active_candidate = None

    def on_candidate_rejected(self) -> None:
        """Reset active candidate reference following rejection."""
        self.active_candidate = None

    def finalize(self, last_sequence: int) -> None:
        """Finalize training at stream termination."""
        if self.active_candidate is not None and self.active_candidate.state == CandidateState.TRAINING:
            self.active_candidate.transition_to(
                CandidateState.INCOMPLETE,
                sequence=last_sequence,
                reason=(
                    f"Stream ended at sequence {last_sequence} with "
                    f"{self.active_candidate.unique_training_labels}/{self.active_candidate.target_training_labels} labels"
                ),
            )
            if self.active_candidate not in self.completed_candidates:
                self.completed_candidates.append(self.active_candidate)

    def get_all_training_records(self) -> List[CandidateTrainingRecord]:
        """Collect all training step records across candidates."""
        records: List[CandidateTrainingRecord] = []
        for cand in self.completed_candidates:
            records.extend(cand.training_records)
        if self.active_candidate is not None and self.active_candidate not in self.completed_candidates:
            records.extend(self.active_candidate.training_records)
        return records

    def get_summary(self) -> Dict[str, Any]:
        """Return full diagnostic summary of candidate management."""
        cands = list(self.completed_candidates)
        if self.active_candidate is not None and self.active_candidate not in cands:
            cands.append(self.active_candidate)

        return {
            "total_candidates_spawned": self.candidate_counter,
            "active_model_version": self.active_model_version,
            "ignored_alerts_count": self.ignored_alerts_count,
            "ignored_alerts": self.ignored_alerts,
            "adaptation_config": self.config.model_dump(),
            "candidates": [c.to_summary().to_dict() for c in cands],
        }

    def export(self, output_dir: Path, scenario: str) -> Tuple[Path, Path]:
        """Export candidate training CSV and summary JSON."""
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / f"{scenario}_candidate_training.csv"
        json_path = output_dir / f"{scenario}_candidate_summary.json"

        # 1. Export CSV
        records = self.get_all_training_records()
        fieldnames = [
            "candidate_id",
            "event_id",
            "event_sequence",
            "arrival_sequence",
            "true_label",
            "source",
            "cumulative_training_labels",
        ]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in records:
                writer.writerow(r.to_dict())

        # 2. Export JSON
        summary_dict = self.get_summary()
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary_dict, f, indent=2)

        return csv_path, json_path
