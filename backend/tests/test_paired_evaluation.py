"""backend/tests/test_paired_evaluation.py
======================================
Tests for Phase 4B: Fresh paired evaluation and statistical candidate promotion.

Coverage includes:
1. Prediction-before-label and training/evaluation separation.
2. Random-channel-only selection and exact 500-event (or configured N) set.
3. Delayed labels and timeout without promotion (INCOMPLETE).
4. Duplicate label handling and zero-disagreement case (b + c = 0).
5. Both promotion conditions (gain >= 0.02 and p-value <= 0.01) and rejection cases.
6. One decision evaluated exactly once without repeated peeking.
7. Next-event atomic model switching and detector reset.
8. Old-version labels excluded from new-version monitoring.
9. Comparison cap (max 5 completed comparisons) and export consistency.
"""

import json
from pathlib import Path
import pytest
from river import linear_model, optim, preprocessing
import scipy.stats

from driftshield.adaptation import CandidateManager, CandidateModel
from driftshield.baseline import BaselineClassifier
from driftshield.config import AdaptationConfig, LabelConfig, MonitoringConfig
from driftshield.contracts import (
    CandidateState,
    EvaluationDecision,
    PairedPredictionRecord,
    PredictionRecord,
    StreamEvent,
)
from driftshield.monitoring import ErrorChangeMonitor
from driftshield.paired_evaluation import PairedEvaluationSession, PairedEvaluator


def create_dummy_candidate(
    candidate_id: str = "cand-1",
    epoch: int = 100,
    active_version: str = "v1.0-frozen",
    target_labels: int = 5,
) -> CandidateModel:
    """Helper to create a frozen candidate model ready for evaluation."""
    scaler = preprocessing.StandardScaler()
    scaler.learn_one({"f0": 0.0, "f1": 0.0})
    cfg = AdaptationConfig(target_training_labels=target_labels, evaluation_target_events=10)
    cand = CandidateModel(
        candidate_id=candidate_id,
        active_model_version=active_version,
        alert_id="alert-1",
        actionable_alert_sequence=epoch,
        epoch=epoch,
        preprocessor=scaler,
        config=cfg,
    )
    # Train dummy candidate to freeze
    for i in range(1, target_labels + 1):
        cand.learn(
            event_id=f"evt-{epoch + i}",
            event_sequence=epoch + i,
            arrival_sequence=epoch + i,
            features={"f0": float(i), "f1": float(i)},
            true_label=1,
            source="monitor",
        )
    assert cand.state == CandidateState.READY_FOR_EVALUATION
    return cand


# ---------------------------------------------------------------------------
# 1. Prediction-Before-Label and Training/Evaluation Separation
# ---------------------------------------------------------------------------


def test_prediction_before_label_and_separation():
    """Verify paired predictions are locked in before labels arrive and training events don't overlap."""
    cand = create_dummy_candidate(epoch=100, target_labels=5)
    cfg = AdaptationConfig(evaluation_target_events=5)
    session = PairedEvaluationSession(
        eval_id="eval-1",
        candidate_id=cand.candidate_id,
        candidate_model=cand,
        active_model_version="v1.0-frozen",
        target_candidate_version="v2.0-promoted",
        freeze_sequence=105,
        config=cfg,
    )

    # Event before or at freeze sequence is rejected
    ev_old = StreamEvent(event_id="evt-105", sequence=105, timestamp=0.0, features={"f0": 1.0, "f1": 1.0})
    assert session.record_paired_event(ev_old, active_predicted_label=0, active_predicted_proba=0.1, is_random_monitor_selected=True) is None

    # Event after freeze sequence is accepted
    ev_fresh = StreamEvent(event_id="evt-106", sequence=106, timestamp=0.0, features={"f0": 1.0, "f1": 1.0})
    rec = session.record_paired_event(ev_fresh, active_predicted_label=0, active_predicted_proba=0.2, is_random_monitor_selected=True)
    assert rec is not None
    assert rec.event_id == "evt-106"
    assert rec.active_predicted_label == 0
    assert rec.true_label is None
    assert not rec.is_delivered


# ---------------------------------------------------------------------------
# 2. Random-Channel-Only Selection and Exact Target Count
# ---------------------------------------------------------------------------


def test_random_channel_only_and_exact_target():
    """Verify selective-only events cannot enter paired evaluation and selection stops at target N."""
    cand = create_dummy_candidate(epoch=100, target_labels=5)
    cfg = AdaptationConfig(evaluation_target_events=3)
    session = PairedEvaluationSession(
        eval_id="eval-1",
        candidate_id=cand.candidate_id,
        candidate_model=cand,
        active_model_version="v1.0-frozen",
        target_candidate_version="v2.0-promoted",
        freeze_sequence=105,
        config=cfg,
    )

    # 1. Selective channel event is rejected
    ev1 = StreamEvent(event_id="evt-106", sequence=106, timestamp=0.0, features={"f0": 1.0, "f1": 1.0})
    assert session.record_paired_event(ev1, 0, 0.4, is_random_monitor_selected=False) is None

    # 2. Random monitor events are accepted
    assert session.record_paired_event(ev1, 0, 0.4, is_random_monitor_selected=True) is not None
    ev2 = StreamEvent(event_id="evt-107", sequence=107, timestamp=0.0, features={"f0": 2.0, "f1": 2.0})
    ev3 = StreamEvent(event_id="evt-108", sequence=108, timestamp=0.0, features={"f0": 3.0, "f1": 3.0})
    assert session.record_paired_event(ev2, 0, 0.4, is_random_monitor_selected=True) is not None
    assert session.record_paired_event(ev3, 0, 0.4, is_random_monitor_selected=True) is not None

    # Exactly 3 events selected
    assert session.is_selection_complete
    assert len(session.selected_event_ids) == 3
    assert session.selection_end_sequence == 108

    # 4th event is rejected because target count reached
    ev4 = StreamEvent(event_id="evt-109", sequence=109, timestamp=0.0, features={"f0": 4.0, "f1": 4.0})
    assert session.record_paired_event(ev4, 0, 0.4, is_random_monitor_selected=True) is None


# ---------------------------------------------------------------------------
# 3. Delayed Labels and Timeout Without Promotion (INCOMPLETE)
# ---------------------------------------------------------------------------


def test_delayed_labels_and_timeout_incomplete():
    """Verify missing labels or timeout causes INCOMPLETE decision with no promotion."""
    cand = create_dummy_candidate(epoch=100, target_labels=5)
    cfg = AdaptationConfig(evaluation_target_events=3, evaluation_timeout_events=20)
    session = PairedEvaluationSession(
        eval_id="eval-1",
        candidate_id=cand.candidate_id,
        candidate_model=cand,
        active_model_version="v1.0-frozen",
        target_candidate_version="v2.0-promoted",
        freeze_sequence=105,
        config=cfg,
    )

    # Select 3 events
    for seq in (106, 107, 108):
        ev = StreamEvent(event_id=f"evt-{seq}", sequence=seq, timestamp=0.0, features={"f0": 1.0, "f1": 1.0})
        session.record_paired_event(ev, 0, 0.5, is_random_monitor_selected=True)

    # Only 1 label delivered with delay
    session.deliver_label("evt-106", true_label=1, delivery_sequence=116)

    # Check timeout at seq 130 (130 - 105 = 25 >= 20)
    dec = session.check_timeout_or_finalize(current_sequence=130, is_stream_end=False)
    assert dec == EvaluationDecision.INCOMPLETE
    assert session.decision == EvaluationDecision.INCOMPLETE
    assert cand.state == CandidateState.INCOMPLETE
    assert session.active_model_promoted_to is None


# ---------------------------------------------------------------------------
# 4. Duplicate Labels and Zero-Disagreement Case (b + c = 0)
# ---------------------------------------------------------------------------


def test_duplicate_labels_and_zero_disagreement():
    """Verify duplicate labels are ignored and zero-disagreement (b+c=0) gives p=1.0 and REJECTED."""
    cand = create_dummy_candidate(epoch=100, target_labels=5)
    cfg = AdaptationConfig(evaluation_target_events=2, min_gain_threshold=0.02, max_pvalue_threshold=0.01)
    session = PairedEvaluationSession(
        eval_id="eval-1",
        candidate_id=cand.candidate_id,
        candidate_model=cand,
        active_model_version="v1.0-frozen",
        target_candidate_version="v2.0-promoted",
        freeze_sequence=105,
        config=cfg,
    )

    # Active and candidate make identical predictions
    ev1 = StreamEvent(event_id="evt-106", sequence=106, timestamp=0.0, features={"f0": 1.0, "f1": 1.0})
    ev2 = StreamEvent(event_id="evt-107", sequence=107, timestamp=0.0, features={"f0": 2.0, "f1": 2.0})
    session.record_paired_event(ev1, active_predicted_label=1, active_predicted_proba=0.8, is_random_monitor_selected=True)
    session.record_paired_event(ev2, active_predicted_label=1, active_predicted_proba=0.8, is_random_monitor_selected=True)

    # Deliver label 1
    session.deliver_label("evt-106", true_label=1, delivery_sequence=106)

    # Duplicate delivery of label 1 is ignored
    assert session.deliver_label("evt-106", true_label=1, delivery_sequence=106) is None

    # Deliver label 2 -> both models correct on both -> b=0, c=0
    dec = session.deliver_label("evt-107", true_label=1, delivery_sequence=107)
    assert dec == EvaluationDecision.REJECTED
    assert session.b == 0
    assert session.c == 0
    assert session.n == 2
    assert session.gain == 0.0
    assert session.p_value == 1.0
    assert cand.state == CandidateState.REJECTED


# ---------------------------------------------------------------------------
# 5. Controlled Fixtures: Both Promotion and Rejection Conditions
# ---------------------------------------------------------------------------


def test_promotion_and_rejection_criteria():
    """Unit fixture testing exact binomial test: gain >= 0.02 and p <= 0.01 for promotion vs rejection."""
    # Case A: Promotion (e.g. b=25, c=5, n=500 -> gain = (25-5)/500 = 0.04 >= 0.02, p-val = binomtest(25, 30, 0.5) = 0.00016 <= 0.01)
    cand_prom = create_dummy_candidate(candidate_id="cand-prom", epoch=100, target_labels=5)
    cfg_prom = AdaptationConfig(
        evaluation_target_events=500,
        min_gain_threshold=0.02,
        max_pvalue_threshold=0.01,
    )
    sess_prom = PairedEvaluationSession(
        eval_id="eval-prom",
        candidate_id=cand_prom.candidate_id,
        candidate_model=cand_prom,
        active_model_version="v1.0-frozen",
        target_candidate_version="v2.0-promoted",
        freeze_sequence=105,
        config=cfg_prom,
    )

    # Synthesize 500 events
    for i in range(1, 501):
        seq = 105 + i
        ev = StreamEvent(event_id=f"evt-{seq}", sequence=seq, timestamp=0.0, features={"f0": 1.0, "f1": 1.0})
        sess_prom.record_paired_event(ev, active_predicted_label=0, active_predicted_proba=0.1, is_random_monitor_selected=True)

    # Deliver labels such that b=25, c=5, and 470 both correct
    for i in range(1, 501):
        seq = 105 + i
        rec = sess_prom.paired_records[f"evt-{seq}"]
        if i <= 25:
            # Active wrong (0), candidate correct (1) -> b
            rec.candidate_predicted_label = 1
            true_lbl = 1
        elif i <= 30:
            # Active correct (0), candidate wrong (1) -> c
            rec.candidate_predicted_label = 1
            true_lbl = 0
        else:
            # Both wrong (0 != 1)
            rec.candidate_predicted_label = 0
            true_lbl = 1
        sess_prom.deliver_label(f"evt-{seq}", true_label=true_lbl, delivery_sequence=seq)

    assert sess_prom.decision == EvaluationDecision.PROMOTED
    assert sess_prom.b == 25
    assert sess_prom.c == 5
    assert sess_prom.n == 500
    assert sess_prom.gain == pytest.approx(0.04)
    assert sess_prom.p_value < 0.001
    assert cand_prom.state == CandidateState.PROMOTED
    assert sess_prom.active_model_promoted_to == "v2.0-promoted"

    # Case B: Rejection due to low gain (b=6, c=0, n=500 -> gain = 6/500 = 0.012 < 0.02 even though p=0.015)
    cand_rej = create_dummy_candidate(candidate_id="cand-rej", epoch=100, target_labels=5)
    sess_rej = PairedEvaluationSession(
        eval_id="eval-rej",
        candidate_id=cand_rej.candidate_id,
        candidate_model=cand_rej,
        active_model_version="v1.0-frozen",
        target_candidate_version="v2.0-promoted",
        freeze_sequence=105,
        config=cfg_prom,
    )
    for i in range(1, 501):
        seq = 105 + i
        ev = StreamEvent(event_id=f"evt-{seq}", sequence=seq, timestamp=0.0, features={"f0": 1.0, "f1": 1.0})
        sess_rej.record_paired_event(ev, active_predicted_label=0, active_predicted_proba=0.1, is_random_monitor_selected=True)

    for i in range(1, 501):
        seq = 105 + i
        rec = sess_rej.paired_records[f"evt-{seq}"]
        if i <= 6:
            rec.candidate_predicted_label = 1
            true_lbl = 1  # b=6
        else:
            rec.candidate_predicted_label = 0
            true_lbl = 0  # both correct
        sess_rej.deliver_label(f"evt-{seq}", true_label=true_lbl, delivery_sequence=seq)

    assert sess_rej.decision == EvaluationDecision.REJECTED
    assert sess_rej.gain < 0.02
    assert cand_rej.state == CandidateState.REJECTED


# ---------------------------------------------------------------------------
# 6. One Decision Without Repeated Peeking
# ---------------------------------------------------------------------------


def test_one_decision_no_repeated_peeking():
    """Verify evaluation decision is evaluated exactly once after all N labels arrive."""
    cand = create_dummy_candidate(epoch=100, target_labels=5)
    cfg = AdaptationConfig(evaluation_target_events=3)
    session = PairedEvaluationSession(
        eval_id="eval-1",
        candidate_id=cand.candidate_id,
        candidate_model=cand,
        active_model_version="v1.0-frozen",
        target_candidate_version="v2.0-promoted",
        freeze_sequence=105,
        config=cfg,
    )

    for seq in (106, 107, 108):
        ev = StreamEvent(event_id=f"evt-{seq}", sequence=seq, timestamp=0.0, features={"f0": 1.0, "f1": 1.0})
        session.record_paired_event(ev, active_predicted_label=0, active_predicted_proba=0.5, is_random_monitor_selected=True)

    # Deliver 1st and 2nd labels: decision is still PENDING (no early peeking)
    assert session.deliver_label("evt-106", true_label=1, delivery_sequence=106) is None
    assert session.decision == EvaluationDecision.PENDING
    assert session.deliver_label("evt-107", true_label=1, delivery_sequence=107) is None
    assert session.decision == EvaluationDecision.PENDING

    # Deliver 3rd label: decision evaluated
    dec = session.deliver_label("evt-108", true_label=1, delivery_sequence=108)
    assert dec is not None
    assert session.decision != EvaluationDecision.PENDING


# ---------------------------------------------------------------------------
# 7. Next-Event Model Switching and Detector Reset
# ---------------------------------------------------------------------------


def test_atomic_model_switching_and_detector_reset():
    """Verify BaselineClassifier switches to promoted candidate and ErrorChangeMonitor resets."""
    baseline = BaselineClassifier(LabelConfig(warmup_size=10))
    monitor = ErrorChangeMonitor(MonitoringConfig(), model_version="v1.0-frozen")

    # Fit warm-up
    for i in range(10):
        ev = StreamEvent(event_id=f"evt-{i}", sequence=i, timestamp=0.0, features={"f0": float(i), "f1": float(i)})
        baseline.register_warmup_features(ev)
        baseline.learn(ev.event_id, 0)
    baseline.freeze()

    assert baseline.model_version == "v1.0-frozen"
    assert monitor.model_version == "v1.0-frozen"

    # Candidate trained on post-drift data
    cand = create_dummy_candidate(candidate_id="cand-1", epoch=10, target_labels=5)

    # Setup PairedEvaluator with promotion callback
    def on_promotion(session: PairedEvaluationSession):
        baseline.promote_candidate(
            candidate_lr_model=session.candidate_model._lr,
            new_model_version=session.target_candidate_version,
        )
        monitor.reset(
            new_model_version=session.target_candidate_version,
            reset_sequence=session.completion_sequence or 0,
        )

    evaluator = PairedEvaluator(AdaptationConfig(evaluation_target_events=2), on_promotion_callback=on_promotion)
    session = evaluator.start_session(cand, active_model_version=baseline.model_version, current_sequence=15)

    # Record 2 events
    ev16 = StreamEvent(event_id="evt-16", sequence=16, timestamp=0.0, features={"f0": 10.0, "f1": 10.0})
    ev17 = StreamEvent(event_id="evt-17", sequence=17, timestamp=0.0, features={"f0": 10.0, "f1": 10.0})
    evaluator.record_paired_event(ev16, active_predicted_label=0, active_predicted_proba=0.1, is_random_monitor_selected=True)
    evaluator.record_paired_event(ev17, active_predicted_label=0, active_predicted_proba=0.1, is_random_monitor_selected=True)

    # Force candidate to predict 1
    session.paired_records["evt-16"].candidate_predicted_label = 1
    session.paired_records["evt-17"].candidate_predicted_label = 1

    # Deliver labels -> both are 1 -> b=2, c=0 -> gain=1.0, p=0.25 <= 0.5 (for target 2 with threshold adjusted)
    # Let's check config threshold
    evaluator.config.min_gain_threshold = 0.02
    evaluator.config.max_pvalue_threshold = 0.5
    evaluator.deliver_label("evt-16", true_label=1, delivery_sequence=16)
    dec = evaluator.deliver_label("evt-17", true_label=1, delivery_sequence=17)

    assert dec == EvaluationDecision.PROMOTED
    assert baseline.model_version == "v2.0-promoted"
    assert monitor.model_version == "v2.0-promoted"

    # Next event predicted by baseline uses the new version tag
    ev18 = StreamEvent(event_id="evt-18", sequence=18, timestamp=0.0, features={"f0": 10.0, "f1": 10.0})
    pred18 = baseline.predict(ev18)
    assert pred18.model_version == "v2.0-promoted"


# ---------------------------------------------------------------------------
# 8. Old-Version Labels Excluded from New-Version Monitoring
# ---------------------------------------------------------------------------


def test_old_version_labels_excluded_from_new_monitor():
    """Verify delayed labels from old model versions do not update the reset ADWIN."""
    monitor = ErrorChangeMonitor(MonitoringConfig(), model_version="v2.0-promoted")

    # Delayed prediction from v1.0-frozen
    pred_old = PredictionRecord(
        event_id="evt-10",
        sequence=10,
        timestamp=0.0,
        predicted_label=0,
        predicted_proba=0.1,
        features={"f0": 1.0, "f1": 1.0},
        model_version="v1.0-frozen",
    )

    alert = monitor.process_monitoring_label(
        event_id="evt-10",
        event_sequence=10,
        arrival_sequence=25,
        original_prediction=pred_old,
        true_label=1,
        source="monitor",
    )
    # Ignored because model_version does not match active v2.0-promoted
    assert alert is None
    assert monitor.monitoring_labels_count == 0


# ---------------------------------------------------------------------------
# 9. Comparison Cap and Export Consistency
# ---------------------------------------------------------------------------


def test_comparison_cap_and_export(tmp_path: Path):
    """Verify comparison cap of at most 5 comparisons and export file consistency."""
    cfg = AdaptationConfig(max_comparisons=2, evaluation_target_events=2)
    evaluator = PairedEvaluator(config=cfg)

    # 1st comparison
    cand1 = create_dummy_candidate(candidate_id="cand-1", epoch=10, target_labels=2)
    s1 = evaluator.start_session(cand1, "v1.0-frozen", current_sequence=12)
    ev1 = StreamEvent(event_id="evt-13", sequence=13, timestamp=0.0, features={"f0": 1.0, "f1": 1.0})
    ev2 = StreamEvent(event_id="evt-14", sequence=14, timestamp=0.0, features={"f0": 1.0, "f1": 1.0})
    evaluator.record_paired_event(ev1, 0, 0.5, is_random_monitor_selected=True)
    evaluator.record_paired_event(ev2, 0, 0.5, is_random_monitor_selected=True)
    evaluator.deliver_label("evt-13", true_label=0, delivery_sequence=13)
    evaluator.deliver_label("evt-14", true_label=0, delivery_sequence=14)
    assert evaluator.completed_comparisons_count == 1

    # 2nd comparison
    cand2 = create_dummy_candidate(candidate_id="cand-2", epoch=20, target_labels=2)
    s2 = evaluator.start_session(cand2, "v1.0-frozen", current_sequence=22)
    ev3 = StreamEvent(event_id="evt-23", sequence=23, timestamp=0.0, features={"f0": 1.0, "f1": 1.0})
    ev4 = StreamEvent(event_id="evt-24", sequence=24, timestamp=0.0, features={"f0": 1.0, "f1": 1.0})
    evaluator.record_paired_event(ev3, 0, 0.5, is_random_monitor_selected=True)
    evaluator.record_paired_event(ev4, 0, 0.5, is_random_monitor_selected=True)
    evaluator.deliver_label("evt-23", true_label=0, delivery_sequence=23)
    evaluator.deliver_label("evt-24", true_label=0, delivery_sequence=24)
    assert evaluator.completed_comparisons_count == 2
    assert evaluator.is_comparison_cap_reached

    # 3rd comparison attempt is rejected due to cap
    cand3 = create_dummy_candidate(candidate_id="cand-3", epoch=30, target_labels=2)
    assert evaluator.start_session(cand3, "v1.0-frozen", current_sequence=32) is None

    # Test export
    csv_path, json_path = evaluator.export(tmp_path, "test_scenario")
    assert csv_path.exists()
    assert json_path.exists()

    with open(json_path, "r", encoding="utf-8") as f:
        summary_data = json.load(f)
    assert summary_data["completed_comparisons_count"] == 2
    assert summary_data["comparison_cap_reached"] is True
    assert len(summary_data["sessions"]) == 2


# ---------------------------------------------------------------------------
# 10. Delayed Candidate Training Delivery Boundary Verification
# ---------------------------------------------------------------------------


def test_delayed_candidate_training_delivery_boundary():
    """
    Verify that with delay=10 and epoch=1657:
    - Pre-epoch events (<= 1657) arriving at or after sequence 1657 are strictly rejected.
    - Earliest eligible event sequence is 1658.
    - Earliest eligible label arrival sequence for training is 1658 + 10 = 1668.
    """
    scaler = preprocessing.StandardScaler()
    scaler.learn_one({"f0": 0.0, "f1": 0.0})
    cand = CandidateModel(
        candidate_id="cand-test-boundary",
        active_model_version="v1.0-frozen",
        alert_id="alert-1657",
        actionable_alert_sequence=1657,
        epoch=1657,
        preprocessor=scaler,
        config=AdaptationConfig(target_training_labels=5),
    )

    # 1. Delayed pre-epoch label arriving at seq 1660 (event seq 1650 <= 1657) -> Rejected
    assert not cand.can_train_on(event_sequence=1650, event_id="evt-1650")
    absorbed_old = cand.learn(
        event_id="evt-1650",
        event_sequence=1650,
        arrival_sequence=1660,
        features={"f0": 1.0, "f1": 1.0},
        true_label=1,
        source="monitor",
    )
    assert not absorbed_old
    assert cand.unique_training_labels == 0

    # 2. Delayed label for triggering event seq 1657 arriving at seq 1667 -> Rejected
    assert not cand.can_train_on(event_sequence=1657, event_id="evt-1657")
    absorbed_epoch = cand.learn(
        event_id="evt-1657",
        event_sequence=1657,
        arrival_sequence=1667,
        features={"f0": 1.0, "f1": 1.0},
        true_label=1,
        source="monitor",
    )
    assert not absorbed_epoch
    assert cand.unique_training_labels == 0

    # 3. Earliest possible post-epoch event seq 1658 arriving at seq 1668 (1658 + 10) -> Accepted!
    assert cand.can_train_on(event_sequence=1658, event_id="evt-1658")
    absorbed_first = cand.learn(
        event_id="evt-1658",
        event_sequence=1658,
        arrival_sequence=1668,
        features={"f0": 1.0, "f1": 1.0},
        true_label=1,
        source="monitor",
    )
    assert absorbed_first
    assert cand.unique_training_labels == 1
    assert cand.training_records[0].event_sequence == 1658
    assert cand.training_records[0].arrival_sequence == 1668


class TestPromotionIntegrityRegression:
    """Regression tests for promotion sequence limits and model version transitions."""

    def test_promotion_cannot_occur_after_stream_end(self, tmp_path: Path) -> None:
        """In a 5000-event run where evaluation requires 5572 events, no promotion occurs."""
        from driftshield.config import DriftShieldConfig, LabelConfig, StreamConfig
        from driftshield.engine import DriftShieldEngine
        from driftshield.simulator import Simulator
        from driftshield.storage import SQLiteStorage

        cfg = DriftShieldConfig(
            stream=StreamConfig(scenario="abrupt", n_events=5000, drift_start_sequence=1000, seed=42),
            labels=LabelConfig(warmup_size=200, label_budget=1000, monitor_rate=0.15, label_delay=0),
            adaptation=AdaptationConfig(target_training_labels=200, evaluation_target_events=500),
            output_dir=str(tmp_path),
        )
        storage = SQLiteStorage(db_path=tmp_path / "test_int.db", artifacts_dir=tmp_path / "artifacts")
        sim = Simulator(cfg.stream)
        engine = DriftShieldEngine(config=cfg, storage=storage)
        engine.initialize(simulator=sim)

        for event in sim.iter_events():
            engine.process_event(event)

        summary = engine.finalize()

        # At event 5000, promotion should NOT have occurred
        assert summary.active_model_version == "v1.0-frozen"
        cand = summary.candidate_summary["candidates"][0]
        # Candidate was evaluating when stream finished, transitions to INCOMPLETE on finalize
        assert cand["state"] in (CandidateState.EVALUATING.value, CandidateState.INCOMPLETE.value)
        # Ensure no promotion transition was recorded
        states = [t["to_state"] for t in cand["state_transitions"]]
        assert CandidateState.PROMOTED.value not in states

        # All recorded predictions must reference v1.0-frozen
        preds = engine.evaluator.get_all_predictions()
        assert len(preds) == 4800  # 5000 - 200 warmup
        for p in preds:
            assert p["model_version"] == "v1.0-frozen"

    def test_promotion_matches_actual_model_version_transition(self, tmp_path: Path) -> None:
        """In a 10000-event run, promotion occurs at seq 5572 and switches active model."""
        from driftshield.config import DriftShieldConfig, LabelConfig, StreamConfig
        from driftshield.engine import DriftShieldEngine
        from driftshield.simulator import Simulator
        from driftshield.storage import SQLiteStorage

        cfg = DriftShieldConfig(
            stream=StreamConfig(scenario="abrupt", n_events=10000, drift_start_sequence=1000, seed=42),
            labels=LabelConfig(warmup_size=200, label_budget=1500, monitor_rate=0.15, label_delay=0),
            adaptation=AdaptationConfig(target_training_labels=200, evaluation_target_events=500),
            output_dir=str(tmp_path),
        )
        storage = SQLiteStorage(db_path=tmp_path / "test_prom.db", artifacts_dir=tmp_path / "artifacts")
        sim = Simulator(cfg.stream)
        engine = DriftShieldEngine(config=cfg, storage=storage)
        engine.initialize(simulator=sim)

        for event in sim.iter_events():
            engine.process_event(event)

        summary = engine.finalize()

        assert summary.active_model_version == "v2.0-promoted"
        cand = summary.candidate_summary["candidates"][0]
        assert cand["state"] == CandidateState.PROMOTED.value

        prom_transition = next(t for t in cand["state_transitions"] if t["to_state"] == CandidateState.PROMOTED.value)
        assert prom_transition["sequence"] == 5572
        assert prom_transition["sequence"] <= 10000

        preds = engine.evaluator.get_all_predictions()
        for p in preds:
            seq = p["sequence"]
            if seq <= 5572:
                assert p["model_version"] == "v1.0-frozen"
            else:
                assert p["model_version"] == "v2.0-promoted"


