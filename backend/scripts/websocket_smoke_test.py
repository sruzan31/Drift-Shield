"""backend/scripts/websocket_smoke_test.py
======================================
Real network WebSocket smoke test for DriftShield Phase 5C.

Spawns a real localhost Uvicorn server on an ephemeral port, exercises REST creation
and control endpoints, connects a real TCP/IP WebSocket client using `websockets`,
and records update interval distributions, snapshot schema compliance, and lifecycle
responsiveness.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import statistics
import sys
import time
import threading
from typing import Any, Dict, List

import httpx
import uvicorn
import websockets

# Add backend/src to sys.path
repo_root = Path(__file__).resolve().parent.parent.parent
backend_src = repo_root / "backend" / "src"
if str(backend_src) not in sys.path:
    sys.path.insert(0, str(backend_src))

from driftshield.api.app import create_app
from driftshield.api.schemas import WebSocketSnapshotMessage
from driftshield.run_manager import RunManager
from driftshield.storage import SQLiteStorage


class ServerThread(threading.Thread):
    """Runs Uvicorn in a dedicated background daemon thread."""

    def __init__(self, app, host: str = "127.0.0.1", port: int = 8765) -> None:
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.config = uvicorn.Config(app=app, host=host, port=port, log_level="warning")
        self.server = uvicorn.Server(config=self.config)

    def run(self) -> None:
        self.server.run()

    def stop(self) -> None:
        self.server.should_exit = True


async def run_network_smoke_test(host: str = "127.0.0.1", port: int = 8765) -> Dict[str, Any]:
    """Execute live network WebSocket smoke test against running server."""
    base_http = f"http://{host}:{port}"
    base_ws = f"ws://{host}:{port}"

    # Wait for server readiness
    async with httpx.AsyncClient() as client:
        ready = False
        for _ in range(30):
            try:
                res = await client.get(f"{base_http}/health", timeout=1.0)
                if res.status_code == 200:
                    ready = True
                    break
            except Exception:
                await asyncio.sleep(0.1)
        if not ready:
            raise RuntimeError(f"Server at {base_http} failed to start.")

        print(f"[SMOKE TEST] Connected to DriftShield HTTP server at {base_http}")

        # 1. Create a simulation run via REST
        run_payload = {
            "scenario": "abrupt",
            "n_events": 1000,
            "warmup_size": 200,
            "label_budget": 300,
            "label_delay": 0,
            "seed": 42,
            "target_training_labels": 20,
            "evaluation_target_events": 50,
            "events_per_second": 200.0,
        }
        res = await client.post(f"{base_http}/api/runs", json=run_payload)
        assert res.status_code == 201, f"Failed to create run: {res.text}"
        run_data = res.json()
        run_id = run_data["run_id"]
        print(f"[SMOKE TEST] Created run '{run_id}' via POST /api/runs")

    # 2. Connect via real WebSocket with allowed origin header
    ws_url = f"{base_ws}/api/runs/{run_id}/live"
    print(f"[SMOKE TEST] Connecting to WebSocket: {ws_url} (Origin: http://localhost:3000)")

    received_snapshots: List[Dict[str, Any]] = []
    receive_timestamps: List[float] = []

    async with websockets.connect(
        ws_url,
        origin=websockets.Origin("http://localhost:3000"),
    ) as ws:
        # 3. Receive initial snapshot #1
        raw_msg1 = await ws.recv()
        t_recv1 = time.time()
        msg1 = json.loads(raw_msg1)
        validated1 = WebSocketSnapshotMessage(**msg1)
        received_snapshots.append(msg1)
        receive_timestamps.append(t_recv1)
        print(f"[SMOKE TEST] Received initial snapshot (seq={validated1.snapshot_sequence}, state={validated1.operational_state}, events={validated1.events_processed}/{validated1.total_events})")

        # 4. Start the run via REST control
        async with httpx.AsyncClient() as client:
            ctrl_res = await client.post(f"{base_http}/api/runs/{run_id}/control", json={"action": "start"})
            assert ctrl_res.status_code == 200, f"Failed to start run: {ctrl_res.text}"
            print(f"[SMOKE TEST] Started run execution via POST /api/runs/{run_id}/control")

        # 5. Stream subsequent live snapshots until terminal completion
        while True:
            try:
                raw_msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
                t_recv = time.time()
                msg = json.loads(raw_msg)
                validated = WebSocketSnapshotMessage(**msg)
                received_snapshots.append(msg)
                receive_timestamps.append(t_recv)

                print(
                    f"  -> Snapshot seq={validated.snapshot_sequence:02d} | "
                    f"state={validated.operational_state:9s} | "
                    f"cand_state={str(validated.candidate_state):12s} | "
                    f"events={validated.events_processed:4d}/{validated.total_events} ({validated.progress_percent:5.1f}%) | "
                    f"active_model={validated.active_model_version}"
                )

                if validated.operational_state in ("COMPLETED", "STOPPED", "INTERRUPTED"):
                    print(f"[SMOKE TEST] Terminal state '{validated.operational_state}' received over WebSocket.")
                    break
            except asyncio.TimeoutError:
                print("[SMOKE TEST] Timeout waiting for WebSocket message; checking REST status...")
                async with httpx.AsyncClient() as client:
                    detail = (await client.get(f"{base_http}/api/runs/{run_id}")).json()
                    if detail["operational_state"] in ("COMPLETED", "STOPPED", "INTERRUPTED"):
                        break

    # Compute interval statistics
    intervals_ms = [
        (receive_timestamps[i] - receive_timestamps[i - 1]) * 1000.0
        for i in range(1, len(receive_timestamps))
    ]

    mean_interval = statistics.mean(intervals_ms) if intervals_ms else 0.0
    stdev_interval = statistics.stdev(intervals_ms) if len(intervals_ms) > 1 else 0.0
    min_interval = min(intervals_ms) if intervals_ms else 0.0
    max_interval = max(intervals_ms) if intervals_ms else 0.0

    report = {
        "run_id": run_id,
        "total_snapshots": len(received_snapshots),
        "total_intervals": len(intervals_ms),
        "mean_interval_ms": round(mean_interval, 2),
        "stdev_interval_ms": round(stdev_interval, 2),
        "min_interval_ms": round(min_interval, 2),
        "max_interval_ms": round(max_interval, 2),
        "final_snapshot": received_snapshots[-1] if received_snapshots else None,
    }

    return report


def main() -> None:
    tmp_dir = Path("/tmp/driftshield_smoke_test")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_dir / "driftshield.db"
    art_dir = tmp_dir / "artifacts"
    if db_path.exists():
        db_path.unlink()

    storage = SQLiteStorage(db_path=db_path, artifacts_dir=art_dir)
    manager = RunManager(storage=storage, output_dir=tmp_dir)
    app = create_app(storage=storage, run_manager=manager, output_dir=tmp_dir)

    server = ServerThread(app=app, host="127.0.0.1", port=8765)
    server.start()
    print("[SMOKE TEST] Background Uvicorn server started on http://127.0.0.1:8765")

    try:
        report = asyncio.run(run_network_smoke_test(host="127.0.0.1", port=8765))
        print("\n=======================================================")
        print("           PHASE 5C SMOKE TEST MEASUREMENT REPORT      ")
        print("=======================================================")
        print(f"Run ID:                  {report['run_id']}")
        print(f"Total Snapshots:         {report['total_snapshots']}")
        print(f"Mean Update Interval:    {report['mean_interval_ms']} ms (Target ~500 ms)")
        print(f"Std Dev Update Interval: {report['stdev_interval_ms']} ms")
        print(f"Min / Max Interval:      {report['min_interval_ms']} ms / {report['max_interval_ms']} ms")
        final_snap = report["final_snapshot"]
        if final_snap:
            print(f"Final State:             {final_snap.get('operational_state')}")
            print(f"Final Model Version:     {final_snap.get('active_model_version')}")
            print(f"Events Processed:        {final_snap.get('events_processed')} / {final_snap.get('total_events')}")
            print(f"Metrics (full_synthetic):{final_snap.get('metrics', {}).get('full_synthetic')}")
            print(f"Metrics (monitoring):    {final_snap.get('metrics', {}).get('random_monitoring')}")
        print("=======================================================\n")
    finally:
        server.stop()
        print("[SMOKE TEST] Uvicorn server stopped cleanly.")


if __name__ == "__main__":
    main()
