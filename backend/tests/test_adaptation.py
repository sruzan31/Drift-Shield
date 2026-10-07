"""Unit and integration tests for Phase 4A Candidate Training."""

import csv
import json
from pathlib import Path
import pytest
from river import preprocessing

from driftshield.adaptation import CandidateManager, CandidateModel
from driftshield.baseline import BaselineClassifier
from driftshield.config import AdaptationConfig, DriftShieldConfig, LabelConfig, MonitoringConfig, StreamConfig
from driftshield.contracts import CandidateState, DriftAlert
from driftshield.evaluator import Evaluator
from driftshield.labeling import LabelAcquirer
from driftshield.monitoring import ErrorChangeMonitor
from driftshield.run_baseline import run_scenario
from driftshield.simulator import Simulator


# =====================================================================
# Unit Tests for CandidateModel & CandidateManager
# =====================================================================

class TestCandidateModelUnit:
    def test_pre_epoch_labels_cannot_train(self) -> None:
        scaler = preprocessing.StandardScaler()
        cand = CandidateModel(
            candidate_id="cand-1",
            active_model_version="v1.0-frozen",
            alert_id="alert-100",
            actionable_alert_sequence=100,
            epoch=100,
            preprocessor=scaler,
            config=AdaptationConfig(target_training_labels=200),
        )

        # Event strictly before epoch (sequence 90)
        assert not cand.can_train_on(90, "evt-90")
        assert not cand.learn("evt-90", 90, 105, {"f0": 1.0, "f1": 2.0}, 1, "monitor")

        # Boundary event (sequence 100 == epoch)
        assert not cand.can_train_on(100, "evt-100")
        assert not cand.learn("evt-100", 100, 105, {"f0": 1.0, "f1": 2.0}, 1, "monitor")

        assert cand.unique_training_labels == 0

    def test_post_epoch_labels_train_candidate(self) -> None:
        scaler = preprocessing.StandardScaler()
        cand = CandidateModel(
            candidate_id="cand-1",
            active_model_version="v1.0-frozen",
            alert_id="alert-100",
            actionable_alert_sequence=100,
            epoch=100,
            preprocessor=scaler,
            config=AdaptationConfig(target_training_labels=5),
        )

        # Event strictly after epoch (sequence 101)
        assert cand.can_train_on(101, "evt-101")
        assert cand.learn("evt-101", 101, 101, {"f0": 1.0, "f1": 2.0}, 1, "monitor")
        assert cand.unique_training_labels == 1
        assert len(cand.training_records) == 1

    def test_duplicate_label_cannot_double_train(self) -> None:
        scaler = preprocessing.StandardScaler()
        cand = CandidateModel(
            candidate_id="cand-1",
            active_model_version="v1.0-frozen",
            alert_id="alert-100",
            actionable_alert_sequence=100,
            epoch=100,
            preprocessor=scaler,
            config=AdaptationConfig(target_training_labels=10),
        )

        assert cand.learn("evt-105", 105, 105, {"f0": 1.0, "f1": 2.0}, 1, "monitor")
        assert cand.unique_training_labels == 1

        # Second delivery with same event_id (e.g. from selective overlap)
        assert not cand.learn("evt-105", 105, 105, {"f0": 1.0, "f1": 2.0}, 1, "selective")
        assert cand.unique_training_labels == 1

    def test_reaches_target_and_freezes(self) -> None:
        scaler = preprocessing.StandardScaler()
        cand = CandidateModel(
            candidate_id="cand-1",
            active_model_version="v1.0-frozen",
            alert_id="alert-100",
            actionable_alert_sequence=100,
            epoch=100,
            preprocessor=scaler,
            config=AdaptationConfig(target_training_labels=3),
        )

        assert cand.state == CandidateState.TRAINING
        cand.learn("evt-101", 101, 101, {"f0": 1.0, "f1": 2.0}, 1, "monitor")
        cand.learn("evt-102", 102, 102, {"f0": 1.0, "f1": 2.0}, 0, "monitor")
        assert cand.state == CandidateState.TRAINING

        cand.learn("evt-103", 103, 103, {"f0": 1.0, "f1": 2.0}, 1, "monitor")
        assert cand.state == CandidateState.READY_FOR_EVALUATION
        assert cand.is_frozen
        assert cand.freeze_sequence == 103
        assert cand.unique_training_labels == 3

        # Further labels cannot train frozen candidate
        assert not cand.learn("evt-104", 104, 104, {"f0": 1.0, "f1": 2.0}, 1, "monitor")
        assert cand.unique_training_labels == 3


class TestCandidateManagerUnit:
    def test_single_active_candidate_policy(self) -> None:
        mgr = CandidateManager(AdaptationConfig(cooldown_events=10))
        alert1 = DriftAlert(
            alert_id="alert-1",
            event_id="evt-1500",
            event_sequence=1500,
            arrival_sequence=1500,
            detection_delay_from_event=0,
            model_version="v1.0-frozen",
            loss=1,
            adwin_delta=0.002,
            adwin_estimation=0.75,
            adwin_width=50,
            monitoring_labels_count=50,
            monitoring_coverage=0.1,
        )
        cand1 = mgr.handle_alert(alert1, current_sequence=1500)
        assert cand1 is not None
        assert mgr.active_candidate is cand1
        assert cand1.state == CandidateState.TRAINING

        # Second alert while cand1 is training is ignored
        alert2 = DriftAlert(
            alert_id="alert-2",
            event_id="evt-1520",
            event_sequence=1520,
            arrival_sequence=1520,
            detection_delay_from_event=0,
            model_version="v1.0-frozen",
            loss=1,
            adwin_delta=0.002,
            adwin_estimation=0.80,
            adwin_width=50,
            monitoring_labels_count=55,
            monitoring_coverage=0.1,
        )
        cand2 = mgr.handle_alert(alert2, current_sequence=1520)
        assert cand2 is None
        assert mgr.ignored_alerts_count == 1
        assert mgr.candidate_counter == 1

    def test_finalize_marks_incomplete(self) -> None:
        mgr = CandidateManager(AdaptationConfig(target_training_labels=200))
        alert = DriftAlert(
            alert_id="alert-1",
            event_id="evt-1500",
            event_sequence=1500,
            arrival_sequence=1500,
            detection_delay_from_event=0,
            model_version="v1.0-frozen",
            loss=1,
            adwin_delta=0.002,
            adwin_estimation=0.75,
            adwin_width=50,
            monitoring_labels_count=50,
            monitoring_coverage=0.1,
        )
        cand = mgr.handle_alert(alert, current_sequence=1500)
        assert cand is not None
        # Train on only 2 labels
        mgr.train_step("evt-1501", 1501, 1501, {"f0": 1.0, "f1": 2.0}, 1, "monitor")
        mgr.train_step("evt-1502", 1502, 1502, {"f0": 1.0, "f1": 2.0}, 0, "monitor")

        # Finalize at stream end (sequence 2000)
        mgr.finalize(last_sequence=2000)
        assert cand.state == CandidateState.INCOMPLETE
        assert cand.unique_training_labels == 2


# =====================================================================
# Integration Tests with Full Pipeline
# =====================================================================

class TestCandidateIntegration:
    def test_abrupt_short_run_candidate_incomplete(self, tmp_path: Path) -> None:
        # Standard short run (2000 events, 300 label budget)
        # Drift at 1000, alert around 1647.
        # Only ~35 labels arrive between 1647 and 2000; target=200 produces INCOMPLETE.
        cfg = DriftShieldConfig(
            stream=StreamConfig(scenario="abrupt", n_events=2000, seed=42, drift_start_sequence=1000),
            labels=LabelConfig(warmup_size=200, label_budget=300, label_delay=0),
            adaptation=AdaptationConfig(target_training_labels=200),
            output_dir=str(tmp_path),
        )
        metrics = run_scenario("abrupt", cfg, str(tmp_path))

        summary_file = tmp_path / "abrupt_candidate_summary.json"
        csv_file = tmp_path / "abrupt_candidate_training.csv"
        assert summary_file.exists()
        assert csv_file.exists()

        with open(summary_file, "r") as f:
            data = json.load(f)

        assert data["total_candidates_spawned"] == 1
        cand = data["candidates"][0]
        assert cand["state"] == CandidateState.INCOMPLETE.value
        assert cand["unique_training_labels"] < 200
        assert cand["target_training_labels"] == 200

    def test_abrupt_long_run_candidate_reaches_ready_for_evaluation(self, tmp_path: Path) -> None:
        # Long run: 6000 events, budget=1200, target=200
        cfg = DriftShieldConfig(
            stream=StreamConfig(scenario="abrupt", n_events=6000, seed=42, drift_start_sequence=1000),
            labels=LabelConfig(warmup_size=200, label_budget=1200, label_delay=0),
            adaptation=AdaptationConfig(target_training_labels=200),
            output_dir=str(tmp_path),
        )
        metrics = run_scenario("abrupt", cfg, str(tmp_path))

        summary_file = tmp_path / "abrupt_candidate_summary.json"
        csv_file = tmp_path / "abrupt_candidate_training.csv"
        assert summary_file.exists()
        assert csv_file.exists()

        with open(summary_file, "r") as f:
            data = json.load(f)

        assert data["total_candidates_spawned"] >= 1
        cand = data["candidates"][0]
        # Candidate reached READY_FOR_EVALUATION during its training lifecycle
        states_visited = [t["to_state"] for t in cand["state_transitions"]]
        assert CandidateState.READY_FOR_EVALUATION.value in states_visited
        assert cand["unique_training_labels"] == 200
        assert cand["freeze_sequence"] is not None

        # Verify CSV training records count
        with open(csv_file, "r") as f:
            reader = csv.DictReader(f)
            records = list(reader)
        assert len(records) >= 200

    def test_delayed_labels_candidate_training(self, tmp_path: Path) -> None:
        # Delay = 10 on long run
        cfg = DriftShieldConfig(
            stream=StreamConfig(scenario="abrupt", n_events=6000, seed=42, drift_start_sequence=1000),
            labels=LabelConfig(warmup_size=200, label_budget=1200, label_delay=10),
            adaptation=AdaptationConfig(target_training_labels=200),
            output_dir=str(tmp_path),
        )
        metrics = run_scenario("abrupt", cfg, str(tmp_path))

        summary_file = tmp_path / "abrupt_candidate_summary.json"
        with open(summary_file, "r") as f:
            data = json.load(f)

        cand = data["candidates"][0]
        states_visited = [t["to_state"] for t in cand["state_transitions"]]
        assert CandidateState.READY_FOR_EVALUATION.value in states_visited
        assert cand["unique_training_labels"] == 200
        # In delayed labels, epoch is arrival sequence (e.g. 1657)
        assert cand["epoch"] == cand["actionable_alert_sequence"]
        # Verify all training events are strictly after epoch
        for tid in cand["training_event_ids"]:
            seq = int(tid.replace("evt-", ""))
            assert seq > cand["epoch"]
