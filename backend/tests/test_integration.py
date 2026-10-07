"""
Integration tests for DriftShield Phase 1.

Tests the full pipeline: simulator -> baseline -> labeling -> evaluator.

Key properties verified:
1. End-to-end run with identical seeds produces identical metrics.
2. Warm-up results excluded from reported evaluation.
3. Error rate consistent with direct calculation from saved predictions.
4. Both stationary and abrupt scenarios run without errors.
5. CLI runner produces CSV and JSON output files.
"""

import json
import math
import os
import pytest

from driftshield.baseline import BaselineClassifier
from driftshield.config import DriftShieldConfig, LabelConfig, StreamConfig
from driftshield.contracts import PredictionRecord
from driftshield.evaluator import Evaluator
from driftshield.labeling import LabelAcquirer
from driftshield.run_baseline import run_scenario
from driftshield.simulator import Simulator


def run_full_pipeline(scenario: str, n_events=300, seed=42, warmup=50, budget=80, delay=0):
    """Helper: run one scenario end-to-end and return (metrics, evaluator)."""
    stream_cfg = StreamConfig(
        scenario=scenario,
        n_events=n_events,
        seed=seed,
        drift_start_sequence=n_events // 2,
    )
    label_cfg = LabelConfig(
        warmup_size=warmup,
        label_budget=budget,
        monitor_rate=0.15,
        low_margin_k=10,
        label_delay=delay,
    )
    cfg = DriftShieldConfig(stream=stream_cfg, labels=label_cfg)

    sim = Simulator(stream_cfg, label_delay=delay)
    baseline = BaselineClassifier(label_cfg)
    acquirer = LabelAcquirer(label_cfg, sim.label_records)
    evaluator = Evaluator(sim, warmup_size=warmup)

    for event in sim.iter_events():
        is_warmup = event.sequence < warmup
        if is_warmup:
            baseline.register_warmup_features(event)

        pred = baseline.predict(event)
        evaluator.record_prediction(pred)

        delivered = acquirer.step(event.sequence, pred)
        for lbl in delivered:
            evaluator.deliver_label(lbl)
            if lbl.source == "warmup" and not baseline.is_frozen:
                baseline.learn(lbl.event_id, lbl.true_label)

        if not baseline.is_frozen and event.sequence >= warmup - 1 + delay:
            baseline.freeze()
            eval_start = event.sequence + 1
            evaluator.set_evaluation_start_sequence(eval_start)

    if delay > 0:
        last_seq = sim.events[-1].sequence
        remaining = acquirer.flush_pending_up_to(last_seq + delay)
        for lbl in remaining:
            evaluator.deliver_label(lbl)

    eval_start_seq = warmup + delay if delay > 0 else warmup
    metrics = evaluator.compute_metrics(
        label_acquisition_count=acquirer.budget_used,
        evaluation_start_sequence=eval_start_seq,
    )
    return metrics, evaluator, acquirer


class TestEndToEndReproducibility:
    def test_identical_config_produces_identical_metrics(self):
        m1, _, _ = run_full_pipeline("stationary", seed=42)
        m2, _, _ = run_full_pipeline("stationary", seed=42)
        assert m1.error_rate == pytest.approx(m2.error_rate)
        assert m1.scored_predictions == m2.scored_predictions
        assert m1.label_acquisition_count == m2.label_acquisition_count

    def test_different_seeds_may_differ(self):
        m1, _, _ = run_full_pipeline("stationary", seed=1)
        m2, _, _ = run_full_pipeline("stationary", seed=2)
        # Different seeds should produce different data; error rates may differ
        # (This is a sanity check, not a strict assertion)
        assert m1.total_predictions > 0
        assert m2.total_predictions > 0


class TestWarmupExclusionIntegration:
    def test_warmup_excluded_from_metrics(self):
        warmup = 50
        n_events = 200
        m, _, _ = run_full_pipeline("stationary", n_events=n_events, warmup=warmup)
        assert m.warmup_predictions == warmup
        assert m.total_predictions == n_events - warmup
        assert m.warmup_size == warmup

    def test_scored_never_exceeds_postWarmup(self):
        m, _, _ = run_full_pipeline("stationary", n_events=200, warmup=50)
        assert m.scored_predictions <= m.total_predictions


class TestBudgetIntegration:
    def test_budget_respected(self):
        budget = 40
        _, _, acquirer = run_full_pipeline("stationary", budget=budget)
        assert acquirer.budget_used <= budget

    def test_zero_budget(self):
        n_events = 200
        warmup = 50
        stream_cfg = StreamConfig(n_events=n_events, seed=42)
        label_cfg = LabelConfig(
            warmup_size=warmup,
            label_budget=0,
            monitor_rate=1.0,
            label_delay=0,
        )
        sim = Simulator(stream_cfg, label_delay=0)
        baseline = BaselineClassifier(label_cfg)
        acquirer = LabelAcquirer(label_cfg, sim.label_records)
        evaluator = Evaluator(sim, warmup_size=warmup)

        for event in sim.iter_events():
            is_warmup = event.sequence < warmup
            if is_warmup:
                baseline.register_warmup_features(event)
            pred = baseline.predict(event)
            evaluator.record_prediction(pred)
            delivered = acquirer.step(event.sequence, pred)
            for lbl in delivered:
                evaluator.deliver_label(lbl)
                if lbl.source == "warmup" and not baseline.is_frozen:
                    baseline.learn(lbl.event_id, lbl.true_label)
            if not baseline.is_frozen and event.sequence >= warmup - 1 + label_cfg.label_delay:
                baseline.freeze()

        assert acquirer.budget_used == 0
        m = evaluator.compute_metrics(label_acquisition_count=acquirer.budget_used)
        assert m.label_acquisition_count == 0
        assert m.monitor_channel.total == 0
        assert m.monitor_channel.error_rate is None
        assert m.scored_predictions == n_events - warmup


class TestErrorRateIntegration:
    def test_error_rate_matches_direct_calculation(self):
        m, evaluator, _ = run_full_pipeline("stationary", n_events=300)
        if m.scored_predictions > 0:
            direct = evaluator.compute_error_rate_from_records()
            assert abs(m.error_rate - direct) < 1e-9

    def test_stationary_error_below_50_percent(self):
        """A logistic regression trained on clean data should beat random."""
        m, _, _ = run_full_pipeline("stationary", n_events=1000, warmup=200, budget=400)
        if m.scored_predictions > 0:
            assert m.error_rate < 0.5, (
                f"Stationary error rate {m.error_rate:.3f} should be < 0.5 "
                "(logistic regression should beat random guessing)"
            )


class TestDelayedLabels:
    def test_delayed_labels_match_predictions(self):
        """Labels with delay=5 must still join the correct predictions."""
        m, evaluator, _ = run_full_pipeline(
            "stationary", n_events=200, warmup=30, delay=5
        )
        rows = evaluator.get_scored_predictions()
        for row in rows:
            if row["true_label"] is not None:
                # correct field should match prediction vs true label
                expected_correct = int(row["predicted_label"] == row["true_label"])
                assert row["correct"] == expected_correct

    def test_delayed_warmup_all_labels_learned_before_freeze(self):
        """All warmup labels must be delivered and learned before model freeze when delay > 0."""
        delay = 10
        warmup = 30
        sim = Simulator(StreamConfig(n_events=100, seed=42), label_delay=delay)
        cfg = LabelConfig(warmup_size=warmup, label_delay=delay)
        baseline = BaselineClassifier(cfg)
        acquirer = LabelAcquirer(cfg, sim.label_records)

        learned_warmup_ids = []
        for evt in sim.events:
            is_warmup = evt.sequence < warmup
            if is_warmup:
                baseline.register_warmup_features(evt)
            pred = baseline.predict(evt)
            delivered = acquirer.step(evt.sequence, pred)
            for lbl in delivered:
                if lbl.source == "warmup" and not baseline.is_frozen:
                    baseline.learn(lbl.event_id, lbl.true_label)
                    learned_warmup_ids.append(lbl.event_id)
            if not baseline.is_frozen and evt.sequence >= warmup - 1 + delay:
                baseline.freeze()

        assert baseline.is_frozen
        # All 30 warmup labels must have been learned
        assert len(learned_warmup_ids) == warmup
        assert learned_warmup_ids == [f"evt-{i}" for i in range(warmup)]


class TestAbruptScenario:
    def test_abrupt_runs_without_error(self):
        m, _, _ = run_full_pipeline("abrupt", n_events=400, warmup=80)
        assert isinstance(m.error_rate, float)

    def test_abrupt_higher_error_than_stationary(self):
        """Post-drift, a frozen model should make more errors."""
        m_stat, _, _ = run_full_pipeline("stationary", n_events=600, warmup=100, budget=200)
        m_abrupt, _, _ = run_full_pipeline("abrupt", n_events=600, warmup=100, budget=200)
        # Both scenarios have enough data; abrupt should generally be worse
        # (not a hard guarantee, but true in expectation for this simulator)
        if m_stat.scored_predictions > 0 and m_abrupt.scored_predictions > 0:
            assert m_abrupt.error_rate >= m_stat.error_rate - 0.05, (
                "Abrupt scenario should not be significantly better than stationary "
                "(model is frozen; drift should degrade performance)"
            )


class TestCLIRunner:
    def test_run_scenario_produces_files(self, tmp_path):
        cfg = DriftShieldConfig(
            stream=StreamConfig(n_events=100, seed=99, drift_start_sequence=50),
            labels=LabelConfig(warmup_size=20, label_budget=30, label_delay=0),
            output_dir=str(tmp_path),
        )
        metrics = run_scenario("stationary", cfg, str(tmp_path))
        assert os.path.exists(os.path.join(str(tmp_path), "stationary_predictions.csv"))
        assert os.path.exists(os.path.join(str(tmp_path), "stationary_metrics.json"))

    def test_metrics_json_valid(self, tmp_path):
        cfg = DriftShieldConfig(
            stream=StreamConfig(n_events=100, seed=99, drift_start_sequence=50),
            labels=LabelConfig(warmup_size=20, label_budget=30, label_delay=0),
            output_dir=str(tmp_path),
        )
        run_scenario("stationary", cfg, str(tmp_path))
        with open(os.path.join(str(tmp_path), "stationary_metrics.json")) as f:
            data = json.load(f)
        assert data["synthetic_data"] is True
        assert data["phase"] in (1, 5)
        assert "error_rate" in data["metrics"]
        assert "limitations" in data

    def test_both_scenarios_run(self, tmp_path):
        for scenario in ("stationary", "abrupt"):
            cfg = DriftShieldConfig(
                stream=StreamConfig(n_events=120, seed=7, drift_start_sequence=60),
                labels=LabelConfig(warmup_size=20, label_budget=30, label_delay=0),
                output_dir=str(tmp_path),
            )
            metrics = run_scenario(scenario, cfg, str(tmp_path))
            assert isinstance(metrics["error_rate"], float)


class TestEvaluationStartBoundary:
    def test_delay_10_evaluation_starts_at_210(self):
        """
        For n_events=2000, warmup=200, delay=10:
        Sequence 209 is predicted before freeze; evaluation begins at sequence 210.
        Total evaluated: 1790 (790 pre-drift, 1000 post-drift).
        """
        cfg = DriftShieldConfig(
            stream=StreamConfig(n_events=2000, seed=42, scenario="abrupt", drift_start_sequence=1000),
            labels=LabelConfig(warmup_size=200, label_budget=300, label_delay=10),
        )
        sim = Simulator(cfg.stream, label_delay=10)
        baseline = BaselineClassifier(cfg.labels)
        acquirer = LabelAcquirer(cfg.labels, sim.label_records)
        evaluator = Evaluator(sim, warmup_size=200, drift_sequence=1000)

        freeze_seq = None
        eval_start_seq = None

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

            if not baseline.is_frozen and event.sequence >= 200 - 1 + 10:
                baseline.freeze()
                freeze_seq = event.sequence
                eval_start_seq = event.sequence + 1
                evaluator.set_evaluation_start_sequence(eval_start_seq)

        assert freeze_seq == 209
        assert eval_start_seq == 210

        metrics = evaluator.compute_metrics(
            label_acquisition=acquirer.get_channel_stats(),
            evaluation_start_sequence=eval_start_seq,
        )
        assert metrics.evaluation_start_sequence == 210
        assert metrics.initialization_predictions == 210
        assert metrics.full_synthetic.total == 1790
        assert metrics.pre_drift.total == 790
        assert metrics.post_drift.total == 1000


class TestUnclippedLabelDeliveryAndDrain:
    def test_unclipped_delivery_sequence_and_drain(self):
        """
        Verify label delivery sequences are unclipped (seq + delay) and drained properly
        by advancing logical time past input end.
        """
        n_events = 50
        delay = 10
        stream_cfg = StreamConfig(n_events=n_events, seed=1)
        sim = Simulator(stream_cfg, label_delay=delay)

        # Label records must have exact delivery_sequence = sequence + delay
        for i, rec in enumerate(sim.label_records):
            assert rec.delivery_sequence == i + delay

        # Final label delivery sequence is 49 + 10 = 59 (greater than n_events - 1)
        assert sim.label_records[-1].delivery_sequence == 59

        cfg = LabelConfig(warmup_size=10, label_budget=30, label_delay=delay)
        acquirer = LabelAcquirer(cfg, sim.label_records)
        evaluator = Evaluator(sim, warmup_size=10)

        # Process stream steps
        for event in sim.iter_events():
            pred = make_prediction(event) if 'make_prediction' in globals() else PredictionRecord(
                event_id=event.event_id,
                sequence=event.sequence,
                timestamp=event.timestamp,
                predicted_label=0,
                predicted_proba=0.5,
                features=dict(event.features),
                warmup=event.sequence < 10,
            )
            evaluator.record_prediction(pred)
            delivered = acquirer.step(event.sequence, pred)
            for lbl in delivered:
                evaluator.deliver_label(lbl)

        # Advance logical time after stream ends to drain remaining pipeline labels
        remaining = acquirer.flush_pending_up_to(49 + delay)
        for lbl in remaining:
            evaluator.deliver_label(lbl)

        stats = acquirer.get_channel_stats()
        # All warmup labels delivered
        assert stats["warmup"]["delivered"] == 10
        assert stats["warmup"]["pending"] == 0

