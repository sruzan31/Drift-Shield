"""driftshield.api.websocket
============================
WebSocket live update endpoint and connection manager for DriftShield Phase 5C.

Implements WS /api/runs/{run_id}/live with:
- Strict localhost browser origin validation (rejects disallowed with 4003).
- Run existence verification against SQLite storage (rejects unknown with 4004).
- Immediate current-state snapshot on connection.
- Periodic updates approximately every 500 ms for active runs.
- Bounded per-client queues with automatic snapshot coalescing (prevents slow clients from blocking engine or growing memory).
- Clean lifecycle and subscription teardown on disconnect.
- Safe thread-to-async loop bridging without concurrent model mutations.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional, Set
import time

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status

from ..run_manager import RunManager, RunNotFoundError
from .routes import get_run_manager
from .schemas import WebSocketSnapshotMessage

logger = logging.getLogger("driftshield.api.websocket")

ALLOWED_ORIGIN_PREFIXES = (
    "http://localhost",
    "http://127.0.0.1",
    "https://localhost",
    "https://127.0.0.1",
)


def is_allowed_origin(origin: Optional[str]) -> bool:
    """
    Validate that incoming WebSocket Origin header matches allowed localhost patterns.
    Non-browser clients without Origin header (e.g. CLI/tests) are permitted.
    """
    if origin is None:
        return True
    norm = origin.strip().lower()
    for prefix in ALLOWED_ORIGIN_PREFIXES:
        if norm == prefix or norm.startswith(prefix + ":"):
            return True
    return False


class WebSocketConnectionManager:
    """
    Manages active WebSocket subscriptions and periodic snapshot broadcasting.
    """

    def __init__(self, update_interval_seconds: float = 0.5) -> None:
        self.update_interval = update_interval_seconds
        self._subscribers: Dict[str, Set[asyncio.Queue[str]]] = {}
        self._broadcast_tasks: Dict[str, asyncio.Task] = {}
        self._sequence_counters: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def subscribe(
        self, run_id: str, queue: asyncio.Queue[str], manager: RunManager
    ) -> None:
        """Register a client queue and start broadcaster if needed."""
        async with self._lock:
            if run_id not in self._subscribers:
                self._subscribers[run_id] = set()
                self._sequence_counters[run_id] = 1
            self._subscribers[run_id].add(queue)

            if run_id not in self._broadcast_tasks or self._broadcast_tasks[run_id].done():
                task = asyncio.create_task(
                    self._broadcast_loop(run_id, manager),
                    name=f"ws-broadcaster-{run_id}",
                )
                self._broadcast_tasks[run_id] = task

    async def unsubscribe(self, run_id: str, queue: asyncio.Queue[str]) -> None:
        """Unregister a client queue and stop broadcaster if no subscribers remain."""
        async with self._lock:
            if run_id in self._subscribers:
                self._subscribers[run_id].discard(queue)
                if not self._subscribers[run_id]:
                    del self._subscribers[run_id]
                    if run_id in self._broadcast_tasks:
                        task = self._broadcast_tasks.pop(run_id)
                        if not task.done():
                            task.cancel()
                    self._sequence_counters.pop(run_id, None)

    async def _broadcast_loop(self, run_id: str, manager: RunManager) -> None:
        """Periodic broadcast loop publishing snapshots every ~500 ms."""
        try:
            while True:
                await asyncio.sleep(self.update_interval)

                async with self._lock:
                    subscribers = list(self._subscribers.get(run_id, []))
                    if not subscribers:
                        break
                    seq = self._sequence_counters.get(run_id, 1) + 1
                    self._sequence_counters[run_id] = seq

                try:
                    snap_dict = manager.get_live_snapshot(run_id, snapshot_sequence=seq)
                    msg_json = WebSocketSnapshotMessage(**snap_dict).model_dump_json()
                except RunNotFoundError:
                    logger.warning("Run '%s' no longer found during broadcast loop.", run_id)
                    break
                except Exception as e:
                    logger.exception("Error creating live snapshot for run '%s': %s", run_id, e)
                    break

                for q in subscribers:
                    # Bounded non-blocking queue put with coalescing:
                    # If queue is full (slow consumer), drop oldest unconsumed snapshot
                    if q.full():
                        try:
                            q.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    try:
                        q.put_nowait(msg_json)
                    except asyncio.QueueFull:
                        pass

                # If run is in a terminal state, broadcast final snapshot and exit loop
                if snap_dict["operational_state"] in ("COMPLETED", "STOPPED", "INTERRUPTED"):
                    break

        except asyncio.CancelledError:
            pass
        finally:
            async with self._lock:
                if run_id in self._broadcast_tasks and self._broadcast_tasks[run_id] is asyncio.current_task():
                    del self._broadcast_tasks[run_id]


# Global connection manager instance
ws_manager = WebSocketConnectionManager(update_interval_seconds=0.5)

ws_router = APIRouter()


@ws_router.websocket("/api/runs/{run_id}/live")
async def websocket_run_live(
    websocket: WebSocket,
    run_id: str,
    manager: RunManager = Depends(get_run_manager),
) -> None:
    """
    Live streaming WebSocket endpoint for run updates.

    Protocol:
    1. Origin header check: rejected with close code 4003 if disallowed.
    2. Run existence check: rejected with close code 4004 if not found.
    3. Accept connection and send snapshot 1 immediately.
    4. For completed/interrupted runs: connection remains available for query without starting workers.
    5. For active runs: stream live periodic snapshots every ~500 ms with bounded buffering.
    """
    origin = websocket.headers.get("origin")
    if origin is not None and not is_allowed_origin(origin):
        logger.warning(
            "WebSocket connection rejected: disallowed origin '%s' for run '%s'",
            origin,
            run_id,
        )
        await websocket.close(code=4003, reason="Disallowed browser origin")
        return

    # Validate run existence in storage
    run_rec = manager.storage.get_run(run_id)
    if run_rec is None:
        logger.warning("WebSocket connection rejected: run '%s' not found.", run_id)
        await websocket.close(code=4004, reason=f"Run '{run_id}' not found")
        return

    await websocket.accept()

    try:
        # 1. Send initial state snapshot immediately
        initial_snap = manager.get_live_snapshot(run_id, snapshot_sequence=1)
        initial_msg = WebSocketSnapshotMessage(**initial_snap).model_dump_json()
        await websocket.send_text(initial_msg)

        # If run is already completed/stopped/interrupted, maintain connection until client closes
        if initial_snap["operational_state"] in ("COMPLETED", "STOPPED", "INTERRUPTED"):
            try:
                while True:
                    # Wait for client to close or send ping/text
                    msg = await websocket.receive()
                    if msg.get("type") == "websocket.disconnect":
                        break
            except (WebSocketDisconnect, asyncio.CancelledError):
                pass
            return

        # 2. For active runs, subscribe with bounded per-client queue (maxsize=1)
        client_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
        await ws_manager.subscribe(run_id, client_queue, manager)

        async def _client_sender() -> None:
            while True:
                msg = await client_queue.get()
                await websocket.send_text(msg)

        async def _client_receiver() -> None:
            while True:
                data = await websocket.receive()
                if data.get("type") == "websocket.disconnect":
                    break

        sender_task = asyncio.create_task(_client_sender(), name=f"ws-send-{run_id}")
        receiver_task = asyncio.create_task(_client_receiver(), name=f"ws-recv-{run_id}")

        done, pending = await asyncio.wait(
            [sender_task, receiver_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()

    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as e:
        logger.exception("Error in WebSocket session for run '%s': %s", run_id, e)
    finally:
        if 'client_queue' in locals():
            await ws_manager.unsubscribe(run_id, client_queue)
