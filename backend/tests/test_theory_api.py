"""backend.tests.test_theory_api
===============================
Unit and integration tests for DriftShield Phase 6B Theory Lab API.
"""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Generator

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from driftshield.api.app import create_app
from driftshield.api.theory import TheoryExperimentRunner, get_theory_runner
from driftshield.storage import SQLiteStorage
from driftshield.theory.rare_region import (
    min_deadline,
    theoretical_miss_probability,
)


@pytest.fixture
def test_env(tmp_path: Path) -> Generator[dict, None, None]:
    db_path = tmp_path / "test_theory.db"
    artifacts_dir = tmp_path / "artifacts"
    output_dir = tmp_path / "outputs"

    storage = SQLiteStorage(db_path=db_path, artifacts_dir=artifacts_dir)
    app = create_app(storage=storage, output_dir=output_dir)

    with TestClient(app) as client:
        yield {
            "client": client,
            "storage": storage,
            "output_dir": output_dir,
            "app": app,
        }


def test_create_rare_region_experiment_and_lifecycle(test_env: dict):
    client = test_env["client"]

    payload = {
        "mode": "rare-region",
        "p": 0.05,
        "q": 0.20,
        "deadline": 50,
        "delta": 0.05,
        "trials": 500,
        "seed": 42,
    }

    resp = client.post("/api/theory/experiments", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    exp_id = data["experiment_id"]
    assert exp_id.startswith("exp-rare-42-")
    assert data["status"] in ("QUEUED", "RUNNING", "COMPLETED")
    assert data["config"]["p"] == 0.05

    # Wait for completion
    for _ in range(50):
        detail_resp = client.get(f"/api/theory/experiments/{exp_id}")
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        if detail["status"] == "COMPLETED":
            break
        time.sleep(0.1)
    else:
        pytest.fail(f"Experiment {exp_id} did not complete in time")

    # Verify results
    results_resp = client.get(f"/api/theory/experiments/{exp_id}/results")
    assert results_resp.status_code == 200
    res = results_resp.json()

    # Analytical theory checks
    expected_miss = theoretical_miss_probability(0.05, 0.20, 50)
    assert pytest.approx(res["theoretical"]["miss_probability"], rel=1e-4) == expected_miss
    assert res["theoretical"]["min_deadline_for_delta"] == min_deadline(0.05, 0.20, 0.05)

    # Empirical checks
    assert res["empirical"]["trials_count"] == 500
    assert 0.0 <= res["empirical"]["miss_frequency"] <= 1.0
    assert 0.0 <= res["empirical"]["detection_frequency"] <= 1.0
    ci = res["empirical"]["confidence_interval_95"]
    assert len(ci) == 2
    assert ci[0] <= ci[1]


def test_create_finite_domain_experiment_and_lifecycle(test_env: dict):
    client = test_env["client"]

    payload = {
        "mode": "finite-domain",
        "n_domain": 16,
        "scenario": "single-last",
        "seed": 101,
    }

    resp = client.post("/api/theory/experiments", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    exp_id = data["experiment_id"]
    assert exp_id.startswith("exp-fini-101-")

    # Wait for completion
    for _ in range(50):
        detail_resp = client.get(f"/api/theory/experiments/{exp_id}")
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        if detail["status"] == "COMPLETED":
            break
        time.sleep(0.1)
    else:
        pytest.fail(f"Experiment {exp_id} did not complete in time")

    results_resp = client.get(f"/api/theory/experiments/{exp_id}/results")
    assert results_resp.status_code == 200
    res = results_resp.json()

    assert res["total_domain_size"] == 16
    assert res["queries_completed"] == 16
    assert res["is_complete"] is True
    assert res["unique_label_cost"] == 16
    assert res["discovered_change_indices"] == [15]
    assert res["evaluator_true_changed_indices"] == [15]
    assert res["evaluator_all_labels_correct"] is True
    assert len(res["records"]) == 16


def test_invalid_parameters_and_workload_limits(test_env: dict):
    client = test_env["client"]

    # 1. Invalid probability p > 1
    resp = client.post("/api/theory/experiments", json={
        "mode": "rare-region",
        "p": 1.5,
        "q": 0.2,
    })
    assert resp.status_code == 422

    # 2. Invalid probability q < 0
    resp = client.post("/api/theory/experiments", json={
        "mode": "rare-region",
        "p": 0.05,
        "q": -0.1,
    })
    assert resp.status_code == 422

    # 3. Workload exceeding maximum limit (trials * deadline > 50M)
    resp = client.post("/api/theory/experiments", json={
        "mode": "rare-region",
        "p": 0.05,
        "q": 0.2,
        "deadline": 100_000,
        "trials": 100_000,  # 100k * 100k = 10 Billion > 50M
    })
    assert resp.status_code == 422

    # 4. Unknown experiment 404
    resp = client.get("/api/theory/experiments/exp-unknown-999")
    assert resp.status_code == 404

    # 5. Invalid finite domain size N < 1
    resp = client.post("/api/theory/experiments", json={
        "mode": "finite-domain",
        "n_domain": 0,
    })
    assert resp.status_code == 422


def test_theory_export_artifacts(test_env: dict):
    client = test_env["client"]

    # Run a small finite domain experiment
    resp = client.post("/api/theory/experiments", json={
        "mode": "finite-domain",
        "n_domain": 8,
        "scenario": "no-change",
        "seed": 42,
    })
    exp_id = resp.json()["experiment_id"]

    for _ in range(50):
        if client.get(f"/api/theory/experiments/{exp_id}").json()["status"] == "COMPLETED":
            break
        time.sleep(0.1)

    # JSON export
    json_resp = client.get(f"/api/theory/experiments/{exp_id}/export?format=json")
    assert json_resp.status_code == 200
    assert "parameters" in json_resp.json() or "config" in json_resp.json() or "total_domain_size" in json_resp.json()

    # CSV export
    csv_resp = client.get(f"/api/theory/experiments/{exp_id}/export?format=csv")
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert "query_sequence" in csv_resp.text


def test_seed_reproducibility(test_env: dict):
    client = test_env["client"]

    p1 = {
        "mode": "rare-region",
        "p": 0.05,
        "q": 0.20,
        "deadline": 40,
        "delta": 0.05,
        "trials": 300,
        "seed": 777,
    }
    p2 = {
        "mode": "rare-region",
        "p": 0.05,
        "q": 0.20,
        "deadline": 40,
        "delta": 0.05,
        "trials": 300,
        "seed": 777,
    }

    id1 = client.post("/api/theory/experiments", json=p1).json()["experiment_id"]
    id2 = client.post("/api/theory/experiments", json=p2).json()["experiment_id"]

    for _ in range(50):
        s1 = client.get(f"/api/theory/experiments/{id1}").json()["status"]
        s2 = client.get(f"/api/theory/experiments/{id2}").json()["status"]
        if s1 == "COMPLETED" and s2 == "COMPLETED":
            break
        time.sleep(0.1)

    res1 = client.get(f"/api/theory/experiments/{id1}/results").json()
    res2 = client.get(f"/api/theory/experiments/{id2}/results").json()

    assert res1["empirical"]["miss_count"] == res2["empirical"]["miss_count"]
    assert res1["empirical"]["detection_count"] == res2["empirical"]["detection_count"]
    assert res1["empirical"]["total_labels_acquired"] == res2["empirical"]["total_labels_acquired"]


def test_startup_recovery_interrupted_theory(tmp_path: Path):
    db_path = tmp_path / "recovery_theory.db"
    artifacts_dir = tmp_path / "artifacts"
    output_dir = tmp_path / "outputs"

    storage = SQLiteStorage(db_path=db_path, artifacts_dir=artifacts_dir)
    # Insert dummy running experiment
    storage.create_theory_experiment(
        experiment_id="exp-dummy-1",
        mode="rare-region",
        seed=42,
        config_dict={"p": 0.05, "q": 0.2},
        artifacts_dir=str(output_dir / "exp-dummy-1"),
    )
    storage.update_theory_experiment_status("exp-dummy-1", "RUNNING")

    # Run startup recovery
    interrupted = storage.startup_recovery_theory()
    assert interrupted == 1

    exp = storage.get_theory_experiment("exp-dummy-1")
    assert exp["status"] == "INTERRUPTED"
    assert "shutdown" in exp["error_message"].lower()


def test_isolation_from_practical_simulation(test_env: dict):
    client = test_env["client"]

    # List practical runs before
    runs_before = client.get("/api/runs").json()["total"]

    # Run theory experiment
    resp = client.post("/api/theory/experiments", json={
        "mode": "finite-domain",
        "n_domain": 8,
        "scenario": "no-change",
        "seed": 42,
    })
    assert resp.status_code == 201
    exp_id = resp.json()["experiment_id"]

    for _ in range(50):
        if client.get(f"/api/theory/experiments/{exp_id}").json()["status"] == "COMPLETED":
            break
        time.sleep(0.1)

    # List practical runs after: must remain identical
    runs_after = client.get("/api/runs").json()["total"]
    assert runs_after == runs_before


def test_bounded_pending_capacity_and_rejection(tmp_path: Path):
    """Confirm pending capacity limit rejects excess requests without orphaned QUEUED records."""
    db_path = tmp_path / "capacity_test.db"
    artifacts_dir = tmp_path / "artifacts"
    output_dir = tmp_path / "outputs"

    storage = SQLiteStorage(db_path=db_path, artifacts_dir=artifacts_dir)
    # Runner with 1 worker and max 2 pending queue slots
    runner = TheoryExperimentRunner(
        storage=storage,
        output_dir=output_dir,
        max_workers=1,
        max_queued=2,
    )

    from driftshield.api.theory import CreateRareRegionRequest

    # Create 3 valid requests (1 running + 2 queued = full capacity)
    req1 = CreateRareRegionRequest(mode="rare-region", deadline=100, trials=5000, seed=1)
    req2 = CreateRareRegionRequest(mode="rare-region", deadline=100, trials=5000, seed=2)
    req3 = CreateRareRegionRequest(mode="rare-region", deadline=100, trials=5000, seed=3)

    exp1 = runner.enqueue_experiment(req1)
    exp2 = runner.enqueue_experiment(req2)
    exp3 = runner.enqueue_experiment(req3)

    assert exp1.status in ("QUEUED", "RUNNING")
    assert exp2.status == "QUEUED"
    assert exp3.status == "QUEUED"

    # 4th request must be rejected with HTTP 429
    req4 = CreateRareRegionRequest(mode="rare-region", deadline=100, trials=5000, seed=4)
    with pytest.raises(HTTPException) as exc_info:
        runner.enqueue_experiment(req4)
    assert exc_info.value.status_code == 429
    assert "capacity exceeded" in exc_info.value.detail.lower()

    # Verify no orphaned record was saved in DB for the rejected 4th request
    rows, total = storage.list_theory_experiments(limit=10)
    assert total == 3

    # Wait for all experiments to finish
    for exp in (exp1, exp2, exp3):
        for _ in range(100):
            r = storage.get_theory_experiment(exp.experiment_id)
            if r and r["status"] == "COMPLETED":
                break
            time.sleep(0.1)

    # Capacity status must be fully released back to 0 running and 0 queued
    status_map = runner.get_capacity_status()
    assert status_map["running"] == 0
    assert status_map["queued"] == 0


def test_practical_websocket_updates_during_theory_workload(test_env: dict):
    """Verify practical live run streams WebSocket updates concurrently with Theory Lab execution."""
    client = test_env["client"]

    # 1. Create a practical run
    create_payload = {
        "scenario": "abrupt",
        "stream_length": 300,
        "warmup_events": 50,
        "evaluation_window": 100,
        "seed": 42,
        "delay": 0,
        "budget": 200,
        "query_prob": 0.5,
    }
    resp = client.post("/api/runs", json=create_payload)
    assert resp.status_code == 201
    run_id = resp.json()["run_id"]

    # 2. Launch concurrent Theory Lab experiment
    theory_payload = {
        "mode": "rare-region",
        "p": 0.05,
        "q": 0.20,
        "deadline": 50,
        "trials": 500,
        "seed": 99,
    }
    theory_resp = client.post("/api/theory/experiments", json=theory_payload)
    assert theory_resp.status_code == 201
    theory_id = theory_resp.json()["experiment_id"]

    # 3. Connect WebSocket and start practical run
    start_resp = client.post(f"/api/runs/{run_id}/control", json={"action": "start"})
    assert start_resp.status_code == 200

    observed_intervals = []
    last_time = time.perf_counter()

    with client.websocket_connect(f"/api/runs/{run_id}/live", headers={"Origin": "http://localhost:5173"}) as ws:
        msg_count = 0
        while msg_count < 6:
            raw = ws.receive_text()
            now = time.perf_counter()
            data = json.loads(raw)
            assert data["run_id"] == run_id

            if msg_count > 0:
                delta_ms = (now - last_time) * 1000.0
                observed_intervals.append(delta_ms)
            last_time = now
            msg_count += 1

            if data["operational_state"] in ("COMPLETED", "PAUSED", "STOPPED"):
                break

    # Verify updates arrived continuously without stalling
    assert len(observed_intervals) >= 1
    # Observed intervals nominally ~500ms broadcast interval
    for interval in observed_intervals:
        assert 50.0 <= interval <= 2500.0  # Measured reasonable bound

    # Wait for theory experiment completion
    for _ in range(50):
        t_status = client.get(f"/api/theory/experiments/{theory_id}").json()["status"]
        if t_status == "COMPLETED":
            break
        time.sleep(0.1)

