"""Unit and integration tests for Phase 3 ADWIN Error-Change Monitoring."""

import csv
import json
from pathlib import Path
import pytest

from driftshield.baseline import BaselineClassifier
from driftshield.config import DriftShieldConfig, LabelConfig, MonitoringConfig, StreamConfig
from driftshield.contracts import DriftAlert, PredictionRecord
from driftshield.evaluator import Evaluator
from driftshield.labeling import LabelAcquirer
from driftshield.monitoring import ErrorChangeMonitor
from driftshield.run_baseline import run_scenario
from driftshield.simulator import Simulator


# =====================================================================
# Unit Tests for ErrorChangeMonitor
# =====================================================================

class TestErrorChangeMonitorUnit:
    def test_selective_only_labels_ignored(self) -> None:
        monitor = ErrorChangeMonitor(MonitoringConfig())
        pred = PredictionRecord(
            event_id="evt-200",
            sequence=200,
            timestamp=1000.0,
            predicted_label=1,
            predicted_proba=0.52,
            features={"f0": 1.0, "f1": 2.0},
            warmup=False,
        )
        alert = monitor.process_monitoring_label(
            event_id="evt-200",
            event_sequence=200,
            arrival_sequence=200,
            original_prediction=pred,
            true_label=0,
            source="selective",
        )
        assert alert is None
        assert monitor.monitoring_labels_count == 0
        assert monitor.adwin_width == 0

    def test_warmup_predictions_ignored(self) -> None:
        monitor = ErrorChangeMonitor(MonitoringConfig())
        pred = PredictionRecord(
            event_id="evt-10",
            sequence=10,
            timestamp=100.0,
            predicted_label=0,
            predicted_proba=0.1,
            features={"f0": 1.0, "f1": 2.0},
            warmup=True,
        )
        alert = monitor.process_monitoring_label(
            event_id="evt-10",
            event_sequence=10,
            arrival_sequence=10,
            original_prediction=pred,
            true_label=1,
            source="monitor",
        )
        assert alert is None
        assert monitor.monitoring_labels_count == 0

    def test_duplicate_monitoring_label_raises(self) -> None:
        monitor = ErrorChangeMonitor(MonitoringConfig())
        pred = PredictionRecord(
            event_id="evt-205",
            sequence=205,
            timestamp=1000.0,
            predicted_label=1,
            predicted_proba=0.9,
            features={"f0": 1.0, "f1": 2.0},
            warmup=False,
        )
        monitor.process_monitoring_label(
            event_id="evt-205",
            event_sequence=205,
            arrival_sequence=205,
            original_prediction=pred,
            true_label=1,
            source="monitor",
        )
        assert monitor.monitoring_labels_count == 1

        with pytest.raises(ValueError, match="Duplicate monitoring label"):
            monitor.process_monitoring_label(
                event_id="evt-205",
                event_sequence=205,
                arrival_sequence=205,
                original_prediction=pred,
                true_label=1,
                source="monitor",
            )

    def test_mismatched_prediction_event_id_raises(self) -> None:
        monitor = ErrorChangeMonitor(MonitoringConfig())
        pred = PredictionRecord(
            event_id="evt-201",
            sequence=201,
            timestamp=1000.0,
            predicted_label=1,
            predicted_proba=0.9,
            features={"f0": 1.0, "f1": 2.0},
            warmup=False,
        )
        with pytest.raises(ValueError, match="Prediction event_id mismatch"):
            monitor.process_monitoring_label(
                event_id="evt-999",
                event_sequence=999,
                arrival_sequence=999,
                original_prediction=pred,
                true_label=1,
                source="monitor",
            )

    def test_loss_uses_original_prediction(self) -> None:
        monitor = ErrorChangeMonitor(MonitoringConfig())
        pred = PredictionRecord(
            event_id="evt-210",
            sequence=210,
            timestamp=1000.0,
            predicted_label=1,
            predicted_proba=0.85,
            features={"f0": 1.0, "f1": 2.0},
            warmup=False,
        )
        monitor.process_monitoring_label(
            event_id="evt-210",
            event_sequence=210,
            arrival_sequence=220,
            original_prediction=pred,
            true_label=0,
            source="monitor",
        )
        assert monitor.monitoring_labels_count == 1
        assert monitor.adwin_estimation == 1.0

    def test_adwin_alert_emission_on_shift(self) -> None:
        cfg = MonitoringConfig(adwin_delta=0.01, adwin_clock=1, adwin_min_window_length=5, adwin_grace_period=5)
        monitor = ErrorChangeMonitor(cfg)

        for i in range(100):
            p = PredictionRecord(
                event_id=f"evt-{i}",
                sequence=i,
                timestamp=float(i),
                predicted_label=0,
                predicted_proba=0.1,
                features={"f0": 0.0, "f1": 0.0},
                warmup=False,
            )
            monitor.process_monitoring_label(
                event_id=f"evt-{i}",
                event_sequence=i,
                arrival_sequence=i,
                original_prediction=p,
                true_label=0,
                source="monitor",
            )

        assert monitor.alerts_count == 0
        assert monitor.adwin_estimation == 0.0

        alert_fired = False
        for i in range(100, 150):
            p = PredictionRecord(
                event_id=f"evt-{i}",
                sequence=i,
                timestamp=float(i),
                predicted_label=0,
                predicted_proba=0.1,
                features={"f0": 0.0, "f1": 0.0},
                warmup=False,
            )
            alert = monitor.process_monitoring_label(
                event_id=f"evt-{i}",
                event_sequence=i,
                arrival_sequence=i,
                original_prediction=p,
                true_label=1,
                source="monitor",
            )
            if alert is not None:
                alert_fired = True
                assert alert.description == "evidence of error change"
                assert alert.loss == 1
                assert alert.event_sequence == i
                break

        assert alert_fired
        assert monitor.alerts_count > 0


# =====================================================================
# Integration Tests with Full Pipeline
# =====================================================================

class TestMonitoringIntegration:
    def test_stationary_scenario_zero_false_alarms(self) -> None:
        cfg = DriftShieldConfig(
            stream=StreamConfig(scenario="stationary", n_events=2000, seed=42),
            labels=LabelConfig(warmup_size=200, label_budget=300, label_delay=0),
            monitoring=MonitoringConfig(adwin_delta=0.002),
        )
        sim = Simulator(cfg.stream, label_delay=0)
        baseline = BaselineClassifier(cfg.labels)
        acquirer = LabelAcquirer(cfg.labels, sim.get_label_records())
        monitor = ErrorChangeMonitor(cfg.monitoring)
        evaluator = Evaluator(sim, warmup_size=200)

        for event in sim.iter_events():
            if event.sequence < 200:
                baseline.register_warmup_features(event)
            if baseline.is_frozen:
                monitor.register_evaluated_event(event.sequence)

            pred = baseline.predict(event)
            evaluator.record_prediction(pred)

            delivered = acquirer.step(event.sequence, pred)
            for lbl in delivered:
                evaluator.deliver_label(lbl)
                if lbl.source == "warmup" and not baseline.is_frozen:
                    baseline.learn(lbl.event_id, lbl.true_label)
                elif baseline.is_frozen and lbl.source in ("monitor", "both"):
                    orig_pred = evaluator._predictions[lbl.event_id]
                    monitor.process_monitoring_label(
                        event_id=lbl.event_id,
                        event_sequence=orig_pred.sequence,
                        arrival_sequence=event.sequence,
                        original_prediction=orig_pred,
                        true_label=lbl.true_label,
                        source=lbl.source,
                    )

            if not baseline.is_frozen and event.sequence >= 199:
                baseline.freeze()

        metrics = evaluator.compute_metrics(
            label_acquisition=acquirer.get_channel_stats(),
            alerts=monitor.alerts,
        )
        assert monitor.alerts_count == 0
        assert metrics.monitoring_evaluation["total_alerts"] == 0
        assert metrics.monitoring_evaluation["false_alarms"] == 0
        assert metrics.monitoring_evaluation["missed_detection"] is False

    def test_abrupt_scenario_detects_drift(self) -> None:
        cfg = DriftShieldConfig(
            stream=StreamConfig(scenario="abrupt", n_events=2000, seed=42, drift_start_sequence=1000),
            labels=LabelConfig(warmup_size=200, label_budget=300, label_delay=0),
            monitoring=MonitoringConfig(adwin_delta=0.002),
        )
        sim = Simulator(cfg.stream, label_delay=0)
        baseline = BaselineClassifier(cfg.labels)
        acquirer = LabelAcquirer(cfg.labels, sim.get_label_records())
        monitor = ErrorChangeMonitor(cfg.monitoring)
        evaluator = Evaluator(sim, warmup_size=200, drift_sequence=1000)

        for event in sim.iter_events():
            if event.sequence < 200:
                baseline.register_warmup_features(event)
            if baseline.is_frozen:
                monitor.register_evaluated_event(event.sequence)

            pred = baseline.predict(event)
            evaluator.record_prediction(pred)

            delivered = acquirer.step(event.sequence, pred)
            for lbl in delivered:
                evaluator.deliver_label(lbl)
                if lbl.source == "warmup" and not baseline.is_frozen:
                    baseline.learn(lbl.event_id, lbl.true_label)
                elif baseline.is_frozen and lbl.source in ("monitor", "both"):
                    orig_pred = evaluator._predictions[lbl.event_id]
                    monitor.process_monitoring_label(
                        event_id=lbl.event_id,
                        event_sequence=orig_pred.sequence,
                        arrival_sequence=event.sequence,
                        original_prediction=orig_pred,
                        true_label=lbl.true_label,
                        source=lbl.source,
                    )

            if not baseline.is_frozen and event.sequence >= 199:
                baseline.freeze()

        metrics = evaluator.compute_metrics(
            label_acquisition=acquirer.get_channel_stats(),
            alerts=monitor.alerts,
        )
        assert monitor.alerts_count > 0
        me = metrics.monitoring_evaluation
        assert me["false_alarms"] == 0
        assert me["missed_detection"] is False
        assert me["first_alert_event_sequence"] >= 1000
        assert me["detection_delay_events"] is not None
        assert me["detection_delay_labeled_observations"] is not None

    def test_delayed_labels_tracking(self) -> None:
        cfg = DriftShieldConfig(
            stream=StreamConfig(scenario="abrupt", n_events=2000, seed=42, drift_start_sequence=1000),
            labels=LabelConfig(warmup_size=200, label_budget=300, label_delay=10),
            monitoring=MonitoringConfig(adwin_delta=0.002),
        )
        sim = Simulator(cfg.stream, label_delay=10)
        baseline = BaselineClassifier(cfg.labels)
        acquirer = LabelAcquirer(cfg.labels, sim.get_label_records())
        monitor = ErrorChangeMonitor(cfg.monitoring)
        evaluator = Evaluator(sim, warmup_size=200, drift_sequence=1000)

        for event in sim.iter_events():
            if event.sequence < 200:
                baseline.register_warmup_features(event)
            if baseline.is_frozen:
                monitor.register_evaluated_event(event.sequence)

            pred = baseline.predict(event)
            evaluator.record_prediction(pred)

            delivered = acquirer.step(event.sequence, pred)
            for lbl in delivered:
                evaluator.deliver_label(lbl)
                if lbl.source == "warmup" and not baseline.is_frozen:
                    baseline.learn(lbl.event_id, lbl.true_label)
                elif baseline.is_frozen and lbl.source in ("monitor", "both"):
                    orig_pred = evaluator._predictions[lbl.event_id]
                    monitor.process_monitoring_label(
                        event_id=lbl.event_id,
                        event_sequence=orig_pred.sequence,
                        arrival_sequence=event.sequence,
                        original_prediction=orig_pred,
                        true_label=lbl.true_label,
                        source=lbl.source,
                    )

            if not baseline.is_frozen and event.sequence >= 199 + 10:
                baseline.freeze()

        # Draining
        last_seq = sim.events[-1].sequence
        remaining = acquirer.flush_pending_up_to(last_seq + 10)
        for lbl in remaining:
            evaluator.deliver_label(lbl)
            if baseline.is_frozen and lbl.source in ("monitor", "both"):
                orig_pred = evaluator._predictions[lbl.event_id]
                monitor.process_monitoring_label(
                    event_id=lbl.event_id,
                    event_sequence=orig_pred.sequence,
                    arrival_sequence=lbl.delivery_sequence,
                    original_prediction=orig_pred,
                    true_label=lbl.true_label,
                    source=lbl.source,
                )

        assert monitor.alerts_count > 0
        first_alert = monitor.alerts[0]
        assert first_alert.arrival_sequence == first_alert.event_sequence + 10
        assert first_alert.detection_delay_from_event == 10

    def test_model_remains_frozen_during_monitoring(self) -> None:
        cfg = DriftShieldConfig(
            stream=StreamConfig(scenario="abrupt", n_events=2000, seed=42, drift_start_sequence=1000),
            labels=LabelConfig(warmup_size=200, label_budget=300, label_delay=0),
        )
        sim = Simulator(cfg.stream, label_delay=0)
        baseline = BaselineClassifier(cfg.labels)
        acquirer = LabelAcquirer(cfg.labels, sim.get_label_records())
        monitor = ErrorChangeMonitor(cfg.monitoring)
        evaluator = Evaluator(sim, warmup_size=200)

        for event in sim.iter_events():
            if event.sequence < 200:
                baseline.register_warmup_features(event)
            pred = baseline.predict(event)
            evaluator.record_prediction(pred)
            delivered = acquirer.step(event.sequence, pred)
            for lbl in delivered:
                evaluator.deliver_label(lbl)
                if lbl.source == "warmup" and not baseline.is_frozen:
                    baseline.learn(lbl.event_id, lbl.true_label)
                elif baseline.is_frozen and lbl.source in ("monitor", "both"):
                    orig_pred = evaluator._predictions[lbl.event_id]
                    monitor.process_monitoring_label(
                        event_id=lbl.event_id,
                        event_sequence=orig_pred.sequence,
                        arrival_sequence=event.sequence,
                        original_prediction=orig_pred,
                        true_label=lbl.true_label,
                        source=lbl.source,
                    )
            if not baseline.is_frozen and event.sequence >= 199:
                baseline.freeze()
                frozen_weights = dict(baseline.weights)

        # Weights must be completely unchanged from freeze point
        assert baseline.is_frozen
        assert baseline.weights == frozen_weights

    def test_run_scenario_exports_alerts_csv_and_json(self, tmp_path: Path) -> None:
        cfg = DriftShieldConfig(
            stream=StreamConfig(scenario="abrupt", n_events=2000, seed=42, drift_start_sequence=1000),
            labels=LabelConfig(warmup_size=200, label_budget=300, label_delay=0),
            output_dir=str(tmp_path),
        )
        run_scenario("abrupt", cfg, str(tmp_path))

        alerts_csv = tmp_path / "abrupt_alerts.csv"
        metrics_json = tmp_path / "abrupt_metrics.json"

        assert alerts_csv.exists()
        assert metrics_json.exists()

        with open(metrics_json, "r") as f:
            data = json.load(f)

        assert "monitoring_summary" in data
        assert "monitoring_evaluation" in data["metrics"]
        assert data["metrics"]["monitoring_evaluation"]["missed_detection"] is False

        with open(alerts_csv, "r") as f:
            reader = csv.DictReader(f)
            alert_rows = list(reader)

        assert len(alert_rows) == len(data["monitoring_summary"]["alerts"])
        if alert_rows:
            assert alert_rows[0]["description"] == "evidence of error change"
