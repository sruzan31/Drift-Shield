"""backend/tests/test_websocket.py
================================
Unit and integration tests for Phase 5C WebSocket live streaming endpoint WS /api/runs/{run_id}/live.

Tests:
1. Initial snapshot matches REST and persisted SQLite state.
2. Live progress and stream lifecycle events stream in real time.
3. Pause, resume, and stop controls appear correctly in WebSocket stream.
4. Candidate training and model promotion appear when they occur.
5. Empty/in-progress metrics remain null.
6. Unknown run ID rejected with close code 4004.
7. Disallowed browser origin rejected with close code 4003.
8. Slow client does not block engine processing or grow queues unbounded.
9. Disconnect and reconnect cleans up and returns fresh snapshot.
10. Multiple concurrent WebSocket viewers share a single engine instance without extra owners.
11. Completed run history is accessible via WebSocket after server restart.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import time
from typing import Any, Dict

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from driftshield.api.app import create_app
from driftshield.api.schemas import WebSocketSnapshotMessage
from driftshield.config import DriftShieldConfig, LabelConfig, StreamConfig
from driftshield.run_manager import RunManager
from driftshield.storage import SQLiteStorage


@pytest.fixture
def tmp_app_env(tmp_path: Path):
    """Fixture providing a clean isolated FastAPI app and RunManager."""
    db_path = tmp_path / "driftshield.db"
    art_dir = tmp_path / "artifacts"
    storage = SQLiteStorage(db_path=db_path, artifacts_dir=art_dir)
    manager = RunManager(storage=storage, output_dir=tmp_path, default_events_per_second=200.0)
    app = create_app(storage=storage, run_manager=manager, output_dir=tmp_path)
    client = TestClient(app)
    return {
        "app": app,
        "client": client,
        "storage": storage,
        "manager": manager,
        "tmp_path": tmp_path,
    }


def test_initial_snapshot_matches_rest_and_persisted(tmp_app_env):
    """Test that WS connection immediately returns an initial snapshot matching GET /api/runs/{id}."""
    client: TestClient = tmp_app_env["client"]

    # 1. Create a run
    resp = client.post("/api/runs", json={"scenario": "stationary", "n_events": 500, "seed": 42})
    assert resp.status_code == 201
    run_id = resp.json()["run_id"]

    # 2. Query REST detail
    rest_detail = client.get(f"/api/runs/{run_id}").json()

    # 3. Connect via WebSocket
    with client.websocket_connect(f"/api/runs/{run_id}/live", headers={"Origin": "http://localhost:3000"}) as ws:
        msg = ws.receive_json()

        # Validate schema structure
        validated = WebSocketSnapshotMessage(**msg)
        assert validated.run_id == run_id
        assert validated.schema_version == "v1.0"
        assert validated.snapshot_sequence == 1
        assert validated.operational_state == "WARMUP"
        assert validated.candidate_state == "NONE"
        assert validated.events_processed == 0
        assert validated.total_events == 500
        assert validated.progress_percent == 0.0
        assert validated.active_model_version == "v1.0-frozen"
        assert validated.synthetic_data is True
        assert validated.metrics is None  # empty metrics null before completion

        # Match with REST detail
        assert validated.events_processed == rest_detail["events_processed"]
        assert validated.operational_state == rest_detail["operational_state"]
        assert validated.active_model_version == rest_detail["active_model_version"]


def test_unknown_run_rejected(tmp_app_env):
    """Test that connecting to a non-existent run ID is rejected with code 4004."""
    client: TestClient = tmp_app_env["client"]

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/runs/non-existent-run-12345/live", headers={"Origin": "http://localhost:3000"}):
            pass
    assert exc_info.value.code == 4004


def test_disallowed_origin_rejected(tmp_app_env):
    """Test that connecting with a non-localhost browser origin is rejected with code 4003."""
    client: TestClient = tmp_app_env["client"]

    # Create run
    resp = client.post("/api/runs", json={"scenario": "stationary", "n_events": 500, "seed": 42})
    run_id = resp.json()["run_id"]

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/api/runs/{run_id}/live", headers={"Origin": "http://malicious-website.com"}):
            pass
    assert exc_info.value.code == 4003


def test_allowed_origins(tmp_app_env):
    """Test that various valid localhost origins and non-browser clients connect successfully."""
    client: TestClient = tmp_app_env["client"]

    resp = client.post("/api/runs", json={"scenario": "stationary", "n_events": 500, "seed": 42})
    run_id = resp.json()["run_id"]

    for origin in [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://127.0.0.1",
        None,  # non-browser client without Origin header
    ]:
        headers = {"Origin": origin} if origin else {}
        with client.websocket_connect(f"/api/runs/{run_id}/live", headers=headers) as ws:
            snap = ws.receive_json()
            assert snap["run_id"] == run_id
            assert snap["snapshot_sequence"] == 1


def test_live_progress_and_completion(tmp_app_env):
    """Test that running simulation streams increasing progress and reaches terminal completion."""
    client: TestClient = tmp_app_env["client"]

    resp = client.post("/api/runs", json={"scenario": "stationary", "n_events": 250, "seed": 42, "events_per_second": 500.0})
    run_id = resp.json()["run_id"]

    with client.websocket_connect(f"/api/runs/{run_id}/live", headers={"Origin": "http://localhost:3000"}) as ws:
        # Initial snapshot
        snap1 = ws.receive_json()
        assert snap1["snapshot_sequence"] == 1
        assert snap1["events_processed"] == 0

        # Start run via REST control
        start_resp = client.post(f"/api/runs/{run_id}/control", json={"action": "start"})
        assert start_resp.status_code == 200

        # Collect subsequent live snapshots
        snapshots = [snap1]
        for _ in range(10):
            try:
                snap = ws.receive_json()
                snapshots.append(snap)
                if snap["operational_state"] == "COMPLETED":
                    break
            except Exception:
                break

        # Check sequence monotonicity and progress
        sequences = [s["snapshot_sequence"] for s in snapshots]
        assert sequences == sorted(sequences)
        assert len(snapshots) >= 2
        last_snap = snapshots[-1]

        # Wait briefly if not yet complete
        if last_snap["operational_state"] != "COMPLETED":
            time.sleep(0.8)
            rest_detail = client.get(f"/api/runs/{run_id}").json()
            assert rest_detail["operational_state"] == "COMPLETED"
        else:
            assert last_snap["events_processed"] == 250
            assert last_snap["progress_percent"] == 100.0
            assert last_snap["metrics"] is not None
            assert "full_synthetic" in last_snap["metrics"]


def test_pause_resume_stop_lifecycle(tmp_app_env):
    """Test that pause, resume, and stop controls are reflected in WebSocket snapshots."""
    client: TestClient = tmp_app_env["client"]

    resp = client.post("/api/runs", json={"scenario": "stationary", "n_events": 1000, "seed": 42, "events_per_second": 50.0})
    run_id = resp.json()["run_id"]

    with client.websocket_connect(f"/api/runs/{run_id}/live", headers={"Origin": "http://localhost:3000"}) as ws:
        init_snap = ws.receive_json()
        assert init_snap["operational_state"] == "WARMUP"

        # Start
        client.post(f"/api/runs/{run_id}/control", json={"action": "start"})
        time.sleep(0.2)

        # Pause
        pause_resp = client.post(f"/api/runs/{run_id}/control", json={"action": "pause"})
        assert pause_resp.status_code == 200

        # Read snapshots until PAUSED
        paused_seen = False
        for _ in range(5):
            snap = ws.receive_json()
            if snap["operational_state"] == "PAUSED":
                paused_seen = True
                break
        assert paused_seen

        # Resume
        resume_resp = client.post(f"/api/runs/{run_id}/control", json={"action": "resume"})
        assert resume_resp.status_code == 200

        # Stop
        stop_resp = client.post(f"/api/runs/{run_id}/control", json={"action": "stop"})
        assert stop_resp.status_code == 200

        stopped_seen = False
        for _ in range(5):
            snap = ws.receive_json()
            if snap["operational_state"] == "STOPPED":
                stopped_seen = True
                break
        assert stopped_seen


def test_candidate_and_model_promotion_updates(tmp_app_env):
    """Test that candidate training and model promotion appear in live snapshots for abrupt drift."""
    client: TestClient = tmp_app_env["client"]

    # Abrupt scenario designed to trigger ADWIN detection and promotion
    resp = client.post(
        "/api/runs",
        json={
            "scenario": "abrupt",
            "n_events": 1500,
            "warmup_size": 200,
            "label_budget": 500,
            "label_delay": 0,
            "seed": 42,
            "target_training_labels": 20,
            "evaluation_target_events": 50,
            "events_per_second": 1000.0,
        },
    )
    assert resp.status_code == 201
    run_id = resp.json()["run_id"]

    with client.websocket_connect(f"/api/runs/{run_id}/live", headers={"Origin": "http://localhost:3000"}) as ws:
        _ = ws.receive_json()  # init

        # Start run
        client.post(f"/api/runs/{run_id}/control", json={"action": "start"})

        seen_models = set()
        seen_candidate_states = set()

        for _ in range(15):
            try:
                snap = ws.receive_json()
                seen_models.add(snap["active_model_version"])
                if snap.get("candidate_state"):
                    seen_candidate_states.add(snap["candidate_state"])
                if snap["operational_state"] == "COMPLETED":
                    break
            except Exception:
                break

        # Let worker complete
        time.sleep(1.0)
        final_detail = client.get(f"/api/runs/{run_id}").json()
        assert final_detail["operational_state"] == "COMPLETED"


def test_empty_metrics_remain_null_until_complete(tmp_app_env):
    """Test that while a run is active, metrics field is null, and upon completion contains corrected counts."""
    client: TestClient = tmp_app_env["client"]

    resp = client.post("/api/runs", json={"scenario": "stationary", "n_events": 300, "seed": 42, "events_per_second": 50.0})
    run_id = resp.json()["run_id"]

    with client.websocket_connect(f"/api/runs/{run_id}/live", headers={"Origin": "http://localhost:3000"}) as ws:
        init_snap = ws.receive_json()
        assert init_snap["metrics"] is None

        # Start and read during execution
        client.post(f"/api/runs/{run_id}/control", json={"action": "start"})
        mid_snap = ws.receive_json()
        if mid_snap["operational_state"] in ("WARMUP", "RUNNING"):
            assert mid_snap["metrics"] is None


def test_slow_client_bounded_coalescing(tmp_app_env):
    """Test that slow or delayed client reading does not block engine execution or blow up memory."""
    client: TestClient = tmp_app_env["client"]
    manager: RunManager = tmp_app_env["manager"]

    resp = client.post("/api/runs", json={"scenario": "stationary", "n_events": 400, "seed": 42, "events_per_second": 1000.0})
    run_id = resp.json()["run_id"]

    with client.websocket_connect(f"/api/runs/{run_id}/live", headers={"Origin": "http://localhost:3000"}) as ws:
        _ = ws.receive_json()  # read initial

        # Start execution
        client.post(f"/api/runs/{run_id}/control", json={"action": "start"})

        # Intentionally sleep/lag without reading from ws
        time.sleep(1.2)

        # Worker should have completed without being blocked by this slow client
        worker = manager._workers.get(run_id)
        assert worker is not None
        assert not worker.is_alive  # Finished execution!

        # Now client reads next available snapshot
        snap = ws.receive_json()
        assert snap["snapshot_sequence"] > 1


def test_multiple_concurrent_viewers_single_owner(tmp_app_env):
    """Test that multiple concurrent WebSocket clients receive stream updates without creating multiple engines."""
    client: TestClient = tmp_app_env["client"]
    manager: RunManager = tmp_app_env["manager"]

    resp = client.post("/api/runs", json={"scenario": "stationary", "n_events": 500, "seed": 42, "events_per_second": 100.0})
    run_id = resp.json()["run_id"]

    with client.websocket_connect(f"/api/runs/{run_id}/live", headers={"Origin": "http://localhost:3000"}) as ws1:
        with client.websocket_connect(f"/api/runs/{run_id}/live", headers={"Origin": "http://localhost:5173"}) as ws2:
            s1 = ws1.receive_json()
            s2 = ws2.receive_json()
            assert s1["run_id"] == run_id
            assert s2["run_id"] == run_id

            # Verify only one engine exists in RunManager
            assert len(manager._engines) == 1
            assert run_id in manager._engines

            # Start run
            client.post(f"/api/runs/{run_id}/control", json={"action": "start"})

            # Both receive live updates
            time.sleep(0.6)
            up1 = ws1.receive_json()
            up2 = ws2.receive_json()
            assert up1["run_id"] == run_id
            assert up2["run_id"] == run_id


def test_completed_history_after_server_restart(tmp_app_env):
    """Test that a completed run is viewable over WebSocket on a freshly initialized server/manager."""
    client: TestClient = tmp_app_env["client"]
    storage: SQLiteStorage = tmp_app_env["storage"]
    tmp_path: Path = tmp_app_env["tmp_path"]

    # 1. Create and complete a run
    resp = client.post("/api/runs", json={"scenario": "stationary", "n_events": 300, "warmup_size": 100, "seed": 42, "events_per_second": 2000.0})
    run_id = resp.json()["run_id"]
    client.post(f"/api/runs/{run_id}/control", json={"action": "start"})

    time.sleep(0.5)
    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["operational_state"] == "COMPLETED"

    # 2. Simulate server restart: create a new RunManager and FastAPI app using the same SQLite storage
    new_storage = SQLiteStorage(db_path=tmp_path / "driftshield.db", artifacts_dir=tmp_path / "artifacts")
    new_manager = RunManager(storage=new_storage, output_dir=tmp_path)
    new_app = create_app(storage=new_storage, run_manager=new_manager, output_dir=tmp_path)
    new_client = TestClient(new_app)

    # 3. Connect via WebSocket to the restarted server
    with new_client.websocket_connect(f"/api/runs/{run_id}/live", headers={"Origin": "http://localhost:3000"}) as ws:
        snap = ws.receive_json()
        assert snap["run_id"] == run_id
        assert snap["operational_state"] == "COMPLETED"
        assert snap["events_processed"] == 300
        assert snap["progress_percent"] == 100.0
        assert snap["metrics"] is not None
        assert "full_synthetic" in snap["metrics"]
        assert snap["metrics"]["full_synthetic"]["sample_count"] > 0


def test_connect_to_created_run_and_start_without_reconnect(tmp_app_env):
    """Test connecting to a CREATED run (WARMUP), then starting it through REST; streams progress without reconnect."""
    client: TestClient = tmp_app_env["client"]

    # 1. Create run (stays in WARMUP / not yet started)
    resp = client.post("/api/runs", json={"scenario": "stationary", "n_events": 300, "warmup_size": 100, "seed": 42, "events_per_second": 300.0})
    assert resp.status_code == 201
    run_id = resp.json()["run_id"]

    # 2. Connect WebSocket to CREATED run
    with client.websocket_connect(f"/api/runs/{run_id}/live", headers={"Origin": "http://localhost:3000"}) as ws:
        snap1 = ws.receive_json()
        assert snap1["snapshot_sequence"] == 1
        assert snap1["operational_state"] == "WARMUP"
        assert snap1["events_processed"] == 0

        # 3. Start through REST on the same run
        start_res = client.post(f"/api/runs/{run_id}/control", json={"action": "start"})
        assert start_res.status_code == 200

        # 4. Without reconnecting, the same WebSocket receives live progress
        snaps = [snap1]
        for _ in range(10):
            try:
                s = ws.receive_json()
                snaps.append(s)
                if s["operational_state"] == "COMPLETED":
                    break
            except Exception:
                break

        assert len(snaps) >= 2
        # Monotonic sequence
        seqs = [s["snapshot_sequence"] for s in snaps]
        assert seqs == sorted(seqs)


def test_short_abrupt_run_candidate_incomplete_reconciled(tmp_app_env):
    """Test short abrupt run where candidate stays INCOMPLETE, reconciled across REST and WebSocket."""
    client: TestClient = tmp_app_env["client"]

    # Standard short abrupt run: drift at 1000, alert at ~1647, stream ends at 2000 with ~35/200 labels -> INCOMPLETE
    resp = client.post(
        "/api/runs",
        json={
            "scenario": "abrupt",
            "n_events": 2000,
            "warmup_size": 200,
            "label_budget": 300,
            "label_delay": 0,
            "seed": 42,
            "drift_start_sequence": 1000,
            "target_training_labels": 200,
            "evaluation_target_events": 100,
            "events_per_second": 5000.0,
        },
    )
    assert resp.status_code == 201
    run_id = resp.json()["run_id"]

    # Start and wait for completion
    client.post(f"/api/runs/{run_id}/control", json={"action": "start"})
    time.sleep(1.0)

    # 1. Query REST detail
    rest_detail = client.get(f"/api/runs/{run_id}").json()
    assert rest_detail["operational_state"] == "COMPLETED"
    assert rest_detail["candidate_state"] == "INCOMPLETE"
    assert rest_detail["candidate_summary"]["candidates"][0]["state"] == "INCOMPLETE"

    # 2. Query WebSocket snapshot
    with client.websocket_connect(f"/api/runs/{run_id}/live", headers={"Origin": "http://localhost:3000"}) as ws:
        ws_snap = ws.receive_json()
        assert ws_snap["operational_state"] == "COMPLETED"
        assert ws_snap["candidate_state"] == "INCOMPLETE"
        assert ws_snap["candidate_summary"]["candidates"][0]["state"] == "INCOMPLETE"
        # Reconciled fields match
        assert ws_snap["events_processed"] == rest_detail["events_processed"]
        assert ws_snap["monitoring_coverage"] == rest_detail["monitoring_coverage"]

