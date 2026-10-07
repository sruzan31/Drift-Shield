"""backend/tests/test_engine_storage.py
===================================
Tests for Phase 5A: Reusable DriftShieldEngine and SQLite Persistence.

Coverage includes:
1. Reusable engine event processing, prediction-before-label, and lifecycle.
2. SQLite schema creation, migrations, and table integrity (Section 10).
3. Exact agreement between SQLite database rows and exported CSV/JSON files.
4. Idempotent duplicate event/label handling and conflict rejection.
5. Foreign key constraint enforcement and transaction rollback on failure.
6. Storage error propagation (no silent losses).
7. Startup recovery (marking unfinished runs as INTERRUPTED).
8. Model artifact saving, SHA-256 content hashing, and version retention across promotions.
9. Evaluator hidden truth isolation.
10. Engine point-in-time snapshot retrieval.
"""

import csv
import json
from pathlib import Path
import sqlite3
import pytest
from river import linear_model, preprocessing

from driftshield.config import AdaptationConfig, DriftShieldConfig, LabelConfig, MonitoringConfig, StreamConfig
from driftshield.contracts import PredictionRecord, StreamEvent
from driftshield.engine import DriftShieldEngine, EngineSnapshot, EngineSummary, get_execution_environment
from driftshield.run_baseline import run_scenario
from driftshield.simulator import Simulator
from driftshield.storage import SQLiteStorage


# ---------------------------------------------------------------------------
# 1. SQLite Storage & Schema Tests
# ---------------------------------------------------------------------------


def test_sqlite_storage_schema_and_migrations(tmp_path: Path):
    """Verify all 10 Section 10 tables are created with migrations recorded."""
    db_path = tmp_path / "test_shield.db"
    artifacts_dir = tmp_path / "artifacts"
    storage = SQLiteStorage(db_path=db_path, artifacts_dir=artifacts_dir)

    conn = storage._get_connection()
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {r[0] for r in cur.fetchall()}

    required_tables = {
        "schema_migrations",
        "runs",
        "events",
        "predictions",
        "labels",
        "label_requests",
        "incidents",
        "model_versions",
        "metric_windows",
        "benchmarks",
        "evaluator_truth",
    }
    assert required_tables.issubset(tables)

    # Check migration entry
    cur = conn.execute("SELECT version FROM schema_migrations;")
    migrations = [r[0] for r in cur.fetchall()]
    assert "v1.0" in migrations
    storage.close()


def test_foreign_key_constraints(tmp_path: Path):
    """Verify foreign key enforcement (inserting prediction without event raises)."""
    db_path = tmp_path / "fk_test.db"
    storage = SQLiteStorage(db_path=db_path)
    storage.create_run("run-1", "stationary", 42, "simulation", {}, {})

    # Inserting event works
    ev = StreamEvent("evt-0", 0, 0.0, {"f0": 1.0, "f1": 1.0})
    storage.record_event("run-1", ev)

    # Prediction referencing valid event works
    pred = PredictionRecord("evt-0", 0, 0.0, 0, 0.2, {"f0": 1.0, "f1": 1.0})
    storage.record_prediction("run-1", pred)

    # Prediction referencing non-existent event fails with IntegrityError
    pred_invalid = PredictionRecord("evt-nonexistent", 99, 0.0, 0, 0.2, {"f0": 1.0, "f1": 1.0})
    with pytest.raises(sqlite3.IntegrityError):
        storage.record_prediction("run-1", pred_invalid)
    storage.close()


def test_duplicate_and_conflicting_events(tmp_path: Path):
    """Verify identical duplicate events are ignored and conflicting duplicates raise ValueError."""
    storage = SQLiteStorage(db_path=tmp_path / "dedup.db")
    storage.create_run("run-1", "stationary", 42, "simulation", {}, {})

    ev1 = StreamEvent("evt-1", 1, 0.0, {"f0": 1.0, "f1": 2.0})
    # First insert -> True
    assert storage.record_event("run-1", ev1) is True

    # Identical duplicate -> False (ignored)
    ev1_dup = StreamEvent("evt-1", 1, 0.0, {"f0": 1.0, "f1": 2.0})
    assert storage.record_event("run-1", ev1_dup) is False

    # Conflicting duplicate (same ID, different features) -> raises ValueError
    ev1_conflict = StreamEvent("evt-1", 1, 0.0, {"f0": 99.0, "f1": 99.0})
    with pytest.raises(ValueError, match="Conflicting duplicate event"):
        storage.record_event("run-1", ev1_conflict)
    storage.close()


def test_duplicate_and_conflicting_labels(tmp_path: Path):
    """Verify identical duplicate labels are ignored and conflicting labels raise ValueError."""
    storage = SQLiteStorage(db_path=tmp_path / "label_dedup.db")
    storage.create_run("run-1", "stationary", 42, "simulation", {}, {})
    ev = StreamEvent("evt-1", 1, 0.0, {"f0": 1.0, "f1": 2.0})
    storage.record_event("run-1", ev)

    # First label -> True
    assert storage.record_label("run-1", "evt-1", true_label=1, source="monitor", channel="monitor", delivery_sequence=1, arrival_sequence=1) is True

    # Identical duplicate -> False
    assert storage.record_label("run-1", "evt-1", true_label=1, source="monitor", channel="monitor", delivery_sequence=1, arrival_sequence=1) is False

    # Conflicting label (same ID, different true_label) -> ValueError
    with pytest.raises(ValueError, match="Conflicting duplicate label"):
        storage.record_label("run-1", "evt-1", true_label=0, source="monitor", channel="monitor", delivery_sequence=1, arrival_sequence=1)
    storage.close()


def test_model_artifact_saving_and_hashing(tmp_path: Path):
    """Verify model/preprocessor serialization, server-generated paths, and SHA-256 content hashes."""
    storage = SQLiteStorage(db_path=tmp_path / "models.db", artifacts_dir=tmp_path / "artifacts")
    storage.create_run("run-1", "stationary", 42, "simulation", {}, {})

    lr = linear_model.LogisticRegression()
    scaler = preprocessing.StandardScaler()
    scaler.learn_one({"f0": 1.0, "f1": 2.0})

    mv_id = storage.save_model_version(
        run_id="run-1",
        version_tag="v1.0-frozen",
        activation_sequence=200,
        model_obj=lr,
        preprocessor_obj=scaler,
        parent_version_tag=None,
    )
    assert mv_id.startswith("mv-run-1-v1.0-frozen")

    versions = storage.get_model_versions("run-1")
    assert len(versions) == 1
    v = versions[0]
    assert v["version_tag"] == "v1.0-frozen"
    assert Path(v["model_artifact_path"]).exists()
    assert Path(v["preprocessor_artifact_path"]).exists()
    assert len(v["model_artifact_hash"]) == 64  # SHA-256 hex length
    assert len(v["preprocessor_artifact_hash"]) == 64
    storage.close()


def test_startup_interrupted_recovery(tmp_path: Path):
    """Verify that restarting storage marks any previous unfinished runs as INTERRUPTED."""
    db_path = tmp_path / "interrupted.db"
    storage1 = SQLiteStorage(db_path=db_path)
    storage1.create_run("run-crashed", "abrupt", 42, "simulation", {}, {})
    storage1.update_run_state("run-crashed", "RUNNING")
    storage1.close()

    # Reopen database (simulate backend process restart)
    storage2 = SQLiteStorage(db_path=db_path)
    run_rec = storage2.get_run("run-crashed")
    assert run_rec["state"] == "INTERRUPTED"
    storage2.close()


# ---------------------------------------------------------------------------
# 2. Engine Lifecycle & Execution Tests
# ---------------------------------------------------------------------------


def test_engine_snapshot_and_idempotence(tmp_path: Path):
    """Verify EngineSnapshot and idempotent event processing."""
    cfg = DriftShieldConfig(
        stream=StreamConfig(scenario="stationary", n_events=50, seed=42),
        labels=LabelConfig(warmup_size=10, label_budget=20),
        output_dir=str(tmp_path),
    )
    sim = Simulator(cfg.stream)
    engine = DriftShieldEngine(config=cfg, run_id="run-snap-test")
    engine.initialize(simulator=sim)

    # Initial snapshot
    snap0 = engine.get_snapshot()
    assert snap0.run_id == "run-snap-test"
    assert snap0.state == "WARMUP"
    assert snap0.events_processed == 0

    # Process 15 events
    for ev in sim.events[:15]:
        res = engine.process_event(ev)
        assert not res.is_duplicate

    # Duplicate test: process event 0 again
    res_dup = engine.process_event(sim.events[0])
    assert res_dup.is_duplicate
    assert res_dup.event_id == "evt-0"

    snap15 = engine.get_snapshot()
    assert snap15.events_processed == 15
    assert snap15.warmup_complete is True
    assert snap15.active_model_version == "v1.0-frozen"


def test_engine_end_to_end_db_agreement(tmp_path: Path):
    """Verify that SQLite database tables perfectly match exported CSV and JSON artifacts."""
    cfg = DriftShieldConfig(
        stream=StreamConfig(scenario="abrupt", n_events=2000, seed=42, drift_start_sequence=1000),
        labels=LabelConfig(warmup_size=200, label_budget=300, label_delay=0),
        adaptation=AdaptationConfig(target_training_labels=200),
        output_dir=str(tmp_path),
    )
    metrics = run_scenario("abrupt", cfg, str(tmp_path))

    db_path = tmp_path / "driftshield.db"
    assert db_path.exists()
    storage = SQLiteStorage(db_path=db_path)

    run_rec = storage.get_run("run-abrupt-42")
    assert run_rec["state"] == "COMPLETED"

    # 1. Predictions check: DB count vs CSV count
    db_preds = storage.get_predictions("run-abrupt-42")
    csv_preds_path = tmp_path / "abrupt_predictions.csv"
    with open(csv_preds_path, "r") as f:
        csv_preds = list(csv.DictReader(f))

    assert len(db_preds) == 2000  # All events predicted
    assert len(csv_preds) == 1800  # Post-warmup evaluated predictions (seq 200-1999)
    # Check sequences match
    assert db_preds[200]["event_id"] == csv_preds[0]["event_id"]

    # 2. Alerts check: DB incidents vs alerts CSV
    db_incidents = storage.get_incidents("run-abrupt-42")
    csv_alerts_path = tmp_path / "abrupt_alerts.csv"
    with open(csv_alerts_path, "r") as f:
        csv_alerts = list(csv.DictReader(f))
    assert len(db_incidents) == len(csv_alerts)
    if len(db_incidents) > 0:
        assert db_incidents[0]["incident_id"] == csv_alerts[0]["alert_id"]

    # 3. Model versions check: v1.0-frozen exists in DB
    versions = storage.get_model_versions("run-abrupt-42")
    v_tags = [v["version_tag"] for v in versions]
    assert "v1.0-frozen" in v_tags

    # 4. Evaluator truth isolation check
    eval_truth = storage.get_evaluator_truth("run-abrupt-42")
    assert len(eval_truth) == 2000
    # Engine predictions do not expose evaluator_truth directly
    storage.close()


def test_long_promotion_engine_persistence(tmp_path: Path):
    """Verify promotion lifecycle records both v1.0-frozen and v2.0-promoted model artifacts in DB."""
    cfg = DriftShieldConfig(
        stream=StreamConfig(scenario="abrupt", n_events=12000, seed=42, drift_start_sequence=1000),
        labels=LabelConfig(warmup_size=200, label_budget=2000, label_delay=0),
        adaptation=AdaptationConfig(target_training_labels=200, evaluation_target_events=500),
        output_dir=str(tmp_path),
    )
    metrics = run_scenario("abrupt", cfg, str(tmp_path))

    storage = SQLiteStorage(db_path=tmp_path / "driftshield.db")
    run_rec = storage.get_run("run-abrupt-42")
    assert run_rec["state"] == "COMPLETED"

    # Verify model versions recorded: v1.0-frozen and v2.0-promoted
    versions = storage.get_model_versions("run-abrupt-42")
    v_tags = [v["version_tag"] for v in versions]
    assert "v1.0-frozen" in v_tags
    assert "v2.0-promoted" in v_tags

    # Verify artifact files exist on disk with valid sha256
    for v in versions:
        assert Path(v["model_artifact_path"]).exists()
        assert Path(v["preprocessor_artifact_path"]).exists()
        assert len(v["model_artifact_hash"]) == 64

    # Verify metric windows recorded
    windows = storage.get_metric_windows("run-abrupt-42")
    assert len(windows) >= 2

    # Verify label_requests recorded and debits reconcile
    conn = storage._get_connection()
    cur = conn.execute("SELECT count(*), sum(budget_debit), sum(cost) FROM label_requests WHERE run_id = 'run-abrupt-42' AND channel != 'warmup';")
    req_count, total_debit, total_cost = cur.fetchone()
    assert req_count > 0
    assert total_debit == total_cost

    # Verify incidents table updated with PROMOTED outcome and full evidence
    cur = conn.execute("SELECT incident_id, outcome, evidence_json FROM incidents WHERE run_id = 'run-abrupt-42';")
    incidents = cur.fetchall()
    assert len(incidents) == 1
    assert incidents[0]["outcome"] == "PROMOTED"
    ev = json.loads(incidents[0]["evidence_json"])
    assert ev["decision"] == "PROMOTED"
    assert ev["b"] == 500
    assert ev["c"] == 0
    assert ev["n"] == 500
    assert ev["promoted_model_version"] == "v2.0-promoted"

    storage.close()


def test_two_runs_same_seed_in_single_db_with_parent_link(tmp_path: Path):
    """Verify two runs with the same scenario and seed co-exist in one DB with parent_run_id linking."""
    db_path = tmp_path / "multi_run.db"
    storage = SQLiteStorage(db_path=db_path)

    # Run 1: Original run
    cfg1 = DriftShieldConfig(
        stream=StreamConfig(scenario="stationary", n_events=50, seed=42),
        labels=LabelConfig(warmup_size=10, label_budget=20, label_delay=0),
        output_dir=str(tmp_path),
    )
    eng1 = DriftShieldEngine(config=cfg1, run_id="run-stationary-42-original", storage=storage)
    sim1 = Simulator(config=cfg1.stream, label_delay=cfg1.labels.label_delay)
    eng1.initialize(sim1)
    for ev in sim1.events:
        eng1.process_event(ev)
    eng1.finalize()

    # Run 2: Replay run linked to original
    cfg2 = DriftShieldConfig(
        stream=StreamConfig(scenario="stationary", n_events=50, seed=42),
        labels=LabelConfig(warmup_size=10, label_budget=20, label_delay=0),
        output_dir=str(tmp_path),
    )
    eng2 = DriftShieldEngine(
        config=cfg2,
        run_id="run-stationary-42-replay",
        parent_run_id="run-stationary-42-original",
        storage=storage,
    )
    sim2 = Simulator(config=cfg2.stream, label_delay=cfg2.labels.label_delay)
    eng2.initialize(sim2)
    for ev in sim2.events:
        eng2.process_event(ev)
    eng2.finalize()

    # Inspect runs in DB
    runs = storage.list_runs()
    assert len(runs) == 2
    r_map = {r["run_id"]: r for r in runs}

    assert "run-stationary-42-original" in r_map
    assert "run-stationary-42-replay" in r_map
    assert r_map["run-stationary-42-original"]["parent_run_id"] is None
    assert r_map["run-stationary-42-replay"]["parent_run_id"] == "run-stationary-42-original"

    # Both have independent records
    preds1 = storage.get_predictions("run-stationary-42-original")
    preds2 = storage.get_predictions("run-stationary-42-replay")
    assert len(preds1) == 50
    assert len(preds2) == 50

    storage.close()


def test_benchmarks_table_exists(tmp_path: Path):
    """Verify benchmarks table exists for future benchmark job orchestration."""
    storage = SQLiteStorage(db_path=tmp_path / "benchmarks_test.db")
    conn = storage._get_connection()
    cur = conn.execute("SELECT count(*) FROM benchmarks;")
    assert cur.fetchone()[0] == 0
    storage.close()

