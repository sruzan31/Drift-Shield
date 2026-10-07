"""backend.tests.test_scenarios
=============================
Phase 7A end-to-end scenario coverage and validation test suite.

Verifies:
1. Deterministic generation and evaluator-only ground truth for:
   - stationary
   - abrupt
   - gradual
   - recurring
   - rare_region
   - adversary
2. Seed reproducibility and isolation across all scenarios.
3. Full engine workflow execution (create -> start -> predict -> labels -> detect -> train -> paired eval -> promote/retain -> persist).
4. Delayed labels and exhausted label budget accounting.
5. Insufficient candidate training or evaluation labels handling (INCOMPLETE status).
6. Adaptive adversary rule selection based strictly on past high-margin events.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
from typing import Dict

import numpy as np
import pytest

from driftshield.config import (
    AdaptationConfig,
    DriftShieldConfig,
    LabelConfig,
    MonitoringConfig,
    StreamConfig,
)
from driftshield.contracts import CandidateState, EvaluationDecision
from driftshield.engine import DriftShieldEngine
from driftshield.simulator import Simulator
from driftshield.storage import SQLiteStorage


# =====================================================================
# 1. Simulator Scenario Determinism & Evaluator Ground Truth
# =====================================================================

class TestSimulatorScenarios:
    """Validate data generation, evaluator-only truth, and seed reproducibility."""

    @pytest.mark.parametrize(
        "scenario",
        ["stationary", "abrupt", "gradual", "recurring", "rare_region", "adversary"],
    )
    def test_seed_reproducibility_across_all_scenarios(self, scenario: str) -> None:
        cfg1 = StreamConfig(scenario=scenario, n_events=400, drift_start_sequence=200, seed=42)
        cfg2 = StreamConfig(scenario=scenario, n_events=400, drift_start_sequence=200, seed=42)
        cfg3 = StreamConfig(scenario=scenario, n_events=400, drift_start_sequence=200, seed=99)

        sim1 = Simulator(cfg1)
        sim2 = Simulator(cfg2)
        sim3 = Simulator(cfg3)

        assert len(sim1.events) == 400
        assert len(sim2.events) == 400

        # Identical seeds must match bit-for-bit
        for e1, e2 in zip(sim1.events, sim2.events):
            assert e1.event_id == e2.event_id
            assert e1.features == e2.features
            assert sim1.get_hidden_label(e1.event_id) == sim2.get_hidden_label(e2.event_id)

        # Different seeds must differ
        diff_features = sum(
            1 for e1, e3 in zip(sim1.events, sim3.events) if e1.features != e3.features
        )
        assert diff_features > 300

    def test_gradual_scenario_transition(self) -> None:
        cfg = StreamConfig(
            scenario="gradual",
            n_events=1000,
            drift_start_sequence=400,
            gradual_window=300,
            seed=42,
        )
        sim = Simulator(cfg)
        assert sim.drift_sequence == 400

        # Pre-drift features (seq < 400) should have class 0 centered near (-1, -1)
        pre_c0_f0 = [
            e.features["feature_0"]
            for e in sim.events[:400]
            if sim.get_hidden_label(e.event_id) == 0
        ]
        assert np.mean(pre_c0_f0) < 0.0

        # Post-drift features (seq >= 700) should have class 0 centered near (+1, +1)
        post_c0_f0 = [
            e.features["feature_0"]
            for e in sim.events[700:]
            if sim.get_hidden_label(e.event_id) == 0
        ]
        assert np.mean(post_c0_f0) > 0.0

    def test_recurring_scenario_alternation(self) -> None:
        cfg = StreamConfig(
            scenario="recurring",
            n_events=1200,
            drift_start_sequence=300,
            recurrence_interval=300,
            seed=42,
        )
        sim = Simulator(cfg)
        assert sim.drift_sequence == 300

        # Period 0: [0, 300) -> pre-drift (class 0 near -1)
        p0_c0 = [e.features["feature_0"] for e in sim.events[:300] if sim.get_hidden_label(e.event_id) == 0]
        # Period 1: [300, 600) -> post-drift (class 0 near +1)
        p1_c0 = [e.features["feature_0"] for e in sim.events[300:600] if sim.get_hidden_label(e.event_id) == 0]
        # Period 2: [600, 900) -> return to pre-drift (class 0 near -1)
        p2_c0 = [e.features["feature_0"] for e in sim.events[600:900] if sim.get_hidden_label(e.event_id) == 0]

        assert np.mean(p0_c0) < 0.0
        assert np.mean(p1_c0) > 0.0
        assert np.mean(p2_c0) < 0.0

    def test_rare_region_scenario_disagreement(self) -> None:
        cfg = StreamConfig(
            scenario="rare_region",
            n_events=1000,
            drift_start_sequence=400,
            rare_region_p=0.05,
            seed=42,
        )
        sim = Simulator(cfg)
        assert sim.drift_sequence == 400

        # Events post-drift have flipped labels exclusively in the rare subregion
        flipped_count = 0
        for e in sim.events[400:]:
            label = sim.get_hidden_label(e.event_id)
            if e.features["feature_0"] < -1.5 and label == 1:
                flipped_count += 1
        assert flipped_count > 0

    def test_adaptive_adversary_past_information_only(self) -> None:
        cfg = StreamConfig(
            scenario="adversary",
            n_events=800,
            drift_start_sequence=300,
            adversary_dwell=200,
            seed=42,
        )
        sim = Simulator(cfg)
        assert "adversary_switches" in sim.evaluator_drift_info
        switches = sim.evaluator_drift_info["adversary_switches"]
        assert len(switches) >= 2

        # Verify each switch specifies a cutoff strictly in the past
        for sw in switches:
            assert sw["cutoff_sequence"] < sw["switch_sequence"]
            assert sw["selected_rule"] in ("r1_inverted", "r2_vertical", "r3_horizontal", "r4_orthogonal")


# =====================================================================
# 2. Full Engine Workflow Across Scenarios
# =====================================================================

class TestEngineScenarioWorkflows:
    """Verify complete lifecycle across all scenarios with SQLite persistence."""

    def test_gradual_drift_full_workflow(self, tmp_path: Path) -> None:
        db_path = tmp_path / "gradual.db"
        art_path = tmp_path / "artifacts"
        storage = SQLiteStorage(db_path=db_path, artifacts_dir=art_path)

        cfg = DriftShieldConfig(
            stream=StreamConfig(
                scenario="gradual",
                n_events=3000,
                drift_start_sequence=800,
                gradual_window=400,
                seed=42,
            ),
            labels=LabelConfig(
                warmup_size=150,
                label_budget=1500,
                monitor_rate=0.35,
                label_delay=0,
            ),
            monitoring=MonitoringConfig(adwin_delta=0.002),
            adaptation=AdaptationConfig(
                target_training_labels=100,
                evaluation_target_events=200,
            ),
            output_dir=str(tmp_path),
        )

        sim = Simulator(cfg.stream)
        engine = DriftShieldEngine(config=cfg, storage=storage)
        engine.initialize(simulator=sim)

        for event in sim.iter_events():
            engine.process_event(event)

        summary = engine.finalize()
        assert summary.state == "COMPLETED"
        assert summary.total_events == 3000

        # ADWIN should detect gradual error accumulation
        assert summary.monitoring_summary["alerts_count"] >= 1

        # Check metrics
        assert summary.metrics is not None
        assert "full_synthetic_evaluation" in summary.metrics
        assert summary.metrics["full_synthetic_evaluation"]["sample_count"] > 0

    def test_recurring_drift_full_workflow(self, tmp_path: Path) -> None:
        db_path = tmp_path / "recurring.db"
        art_path = tmp_path / "artifacts"
        storage = SQLiteStorage(db_path=db_path, artifacts_dir=art_path)

        cfg = DriftShieldConfig(
            stream=StreamConfig(
                scenario="recurring",
                n_events=3000,
                drift_start_sequence=600,
                recurrence_interval=600,
                seed=42,
            ),
            labels=LabelConfig(
                warmup_size=150,
                label_budget=1500,
                monitor_rate=0.35,
                label_delay=0,
            ),
            monitoring=MonitoringConfig(adwin_delta=0.002),
            adaptation=AdaptationConfig(
                target_training_labels=100,
                evaluation_target_events=200,
            ),
            output_dir=str(tmp_path),
        )

        sim = Simulator(cfg.stream)
        engine = DriftShieldEngine(config=cfg, storage=storage)
        engine.initialize(simulator=sim)

        for event in sim.iter_events():
            engine.process_event(event)

        summary = engine.finalize()
        assert summary.state == "COMPLETED"
        assert summary.monitoring_summary["alerts_count"] >= 1

    def test_rare_region_stealth_workflow(self, tmp_path: Path) -> None:
        db_path = tmp_path / "rare_region.db"
        art_path = tmp_path / "artifacts"
        storage = SQLiteStorage(db_path=db_path, artifacts_dir=art_path)

        cfg = DriftShieldConfig(
            stream=StreamConfig(
                scenario="rare_region",
                n_events=2000,
                drift_start_sequence=600,
                rare_region_p=0.05,
                seed=42,
            ),
            labels=LabelConfig(
                warmup_size=150,
                label_budget=600,
                monitor_rate=0.20,
                label_delay=0,
            ),
            output_dir=str(tmp_path),
        )

        sim = Simulator(cfg.stream)
        engine = DriftShieldEngine(config=cfg, storage=storage)
        engine.initialize(simulator=sim)

        for event in sim.iter_events():
            engine.process_event(event)

        summary = engine.finalize()
        assert summary.state == "COMPLETED"
        assert summary.metrics is not None

    def test_adaptive_adversary_workflow(self, tmp_path: Path) -> None:
        db_path = tmp_path / "adversary.db"
        art_path = tmp_path / "artifacts"
        storage = SQLiteStorage(db_path=db_path, artifacts_dir=art_path)

        cfg = DriftShieldConfig(
            stream=StreamConfig(
                scenario="adversary",
                n_events=2500,
                drift_start_sequence=600,
                adversary_dwell=400,
                seed=42,
            ),
            labels=LabelConfig(
                warmup_size=150,
                label_budget=1200,
                monitor_rate=0.30,
                label_delay=0,
            ),
            monitoring=MonitoringConfig(adwin_delta=0.002),
            adaptation=AdaptationConfig(
                target_training_labels=100,
                evaluation_target_events=200,
            ),
            output_dir=str(tmp_path),
        )

        sim = Simulator(cfg.stream)
        engine = DriftShieldEngine(config=cfg, storage=storage)
        engine.initialize(simulator=sim)

        for event in sim.iter_events():
            engine.process_event(event)

        summary = engine.finalize()
        assert summary.state == "COMPLETED"
        assert summary.monitoring_summary["alerts_count"] >= 1


# =====================================================================
# 3. Edge Conditions: Delays, Budget Exhaustion & Incomplete Adaptation
# =====================================================================

class TestEdgeConditions:
    """Validate behavior under delayed labels, budget exhaustion, and short runs."""

    def test_exhausted_label_budget_stops_acquisition_cleanly(self, tmp_path: Path) -> None:
        db_path = tmp_path / "budget_exhaust.db"
        art_path = tmp_path / "artifacts"
        storage = SQLiteStorage(db_path=db_path, artifacts_dir=art_path)

        # Strict budget of only 50 post-warmup labels
        cfg = DriftShieldConfig(
            stream=StreamConfig(scenario="abrupt", n_events=1000, drift_start_sequence=500, seed=42),
            labels=LabelConfig(
                warmup_size=100,
                label_budget=50,
                monitor_rate=0.50,
                label_delay=0,
            ),
            output_dir=str(tmp_path),
        )

        sim = Simulator(cfg.stream)
        engine = DriftShieldEngine(config=cfg, storage=storage)
        engine.initialize(simulator=sim)

        for event in sim.iter_events():
            engine.process_event(event)

        summary = engine.finalize()
        assert summary.state == "COMPLETED"

        # Unique post-warmup acquisitions must never exceed the budget of 50
        chan_stats = engine.acquirer.get_channel_stats()
        total_post_warmup = (
            chan_stats["monitor"]["acquired"] + chan_stats["selective"]["acquired"]
        )
        assert total_post_warmup <= 50

    def test_delayed_labels_and_incomplete_candidate_on_short_run(self, tmp_path: Path) -> None:
        db_path = tmp_path / "incomplete_candidate.db"
        art_path = tmp_path / "artifacts"
        storage = SQLiteStorage(db_path=db_path, artifacts_dir=art_path)

        # Short run where an alert fires but stream ends before candidate training completes
        cfg = DriftShieldConfig(
            stream=StreamConfig(
                scenario="abrupt",
                n_events=800,
                drift_start_sequence=250,
                seed=42,
            ),
            labels=LabelConfig(
                warmup_size=100,
                label_budget=600,
                monitor_rate=0.50,
                label_delay=10,
            ),
            monitoring=MonitoringConfig(adwin_delta=0.002),
            adaptation=AdaptationConfig(
                target_training_labels=500,  # Requires 500 labels, stream only produces ~250
                evaluation_target_events=500,
            ),
            output_dir=str(tmp_path),
        )

        sim = Simulator(cfg.stream, label_delay=10)
        engine = DriftShieldEngine(config=cfg, storage=storage)
        engine.initialize(simulator=sim)

        for event in sim.iter_events():
            engine.process_event(event)

        summary = engine.finalize()
        assert summary.state == "COMPLETED"

        # Candidate should have started training but marked INCOMPLETE at finalization
        assert summary.candidate_summary["total_candidates_spawned"] >= 1
        last_cand = summary.candidate_summary["candidates"][-1]
        assert last_cand["state"] == "INCOMPLETE"
        assert last_cand["unique_training_labels"] < 500


# =====================================================================
# 4. Detailed Accounting & Detection Matching Tests
# =====================================================================

class TestAccountingAndDetectionMatching:
    """Validate warmup vs post-warmup accounting and scenario detection matching."""

    def test_warmup_accounting_separated_from_budget_and_pending_deliveries(self, tmp_path: Path) -> None:
        import sqlite3
        db_path = tmp_path / "warmup_acct.db"
        art_path = tmp_path / "artifacts"
        storage = SQLiteStorage(db_path=db_path, artifacts_dir=art_path)

        cfg = DriftShieldConfig(
            stream=StreamConfig(scenario="stationary", n_events=300, seed=42),
            labels=LabelConfig(
                warmup_size=100,
                label_budget=50,
                monitor_rate=0.50,
                label_delay=5,
            ),
            output_dir=str(tmp_path),
        )

        sim = Simulator(cfg.stream, label_delay=5)
        engine = DriftShieldEngine(config=cfg, storage=storage)
        engine.initialize(simulator=sim)

        for event in sim.iter_events():
            engine.process_event(event)

        summary = engine.finalize()
        stats = engine.acquirer.get_channel_stats()

        # Warmup stats
        assert stats["warmup"]["requested"] == 100
        assert stats["warmup"]["acquired"] == 100
        assert stats["warmup"]["delivered"] == 100
        assert stats["warmup"]["pending"] == 0

        # Post-warmup budget
        assert engine.acquirer.total_acquired <= 50
        assert engine.acquirer.budget_used <= 50
        assert engine.acquirer.budget_remaining >= 0

        # Verify in SQLite storage
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT channel, COUNT(*) FROM label_requests WHERE run_id=? GROUP BY channel", (engine.run_id,))
        req_counts = dict(cur.fetchall())
        conn.close()
        assert req_counts.get("warmup") == 100

    def test_gradual_detection_matching_milestones_and_early_alerts(self, tmp_path: Path) -> None:
        from driftshield.contracts import DriftAlert
        from driftshield.evaluator import Evaluator

        cfg = DriftShieldConfig(
            stream=StreamConfig(
                scenario="gradual",
                n_events=1200,
                drift_start_sequence=500,
                gradual_window=400,
                seed=42,
            ),
            labels=LabelConfig(warmup_size=100, label_budget=800, monitor_rate=0.5),
            output_dir=str(tmp_path),
        )

        sim = Simulator(cfg.stream, label_delay=0)
        evaluator = Evaluator(simulator=sim, warmup_size=100)

        # Simulate predictions
        for ev in sim.iter_events():
            from driftshield.contracts import PredictionRecord
            pred = PredictionRecord(
                event_id=ev.event_id,
                sequence=ev.sequence,
                timestamp=ev.timestamp,
                predicted_label=0,
                predicted_proba=0.8,
                features=ev.features,
                warmup=(ev.sequence < 100),
            )
            evaluator.record_prediction(pred)

        # Test simulated alerts: 1 early (false alarm), 1 during transition, 1 post-transition
        alerts = [
            DriftAlert(
                alert_id="alt-1", event_id="evt-450", event_sequence=450, arrival_sequence=450,
                detection_delay_from_event=0, model_version="v1.0", loss=1,
                adwin_delta=0.002, adwin_estimation=0.4, adwin_width=50,
                monitoring_labels_count=20, monitoring_coverage=0.1,
            ),
            DriftAlert(
                alert_id="alt-2", event_id="evt-750", event_sequence=750, arrival_sequence=750,
                detection_delay_from_event=0, model_version="v1.0", loss=1,
                adwin_delta=0.002, adwin_estimation=0.5, adwin_width=60,
                monitoring_labels_count=40, monitoring_coverage=0.1,
            ),
            DriftAlert(
                alert_id="alt-3", event_id="evt-950", event_sequence=950, arrival_sequence=950,
                detection_delay_from_event=0, model_version="v1.0", loss=1,
                adwin_delta=0.002, adwin_estimation=0.5, adwin_width=70,
                monitoring_labels_count=50, monitoring_coverage=0.1,
            ),
        ]

        metrics = evaluator.compute_metrics(alerts=alerts)
        m_eval = metrics.monitoring_evaluation

        assert m_eval is not None
        assert m_eval["scenario"] == "gradual"
        assert m_eval["onset_sequence"] == 500
        assert m_eval["midpoint_sequence"] == 700
        assert m_eval["completion_sequence"] == 900
        assert m_eval["early_alerts_count"] == 1
        assert m_eval["transition_alerts_count"] == 1
        assert m_eval["post_transition_alerts_count"] == 1
        assert m_eval["false_alarms"] == 1  # The alert at 450 is before onset
        assert m_eval["missed_detection"] is False
        assert m_eval["delay_from_onset_events"] == 250  # 750 - 500
        assert m_eval["delay_from_midpoint_events"] == 50  # 750 - 700

    def test_recurring_detection_matching_duplicate_and_boundary_crossing(self, tmp_path: Path) -> None:
        from driftshield.contracts import DriftAlert
        from driftshield.evaluator import Evaluator

        cfg = DriftShieldConfig(
            stream=StreamConfig(
                scenario="recurring",
                n_events=2000,
                drift_start_sequence=500,
                recurrence_interval=400,
                seed=42,
            ),
            labels=LabelConfig(warmup_size=100, label_budget=800, monitor_rate=0.5, label_delay=50),
            output_dir=str(tmp_path),
        )

        sim = Simulator(cfg.stream, label_delay=50)
        evaluator = Evaluator(simulator=sim, warmup_size=100)

        # Transitions are at [500, 900, 1300, 1700]
        # Alerts:
        # 1. Alert in regime 0 [500-900): event 550, arrives at 550. Delay=50.
        # 2. Duplicate alert in regime 0: event 700, arrives at 700.
        # 3. Alert in regime 1 [900-1300): event 880 (regime 0), arrives at 930 (regime 1) -> boundary crossing!
        # 4. Alert in regime 2 [1300-1700): event 1350, arrives at 1350.
        alerts = [
            DriftAlert(
                alert_id="alt-1", event_id="evt-550", event_sequence=550, arrival_sequence=550,
                detection_delay_from_event=0, model_version="v1.0", loss=1,
                adwin_delta=0.002, adwin_estimation=0.4, adwin_width=50,
                monitoring_labels_count=20, monitoring_coverage=0.1,
            ),
            DriftAlert(
                alert_id="alt-2", event_id="evt-700", event_sequence=700, arrival_sequence=700,
                detection_delay_from_event=0, model_version="v1.0", loss=1,
                adwin_delta=0.002, adwin_estimation=0.5, adwin_width=60,
                monitoring_labels_count=30, monitoring_coverage=0.1,
            ),
            DriftAlert(
                alert_id="alt-3", event_id="evt-880", event_sequence=880, arrival_sequence=930,
                detection_delay_from_event=50, model_version="v1.0", loss=1,
                adwin_delta=0.002, adwin_estimation=0.4, adwin_width=65,
                monitoring_labels_count=35, monitoring_coverage=0.1,
            ),
            DriftAlert(
                alert_id="alt-4", event_id="evt-1350", event_sequence=1350, arrival_sequence=1350,
                detection_delay_from_event=0, model_version="v1.0", loss=1,
                adwin_delta=0.002, adwin_estimation=0.4, adwin_width=70,
                monitoring_labels_count=50, monitoring_coverage=0.1,
            ),
        ]

        metrics = evaluator.compute_metrics(alerts=alerts)
        m_eval = metrics.monitoring_evaluation

        assert m_eval is not None
        assert m_eval["scenario"] == "recurring"
        assert m_eval["matched_transitions_count"] == 2  # Regimes 0 and 2 matched
        assert 0 in m_eval["matched_transitions"]
        assert 2 in m_eval["matched_transitions"]
        assert m_eval["duplicate_alerts_count"] == 2
        assert m_eval["boundary_crossing_alerts_count"] == 1
        assert m_eval["boundary_crossing_alerts"][0]["event_regime"] == 0
        assert m_eval["boundary_crossing_alerts"][0]["arrival_regime"] == 1
        assert 1 in m_eval["missed_transitions"]  # Regime 1 had no event originating in regime 1
        assert 3 in m_eval["missed_transitions"]


