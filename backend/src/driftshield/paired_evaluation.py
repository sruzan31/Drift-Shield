"""driftshield.paired_evaluation
=============================
Fresh paired evaluation and statistical candidate promotion for DriftShield Phase 4B.

Design & Invariant Rules
------------------------
1. Evaluation Protocol:
   - Starts strictly AFTER candidate model training freezes (READY_FOR_EVALUATION).
   - Selects the first N (default: 500) fresh random-monitoring events predicted
     AFTER that freeze.
   - Both active and candidate predictions are recorded at event arrival BEFORE
     revealing the label.
   - Both models and preprocessing remain completely frozen during evaluation.
   - Evaluation events must NOT overlap candidate training events.
   - Selective-only (low-margin) labels CANNOT enter the paired comparison.
   - Evaluation set is selected by event sequence, not label-arrival speed.

2. Statistical Decision Rule:
   - b = count(active wrong, candidate correct)
   - c = count(active correct, candidate wrong)
   - n = all N paired observations (default: 500)
   - Gain = (b - c) / n.
   - One-sided exact binomial sign test:
     scipy.stats.binomtest(b, b + c, p=0.5, alternative="greater") when b + c > 0.
     If b + c == 0, p-value = 1.0 (no evidence of improvement).
   - Evaluate exactly once after all required labels arrive. No repeated peeking.
   - Promote ONLY when gain >= min_gain_threshold (0.02) AND p_value <= max_pvalue_threshold (0.01).
   - Otherwise reject and retain the active model.

3. Atomic Promotion & Lifecycle:
   - Model ownership switches atomically between events.
   - The next stream event prediction uses the new model version (e.g. 'v2.0-promoted').
   - Reset ADWIN detector for the promoted version.
   - Delayed labels continue scoring their original model versions in evaluation.
   - Old-version labels must not update the new version's ADWIN.
   - Preserves previous model artifacts and decision evidence.

4. Budget Allocation & Diagnostics:
   - Enforce at most 5 completed comparisons per run (0.01 per test * 5 = 0.05 family-wise error bound).
   - Under dependent or continuing-drift data, p-values are diagnostic.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import scipy.stats

from .config import AdaptationConfig
from .contracts import (
    CandidateState,
    EvaluationDecision,
    PairedEvaluationSummary,
    PairedPredictionRecord,
    StreamEvent,
)


class PairedEvaluationSession:
    """
    Manages one paired evaluation comparison between the active deployed model
    and a frozen candidate model over a target set of fresh random-monitoring events.

    Parameters
    ----------
    eval_id : str
        Unique identifier (e.g. 'eval-1').
    candidate_id : str
        Candidate model identifier.
    candidate_model : Any
        Frozen CandidateModel instance.
    active_model_version : str
        Version tag of the active model at evaluation start (e.g. 'v1.0-frozen').
    target_candidate_version : str
        Target version tag if promoted (e.g. 'v2.0-promoted').
    freeze_sequence : int
        Sequence at which the candidate completed training and froze.
    config : AdaptationConfig
    """

    def __init__(
        self,
        eval_id: str,
        candidate_id: str,
        candidate_model: Any,
        active_model_version: str,
        target_candidate_version: str,
        freeze_sequence: int,
        config: AdaptationConfig,
    ) -> None:
        self.eval_id = eval_id
        self.candidate_id = candidate_id
        self.candidate_model = candidate_model
        self.active_model_version = active_model_version
        self.target_candidate_version = target_candidate_version
        self.freeze_sequence = freeze_sequence
        self.config = config

        self.target_events_n: int = config.evaluation_target_events
        self.selection_start_sequence: int = freeze_sequence + 1
        self.selection_end_sequence: Optional[int] = None
        self.completion_sequence: Optional[int] = None

        self.selected_event_ids: List[str] = []
        self._selected_event_set: Set[str] = set()
        self.paired_records: Dict[str, PairedPredictionRecord] = {}
        self.delivered_labels: Dict[str, int] = {}

        self.decision: EvaluationDecision = EvaluationDecision.PENDING
        self.decision_reason: str = "Evaluation in progress"
        self.b: int = 0
        self.c: int = 0
        self.n: int = 0
        self.gain: Optional[float] = None
        self.p_value: Optional[float] = None
        self.cost_monitoring_labels_used: int = 0
        self.active_model_promoted_to: Optional[str] = None

    @property
    def is_selection_complete(self) -> bool:
        """True if the target number of fresh evaluation events have been selected."""
        return len(self.selected_event_ids) >= self.target_events_n

    @property
    def is_finished(self) -> bool:
        """True if a terminal decision (PROMOTED, REJECTED, INCOMPLETE) has been reached."""
        return self.decision != EvaluationDecision.PENDING

    def record_paired_event(
        self,
        event: StreamEvent,
        active_predicted_label: int,
        active_predicted_proba: float,
        is_random_monitor_selected: bool,
    ) -> Optional[PairedPredictionRecord]:
        """
        Record paired predictions at event arrival BEFORE revealing the label.

        Only selects fresh events strictly after freeze that were chosen by
        the random monitoring channel.

        Parameters
        ----------
        event : StreamEvent
        active_predicted_label : int
        active_predicted_proba : float
        is_random_monitor_selected : bool
            True if event was sampled by the random-monitoring channel.

        Returns
        -------
        Optional[PairedPredictionRecord]
            Record if selected into the evaluation set, else None.
        """
        if self.is_finished or self.is_selection_complete:
            return None

        # Must be strictly after freeze
        if event.sequence <= self.freeze_sequence:
            return None

        # Selective-only labels CANNOT enter the paired evaluation!
        if not is_random_monitor_selected:
            return None

        # Deduplication check
        if event.event_id in self._selected_event_set:
            return None

        # Predict candidate model on frozen features
        cand_proba = self.candidate_model.predict_proba_one(event.features)
        cand_label = int(cand_proba >= 0.5)

        record = PairedPredictionRecord(
            eval_id=self.eval_id,
            event_id=event.event_id,
            event_sequence=event.sequence,
            active_model_version=self.active_model_version,
            candidate_id=self.candidate_id,
            active_predicted_label=active_predicted_label,
            active_predicted_proba=active_predicted_proba,
            candidate_predicted_label=cand_label,
            candidate_predicted_proba=cand_proba,
            features=dict(event.features),
        )

        self.selected_event_ids.append(event.event_id)
        self._selected_event_set.add(event.event_id)
        self.paired_records[event.event_id] = record

        if len(self.selected_event_ids) == self.target_events_n:
            self.selection_end_sequence = event.sequence

        return record

    def deliver_label(
        self,
        event_id: str,
        true_label: int,
        delivery_sequence: int,
    ) -> Optional[EvaluationDecision]:
        """
        Deliver a ground-truth label for a selected evaluation event.

        Scores active vs candidate predictions and triggers evaluation once all
        target labels arrive.

        Returns
        -------
        Optional[EvaluationDecision]
            The decision if this delivery completed the evaluation set, else None.
        """
        if self.is_finished:
            return None

        if event_id not in self.paired_records:
            return None

        if event_id in self.delivered_labels:
            return None  # Already delivered

        rec = self.paired_records[event_id]
        rec.true_label = true_label
        rec.delivery_sequence = delivery_sequence
        rec.is_delivered = True

        active_correct = (rec.active_predicted_label == true_label)
        candidate_correct = (rec.candidate_predicted_label == true_label)
        rec.active_correct = active_correct
        rec.candidate_correct = candidate_correct

        if not active_correct and candidate_correct:
            rec.disagreement_type = "b_active_wrong_cand_correct"
        elif active_correct and not candidate_correct:
            rec.disagreement_type = "c_active_correct_cand_wrong"
        elif active_correct and candidate_correct:
            rec.disagreement_type = "both_correct"
        else:
            rec.disagreement_type = "both_wrong"

        self.delivered_labels[event_id] = true_label
        self.cost_monitoring_labels_used += 1

        # Check if all required evaluation labels have arrived
        if len(self.delivered_labels) == self.target_events_n:
            return self._evaluate_decision(current_sequence=delivery_sequence)

        return None

    def _evaluate_decision(self, current_sequence: int) -> EvaluationDecision:
        """
        Perform exact one-sided McNemar/binomial sign test and decide promotion.
        """
        if self.is_finished:
            return self.decision

        self.completion_sequence = current_sequence

        # Calculate b, c, n
        b = 0
        c = 0
        for rec in self.paired_records.values():
            if rec.is_delivered:
                if rec.disagreement_type == "b_active_wrong_cand_correct":
                    b += 1
                elif rec.disagreement_type == "c_active_correct_cand_wrong":
                    c += 1

        n = len(self.delivered_labels)
        self.b = b
        self.c = c
        self.n = n

        gain = (b - c) / n if n > 0 else 0.0
        self.gain = gain

        # Exact one-sided binomial sign test under H0: P(candidate correct | disagreement) <= 0.5
        if b + c > 0:
            res = scipy.stats.binomtest(b, b + c, p=0.5, alternative="greater")
            p_val = float(res.pvalue)
        else:
            p_val = 1.0  # Zero disagreements: no evidence of improvement

        self.p_value = p_val

        # Check promotion conditions
        min_gain = self.config.min_gain_threshold
        max_p = self.config.max_pvalue_threshold

        passes_gain = gain >= min_gain
        passes_p = p_val <= max_p

        if passes_gain and passes_p:
            self.decision = EvaluationDecision.PROMOTED
            self.active_model_promoted_to = self.target_candidate_version
            self.decision_reason = (
                f"PROMOTED: Observed gain={gain:.4f} >= {min_gain:.4f} "
                f"and p-value={p_val:.4e} <= {max_p:.4f} (b={b}, c={c}, n={n})."
            )
            self.candidate_model.transition_to(
                CandidateState.PROMOTED,
                sequence=current_sequence,
                reason=self.decision_reason,
            )
        else:
            self.decision = EvaluationDecision.REJECTED
            fail_reasons = []
            if not passes_gain:
                fail_reasons.append(f"gain {gain:.4f} < {min_gain:.4f}")
            if not passes_p:
                fail_reasons.append(f"p-value {p_val:.4e} > {max_p:.4f}")
            self.decision_reason = f"REJECTED: {', '.join(fail_reasons)} (b={b}, c={c}, n={n})."
            self.candidate_model.transition_to(
                CandidateState.REJECTED,
                sequence=current_sequence,
                reason=self.decision_reason,
            )

        return self.decision

    def check_timeout_or_finalize(self, current_sequence: int, is_stream_end: bool = False) -> Optional[EvaluationDecision]:
        """
        Check for timeout or stream completion without full evidence.
        """
        if self.is_finished:
            return None

        # Check configured timeout
        timed_out = False
        if self.config.evaluation_timeout_events is not None:
            if current_sequence - self.freeze_sequence >= self.config.evaluation_timeout_events:
                timed_out = True

        if timed_out or is_stream_end:
            self.decision = EvaluationDecision.INCOMPLETE
            self.completion_sequence = current_sequence
            self.decision_reason = (
                f"INCOMPLETE: Missing evidence ({len(self.delivered_labels)}/{self.target_events_n} labels arrived) "
                f"at sequence {current_sequence} ({'stream ended' if is_stream_end else 'timeout reached'}). No promotion."
            )
            self.candidate_model.transition_to(
                CandidateState.INCOMPLETE,
                sequence=current_sequence,
                reason=self.decision_reason,
            )
            return self.decision

        return None

    def to_summary(self) -> PairedEvaluationSummary:
        """Produce summary contract."""
        return PairedEvaluationSummary(
            eval_id=self.eval_id,
            candidate_id=self.candidate_id,
            active_model_version=self.active_model_version,
            target_candidate_version=self.target_candidate_version,
            freeze_sequence=self.freeze_sequence,
            selection_start_sequence=self.selection_start_sequence,
            selection_end_sequence=self.selection_end_sequence,
            completion_sequence=self.completion_sequence,
            target_events_n=self.target_events_n,
            selected_events_count=len(self.selected_event_ids),
            delivered_labels_count=len(self.delivered_labels),
            b=self.b,
            c=self.c,
            n=self.n,
            gain=self.gain,
            p_value=self.p_value,
            min_gain_threshold=self.config.min_gain_threshold,
            max_pvalue_threshold=self.config.max_pvalue_threshold,
            decision=self.decision.value,
            decision_reason=self.decision_reason,
            active_model_promoted_to=self.active_model_promoted_to,
            cost_monitoring_labels_used=self.cost_monitoring_labels_used,
            selected_event_ids=list(self.selected_event_ids),
        )


class PairedEvaluator:
    """
    Coordinates paired evaluation sessions and statistical promotions across a stream run.

    Enforces:
    - Maximum 5 completed comparisons per run.
    - Single active evaluation session.
    - Promotion callback for atomic model switching and ADWIN reset.
    """

    def __init__(
        self,
        config: Optional[AdaptationConfig] = None,
        on_promotion_callback: Optional[Callable[[PairedEvaluationSession], None]] = None,
    ) -> None:
        self.config = config or AdaptationConfig()
        self.on_promotion_callback = on_promotion_callback

        self.eval_counter: int = 0
        self.active_session: Optional[PairedEvaluationSession] = None
        self.completed_sessions: List[PairedEvaluationSession] = []

    @property
    def completed_comparisons_count(self) -> int:
        """Number of comparisons that reached a completed statistical decision (PROMOTED or REJECTED)."""
        return sum(
            1 for s in self.completed_sessions
            if s.decision in (EvaluationDecision.PROMOTED, EvaluationDecision.REJECTED)
        )

    @property
    def is_comparison_cap_reached(self) -> bool:
        """True if the 5-comparison cap has been reached."""
        return self.completed_comparisons_count >= self.config.max_comparisons

    def start_session(
        self,
        candidate_model: Any,
        active_model_version: str,
        current_sequence: int,
    ) -> Optional[PairedEvaluationSession]:
        """
        Start a fresh paired evaluation session for a frozen candidate.

        Returns None if comparison cap is reached or an evaluation is already active.
        """
        if self.is_comparison_cap_reached:
            return None

        if self.active_session is not None and not self.active_session.is_finished:
            return None

        self.eval_counter += 1
        eval_id = f"eval-{self.eval_counter}"
        target_version = f"v{self.eval_counter + 1}.0-promoted"

        # Transition candidate to EVALUATING
        candidate_model.transition_to(
            CandidateState.EVALUATING,
            sequence=current_sequence,
            reason=f"Started paired evaluation {eval_id} against active model {active_model_version}",
        )

        session = PairedEvaluationSession(
            eval_id=eval_id,
            candidate_id=candidate_model.candidate_id,
            candidate_model=candidate_model,
            active_model_version=active_model_version,
            target_candidate_version=target_version,
            freeze_sequence=current_sequence,
            config=self.config,
        )

        self.active_session = session
        return session

    def record_paired_event(
        self,
        event: StreamEvent,
        active_predicted_label: int,
        active_predicted_proba: float,
        is_random_monitor_selected: bool,
    ) -> Optional[PairedPredictionRecord]:
        """Forward event to active evaluation session."""
        if self.active_session is None or self.active_session.is_finished:
            return None
        return self.active_session.record_paired_event(
            event=event,
            active_predicted_label=active_predicted_label,
            active_predicted_proba=active_predicted_proba,
            is_random_monitor_selected=is_random_monitor_selected,
        )

    def deliver_label(
        self,
        event_id: str,
        true_label: int,
        delivery_sequence: int,
    ) -> Optional[EvaluationDecision]:
        """
        Forward delivered label to active evaluation session.
        If decision is reached and candidate is PROMOTED, triggers on_promotion_callback.
        """
        if self.active_session is None or self.active_session.is_finished:
            return None

        decision = self.active_session.deliver_label(
            event_id=event_id,
            true_label=true_label,
            delivery_sequence=delivery_sequence,
        )

        if decision is not None:
            self.completed_sessions.append(self.active_session)
            if decision == EvaluationDecision.PROMOTED and self.on_promotion_callback:
                self.on_promotion_callback(self.active_session)

        return decision

    def step(self, current_sequence: int) -> None:
        """Step checks (e.g. timeout)."""
        if self.active_session is not None and not self.active_session.is_finished:
            decision = self.active_session.check_timeout_or_finalize(current_sequence, is_stream_end=False)
            if decision is not None:
                self.completed_sessions.append(self.active_session)

    def finalize(self, last_sequence: int) -> None:
        """Finalize all pending evaluation sessions at stream termination."""
        if self.active_session is not None and not self.active_session.is_finished:
            decision = self.active_session.check_timeout_or_finalize(last_sequence, is_stream_end=True)
            if decision is not None and self.active_session not in self.completed_sessions:
                self.completed_sessions.append(self.active_session)

    def get_all_paired_records(self) -> List[PairedPredictionRecord]:
        """Collect all paired prediction records across evaluation sessions."""
        records: List[PairedPredictionRecord] = []
        for s in self.completed_sessions:
            records.extend(s.paired_records.values())
        if self.active_session is not None and self.active_session not in self.completed_sessions:
            records.extend(self.active_session.paired_records.values())
        return sorted(records, key=lambda r: r.event_sequence)

    def get_summary(self) -> Dict[str, Any]:
        """Diagnostic summary of paired evaluation."""
        sessions = list(self.completed_sessions)
        if self.active_session is not None and self.active_session not in sessions:
            sessions.append(self.active_session)

        return {
            "total_evaluations_started": self.eval_counter,
            "completed_comparisons_count": self.completed_comparisons_count,
            "max_comparisons_cap": self.config.max_comparisons,
            "comparison_cap_reached": self.is_comparison_cap_reached,
            "adaptation_config": self.config.model_dump(),
            "sessions": [s.to_summary().to_dict() for s in sessions],
        }

    def export(self, output_dir: Path, scenario: str) -> Tuple[Path, Path]:
        """Export paired evaluation CSV and summary JSON."""
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / f"{scenario}_paired_evaluation.csv"
        json_path = output_dir / f"{scenario}_paired_summary.json"

        # 1. Export CSV
        records = self.get_all_paired_records()
        fieldnames = [
            "eval_id",
            "event_id",
            "event_sequence",
            "active_model_version",
            "candidate_id",
            "active_predicted_label",
            "active_predicted_proba",
            "candidate_predicted_label",
            "candidate_predicted_proba",
            "true_label",
            "delivery_sequence",
            "is_delivered",
            "active_correct",
            "candidate_correct",
            "disagreement_type",
        ]
        # Include feature columns if available
        feat_keys = set()
        for r in records:
            feat_keys.update([f"feat_{k}" for k in r.features.keys()])
        fieldnames.extend(sorted(feat_keys))

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
