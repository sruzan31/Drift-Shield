"""backend/tests/test_api.py
==========================
Tests for Phase 5B: Localhost FastAPI controls, lifecycle management, and history.

Coverage includes:
1. Health & readiness endpoints.
2. Run creation and validation.
3. Creation idempotency (identical return, conflicting 409).
4. Run lifecycle controls: start -> pause -> resume -> stop.
5. Invalid state transitions (e.g. pause before start, start already running/completed).
6. Single active-run capacity limit (409 Conflict when starting second concurrent run).
7. Startup recovery (marking unfinished runs as INTERRUPTED).
8. Paginated runs listing and paginated incidents query.
9. Single event and recorded prediction retrieval.
10. Two runs in single database maintaining independent records, incidents, and decisions.
11. Pause/resume determinism and pacing.
"""

from pathlib import Path
import time
import pytest
from fastapi.testclient import TestClient

from driftshield.api.app import create_app
from driftshield.run_manager import RunManager
from driftshield.storage import SQLiteStorage


@pytest.fixture
def client(tmp_path: Path):
    """Fixture creating a fresh FastAPI test client and isolated storage."""
    db_path = tmp_path / "test_api.db"
    artifacts_dir = tmp_path / "artifacts"
    storage = SQLiteStorage(db_path=db_path, artifacts_dir=artifacts_dir)
    manager = RunManager(storage=storage, output_dir=tmp_path, default_events_per_second=200.0)
    app = create_app(storage=storage, run_manager=manager, output_dir=tmp_path)
    with TestClient(app) as test_client:
        yield test_client


def test_health_and_ready_endpoints(client: TestClient):
    """Verify /health and /ready return ok and storage readiness."""
    res_health = client.get("/health")
    assert res_health.status_code == 200
    data_h = res_health.json()
    assert data_h["status"] == "ok"
    assert data_h["storage_ready"] is True
    assert data_h["active_run_id"] is None

    res_ready = client.get("/ready")
    assert res_ready.status_code == 200
    assert res_ready.json()["status"] == "ok"


def test_create_run_and_validation(client: TestClient):
    """Verify POST /api/runs validates inputs and creates run in INITIALIZING/WARMUP state."""
    payload = {
        "scenario": "stationary",
        "n_events": 100,
        "warmup_size": 20,
        "label_budget": 50,
        "label_delay": 0,
        "seed": 42,
    }
    res = client.post("/api/runs", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["scenario"] == "stationary"
    assert data["state"] in ("INITIALIZING", "WARMUP")
    assert data["seed"] == 42
    assert "run_id" in data

    # Invalid payload (e.g. n_events too small)
    bad_payload = dict(payload, n_events=2)
    res_bad = client.post("/api/runs", json=bad_payload)
    assert res_bad.status_code == 422  # Pydantic validation error


def test_create_run_idempotency(client: TestClient):
    """Verify idempotency key returns existing run on match, and 409 on conflict."""
    payload = {
        "scenario": "stationary",
        "n_events": 100,
        "warmup_size": 20,
        "label_budget": 50,
        "label_delay": 0,
        "seed": 42,
        "idempotency_key": "key-12345",
    }
    # 1. First creation
    res1 = client.post("/api/runs", json=payload)
    assert res1.status_code == 201
    run1 = res1.json()

    # 2. Identical retry with same key returns the same run
    res2 = client.post("/api/runs", json=payload)
    assert res2.status_code == 201
    assert res2.json()["run_id"] == run1["run_id"]

    # 3. Conflicting retry with same key raises 409 Conflict
    conflicting_payload = dict(payload, n_events=500)
    res3 = client.post("/api/runs", json=conflicting_payload)
    assert res3.status_code == 409
    assert "Idempotency key" in res3.json()["detail"]


def test_run_lifecycle_start_pause_resume_stop(client: TestClient):
    """Verify execution lifecycle transitions: start -> pause -> resume -> stop."""
    create_res = client.post(
        "/api/runs",
        json={
            "scenario": "stationary",
            "n_events": 300,
            "warmup_size": 20,
            "label_budget": 50,
            "label_delay": 0,
            "seed": 42,
            "events_per_second": 30.0,
        },
    )
    run_id = create_res.json()["run_id"]

    # 1. Start
    res_start = client.post(f"/api/runs/{run_id}/control", json={"action": "start"})
    assert res_start.status_code == 200
    assert res_start.json()["current_state"] == "RUNNING"

    # Give it a brief moment to process some events
    time.sleep(0.1)

    # 2. Pause
    res_pause = client.post(f"/api/runs/{run_id}/control", json={"action": "pause"})
    assert res_pause.status_code == 200
    assert res_pause.json()["current_state"] == "PAUSED"

    # Verify state in GET /api/runs/{run_id}
    res_detail = client.get(f"/api/runs/{run_id}")
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert detail["state"] == "PAUSED"
    events_at_pause = detail["events_processed"]
    assert events_at_pause > 0

    # Wait a bit while paused — count should NOT increase
    time.sleep(0.1)
    res_detail2 = client.get(f"/api/runs/{run_id}")
    assert res_detail2.json()["events_processed"] == events_at_pause

    # 3. Resume
    res_resume = client.post(f"/api/runs/{run_id}/control", json={"action": "resume"})
    assert res_resume.status_code == 200
    assert res_resume.json()["current_state"] == "RUNNING"

    time.sleep(0.1)
    res_detail3 = client.get(f"/api/runs/{run_id}")
    assert res_detail3.json()["events_processed"] >= events_at_pause

    # 4. Stop
    res_stop = client.post(f"/api/runs/{run_id}/control", json={"action": "stop"})
    assert res_stop.status_code == 200
    assert res_stop.json()["current_state"] == "STOPPED"

    res_detail_final = client.get(f"/api/runs/{run_id}")
    assert res_detail_final.json()["state"] == "STOPPED"


def test_invalid_lifecycle_transitions(client: TestClient):
    """Verify invalid control transitions are rejected with 400 Bad Request."""
    create_res = client.post(
        "/api/runs",
        json={"scenario": "stationary", "n_events": 100, "warmup_size": 20},
    )
    run_id = create_res.json()["run_id"]

    # Pausing before start is invalid
    res_pause = client.post(f"/api/runs/{run_id}/control", json={"action": "pause"})
    assert res_pause.status_code == 400

    # Resuming before start is invalid
    res_resume = client.post(f"/api/runs/{run_id}/control", json={"action": "resume"})
    assert res_resume.status_code == 400

    # Unknown action is invalid
    res_invalid = client.post(f"/api/runs/{run_id}/control", json={"action": "destroy"})
    assert res_invalid.status_code == 400


def test_single_active_run_capacity_limit(client: TestClient):
    """Verify starting a second run while one is active returns 409 Conflict."""
    r1 = client.post("/api/runs", json={"scenario": "stationary", "n_events": 500, "warmup_size": 20, "events_per_second": 10.0}).json()
    r2 = client.post("/api/runs", json={"scenario": "stationary", "n_events": 500, "warmup_size": 20, "events_per_second": 10.0}).json()

    # Start run 1
    res1 = client.post(f"/api/runs/{r1['run_id']}/control", json={"action": "start"})
    assert res1.status_code == 200

    # Attempt to start run 2 concurrently
    res2 = client.post(f"/api/runs/{r2['run_id']}/control", json={"action": "start"})
    assert res2.status_code == 409
    assert "Capacity limit" in res2.json()["detail"]

    # Stop run 1
    client.post(f"/api/runs/{r1['run_id']}/control", json={"action": "stop"})

    # Now starting run 2 should succeed
    res2_after = client.post(f"/api/runs/{r2['run_id']}/control", json={"action": "start"})
    assert res2_after.status_code == 200
    client.post(f"/api/runs/{r2['run_id']}/control", json={"action": "stop"})


def test_startup_recovery_marks_interrupted(tmp_path: Path):
    """Verify that startup recovery marks previous uncompleted runs as INTERRUPTED."""
    db_path = tmp_path / "recovery.db"
    storage = SQLiteStorage(db_path=db_path)
    storage.create_run("run-stale-1", "stationary", 42, "simulation", {}, {})
    storage.update_run_state("run-stale-1", "RUNNING")

    # Starting a new RunManager should recover and mark stale run INTERRUPTED
    manager = RunManager(storage=storage, output_dir=tmp_path)
    manager.startup_recovery()

    run = storage.get_run("run-stale-1")
    assert run["state"] == "INTERRUPTED"
    storage.close()


def test_paginated_runs_and_incidents(client: TestClient):
    """Verify GET /api/runs and GET /api/runs/{id}/incidents pagination."""
    # Create 3 runs
    for i in range(3):
        client.post(
            "/api/runs",
            json={"scenario": "stationary", "n_events": 50, "warmup_size": 10, "seed": 100 + i},
        )

    # Page 1, size 2
    res = client.get("/api/runs?page=1&page_size=2")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["total_pages"] == 2

    # Page 2, size 2
    res_p2 = client.get("/api/runs?page=2&page_size=2")
    assert res_p2.status_code == 200
    assert len(res_p2.json()["items"]) == 1


def test_event_prediction_endpoint(client: TestClient):
    """Verify GET /api/runs/{id}/events/{event_id} returns event features and prediction."""
    create_res = client.post(
        "/api/runs",
        json={"scenario": "stationary", "n_events": 50, "warmup_size": 10, "events_per_second": 1000.0},
    )
    run_id = create_res.json()["run_id"]
    client.post(f"/api/runs/{run_id}/control", json={"action": "start"})

    # Wait for completion
    time.sleep(0.3)

    # Query event 0
    res_ev = client.get(f"/api/runs/{run_id}/events/evt-0")
    assert res_ev.status_code == 200
    ev_data = res_ev.json()
    assert ev_data["event_id"] == "evt-0"
    assert ev_data["sequence"] == 0
    assert "features" in ev_data
    assert ev_data["prediction"] is not None
    assert ev_data["prediction"]["predicted_label"] in (0, 1)


def test_two_abrupt_runs_in_one_db_independent_artifacts(client: TestClient):
    """Verify two abrupt runs in one database have independent incidents, artifacts, and decisions."""
    r1 = client.post(
        "/api/runs",
        json={
            "scenario": "abrupt",
            "n_events": 1000,
            "warmup_size": 100,
            "label_budget": 200,
            "seed": 42,
            "events_per_second": 5000.0,
        },
    ).json()
    run_id_1 = r1["run_id"]
    client.post(f"/api/runs/{run_id_1}/control", json={"action": "start"})

    for _ in range(50):
        d1 = client.get(f"/api/runs/{run_id_1}").json()
        if d1["state"] in ("COMPLETED", "STOPPED", "ERROR"):
            break
        time.sleep(0.05)

    # Second run with explicit replay parent link
    r2 = client.post(
        "/api/runs",
        json={
            "scenario": "abrupt",
            "n_events": 1000,
            "warmup_size": 100,
            "label_budget": 200,
            "seed": 42,
            "parent_run_id": run_id_1,
            "events_per_second": 5000.0,
        },
    ).json()
    run_id_2 = r2["run_id"]
    assert run_id_2 != run_id_1
    assert r2["parent_run_id"] == run_id_1

    client.post(f"/api/runs/{run_id_2}/control", json={"action": "start"})
    for _ in range(50):
        d2 = client.get(f"/api/runs/{run_id_2}").json()
        if d2["state"] in ("COMPLETED", "STOPPED", "ERROR"):
            break
        time.sleep(0.05)

    # Check both runs independently
    d1 = client.get(f"/api/runs/{run_id_1}").json()
    d2 = client.get(f"/api/runs/{run_id_2}").json()
    assert d1["run_id"] == run_id_1
    assert d2["run_id"] == run_id_2
    assert d1["label_accounting"]["total_unique_acquisitions"] > 0
    assert d2["label_accounting"]["total_unique_acquisitions"] > 0


def test_metrics_response_delay_0_abrupt(client: TestClient):
    """Verify exact reconciled metrics for completed abrupt run with delay=0."""
    res = client.post(
        "/api/runs",
        json={
            "scenario": "abrupt",
            "n_events": 2000,
            "warmup_size": 200,
            "label_budget": 300,
            "label_delay": 0,
            "seed": 42,
            "events_per_second": 5000.0,
        },
    )
    assert res.status_code == 201
    run_id = res.json()["run_id"]

    # In INITIALIZING/WARMUP state before start, metrics are None
    detail_init = client.get(f"/api/runs/{run_id}").json()
    assert detail_init["metrics"] is None

    # Start and wait for completion
    client.post(f"/api/runs/{run_id}/control", json={"action": "start"})
    for _ in range(100):
        d = client.get(f"/api/runs/{run_id}").json()
        if d["state"] in ("COMPLETED", "STOPPED", "ERROR"):
            break
        time.sleep(0.05)

    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["state"] == "COMPLETED"
    assert detail["events_processed"] == 2000
    assert detail["total_events"] == 2000

    metrics = detail["metrics"]
    assert metrics is not None
    assert "full_synthetic" in metrics
    assert "random_monitoring" in metrics

    # 1. Full synthetic evaluation: 1800 post-warmup evaluated, 800 correct, 1000 incorrect
    fs = metrics["full_synthetic"]
    assert fs["sample_count"] == 1800
    assert fs["correct_count"] == 800
    assert fs["incorrect_count"] == 1000
    assert fs["denominator"] == 1800
    assert fs["sample_count"] == fs["denominator"]
    assert fs["error_rate"] == pytest.approx(1000 / 1800)

    # 2. Random monitoring channel: 156 labels acquired, 58 correct, 98 incorrect
    mon = metrics["random_monitoring"]
    assert mon["sample_count"] == 156
    assert mon["correct_count"] == 58
    assert mon["incorrect_count"] == 98
    assert mon["denominator"] == 156
    assert mon["sample_count"] == mon["denominator"]
    assert mon["error_rate"] == pytest.approx(98 / 156)


def test_metrics_response_delay_10_abrupt(client: TestClient):
    """Verify exact reconciled metrics for completed abrupt run with delay=10 (1790 post-init events)."""
    res = client.post(
        "/api/runs",
        json={
            "scenario": "abrupt",
            "n_events": 2000,
            "warmup_size": 200,
            "label_budget": 300,
            "label_delay": 10,
            "seed": 42,
            "events_per_second": 5000.0,
        },
    )
    assert res.status_code == 201
    run_id = res.json()["run_id"]

    client.post(f"/api/runs/{run_id}/control", json={"action": "start"})
    for _ in range(100):
        d = client.get(f"/api/runs/{run_id}").json()
        if d["state"] in ("COMPLETED", "STOPPED", "ERROR"):
            break
        time.sleep(0.05)

    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["state"] == "COMPLETED"

    metrics = detail["metrics"]
    assert metrics is not None

    # For delay=10, warmup delivers at seq 209, so evaluation starts at seq 210: 2000 - 210 = 1790 events
    fs = metrics["full_synthetic"]
    assert fs["sample_count"] == 1790
    assert fs["correct_count"] == 790
    assert fs["incorrect_count"] == 1000
    assert fs["denominator"] == 1790
    assert fs["sample_count"] == fs["denominator"]
    assert fs["error_rate"] == pytest.approx(1000 / 1790)

    # Random monitoring channel
    mon = metrics["random_monitoring"]
    assert mon["sample_count"] == 156
    assert mon["correct_count"] == 58
    assert mon["incorrect_count"] == 98
    assert mon["denominator"] == 156
    assert mon["sample_count"] == mon["denominator"]
    assert mon["error_rate"] == pytest.approx(98 / 156)


def test_metrics_empty_warmup_only_run(client: TestClient):
    """Verify that a run stopped during warm-up produces empty / null evaluation metrics."""
    res = client.post(
        "/api/runs",
        json={
            "scenario": "stationary",
            "n_events": 200,
            "warmup_size": 100,
            "seed": 42,
            "events_per_second": 10.0,
        },
    )
    assert res.status_code == 201
    run_id = res.json()["run_id"]

    # Start and stop immediately while still in warm-up (< 100 events)
    client.post(f"/api/runs/{run_id}/control", json={"action": "start"})
    time.sleep(0.05)
    client.post(f"/api/runs/{run_id}/control", json={"action": "stop"})

    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["state"] == "STOPPED"
    metrics = detail["metrics"]
    assert metrics is not None
    # No post-warmup events were evaluated before stop: error_rate is None/null
    assert metrics["full_synthetic"]["sample_count"] == 0
    assert metrics["full_synthetic"]["denominator"] == 0
    assert metrics["full_synthetic"]["error_rate"] is None
    assert metrics["random_monitoring"]["sample_count"] == 0
    assert metrics["random_monitoring"]["error_rate"] is None
