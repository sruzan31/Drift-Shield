"""driftshield.storage
===================
SQLite persistence layer and model artifact repository for DriftShield Phase 5A.

Design & Invariant Rules
------------------------
1. Schema & Relational Integrity:
   - Implements the 10-table schema from Master Specification Section 10.
   - Enforces PRAGMA foreign_keys = ON and transaction boundaries.
   - Preserves unique run and event keys with strict deduplication.

2. Durability & Failure Handling:
   - Single-writer SQLite architecture.
   - Immediate exception propagation on storage failure (never false 202 or false durable write).
   - Unfinished runs found during startup are marked 'INTERRUPTED'.

3. Artifact Management:
   - Stores serialized model and preprocessor artifacts under server-generated paths.
   - Computes and stores SHA-256 content hashes for tamper detection and audit.
   - Retains historical model artifacts across promotions.

4. Information Isolation:
   - Evaluator ground truth (hidden labels, drift onset) is isolated in the
     separate `evaluator_truth` table, inaccessible to operational prediction queries.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pickle
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from .contracts import DriftAlert, PredictionRecord, StreamEvent


SCHEMA_VERSION = "v1.0"

CREATE_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    parent_run_id TEXT,
    scenario TEXT NOT NULL,
    seed INTEGER NOT NULL,
    mode TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    state TEXT NOT NULL,
    config_json TEXT NOT NULL,
    environment_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    completed_at REAL,
    FOREIGN KEY (parent_run_id) REFERENCES runs(run_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS events (
    run_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    received_at REAL NOT NULL,
    features_json TEXT NOT NULL,
    is_synthetic INTEGER NOT NULL DEFAULT 1,
    processing_status TEXT NOT NULL,
    PRIMARY KEY (run_id, event_id),
    UNIQUE (run_id, sequence),
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS predictions (
    prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    model_version TEXT NOT NULL,
    predicted_label INTEGER NOT NULL,
    predicted_proba REAL NOT NULL,
    latency_ms REAL NOT NULL DEFAULT 0.0,
    created_at REAL NOT NULL,
    FOREIGN KEY (run_id, event_id) REFERENCES events(run_id, event_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS labels (
    label_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    true_label INTEGER NOT NULL,
    source TEXT NOT NULL,
    channel TEXT NOT NULL,
    delivery_sequence INTEGER NOT NULL,
    arrival_sequence INTEGER NOT NULL,
    validation_status TEXT NOT NULL DEFAULT 'VALID',
    created_at REAL NOT NULL,
    FOREIGN KEY (run_id, event_id) REFERENCES events(run_id, event_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS label_requests (
    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    cost REAL NOT NULL DEFAULT 1.0,
    budget_debit INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL,
    requested_sequence INTEGER NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (run_id, event_id) REFERENCES events(run_id, event_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    event_id TEXT NOT NULL,
    event_sequence INTEGER NOT NULL,
    arrival_sequence INTEGER NOT NULL,
    detection_delay INTEGER NOT NULL,
    model_version TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    candidate_id TEXT,
    outcome TEXT,
    created_at REAL NOT NULL,
    PRIMARY KEY (run_id, incident_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS model_versions (
    model_version_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    version_tag TEXT NOT NULL,
    parent_version_tag TEXT,
    activation_sequence INTEGER NOT NULL,
    model_artifact_path TEXT NOT NULL,
    preprocessor_artifact_path TEXT NOT NULL,
    model_artifact_hash TEXT NOT NULL,
    preprocessor_artifact_hash TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS metric_windows (
    window_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    start_sequence INTEGER NOT NULL,
    end_sequence INTEGER NOT NULL,
    window_type TEXT NOT NULL,
    method TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL,
    sample_count INTEGER NOT NULL,
    correct_count INTEGER NOT NULL DEFAULT 0,
    incorrect_count INTEGER NOT NULL DEFAULT 0,
    denominator INTEGER NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS benchmarks (
    benchmark_id TEXT PRIMARY KEY,
    run_id TEXT,
    scenario TEXT NOT NULL,
    seed INTEGER NOT NULL,
    config_json TEXT NOT NULL,
    artifact_locations_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluator_truth (
    eval_truth_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    hidden_label INTEGER NOT NULL,
    is_pre_drift INTEGER NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS theory_experiments (
    experiment_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    seed INTEGER NOT NULL,
    config_json TEXT NOT NULL,
    results_json TEXT,
    error_message TEXT,
    artifacts_dir TEXT NOT NULL,
    summary_artifact_path TEXT,
    data_artifact_path TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    completed_at REAL
);
"""


class SQLiteStorage:
    """
    Durable SQLite storage engine and artifact repository.

    Parameters
    ----------
    db_path : Path | str
        Filesystem path to the SQLite database file.
    artifacts_dir : Optional[Path | str]
        Directory where model and preprocessor binary artifacts are saved.
    """

    def __init__(
        self,
        db_path: Path | str = "driftshield.db",
        artifacts_dir: Optional[Path | str] = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.artifacts_dir = (
            Path(artifacts_dir) if artifacts_dir else self.db_path.parent / "artifacts"
        )
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir = self.artifacts_dir / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                self._conn = sqlite3.connect(
                    str(self.db_path),
                    timeout=30.0,
                    check_same_thread=False,
                )
                self._conn.row_factory = sqlite3.Row
                self._conn.execute("PRAGMA foreign_keys = ON;")
                self._conn.execute("PRAGMA journal_mode = WAL;")
            return self._conn

    def _init_db(self) -> None:
        """Initialize database schema, apply migrations, and mark unfinished runs INTERRUPTED."""
        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.executescript(CREATE_SCHEMA_SQL)
                # Automatic schema migration for existing databases
                cur = conn.execute("PRAGMA table_info(runs);")
                run_cols = {r["name"] for r in cur.fetchall()}
                if "parent_run_id" not in run_cols:
                    conn.execute("ALTER TABLE runs ADD COLUMN parent_run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL;")

                cur = conn.execute("PRAGMA table_info(label_requests);")
                lbl_req_cols = {r["name"] for r in cur.fetchall()}
                if "cost" not in lbl_req_cols:
                    conn.execute("ALTER TABLE label_requests ADD COLUMN cost REAL NOT NULL DEFAULT 1.0;")
                if "created_at" not in lbl_req_cols:
                    conn.execute(f"ALTER TABLE label_requests ADD COLUMN created_at REAL NOT NULL DEFAULT {time.time()};")

                cur = conn.execute("PRAGMA table_info(metric_windows);")
                mw_cols = {r["name"] for r in cur.fetchall()}
                if "correct_count" not in mw_cols:
                    conn.execute("ALTER TABLE metric_windows ADD COLUMN correct_count INTEGER NOT NULL DEFAULT 0;")
                if "incorrect_count" not in mw_cols:
                    conn.execute("ALTER TABLE metric_windows ADD COLUMN incorrect_count INTEGER NOT NULL DEFAULT 0;")

                cur = conn.execute("PRAGMA table_info(incidents);")
                inc_cols = {r["name"]: r["pk"] for r in cur.fetchall()}
                if inc_cols and inc_cols.get("run_id", 0) == 0:
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS incidents_new (
                            incident_id TEXT NOT NULL,
                            run_id TEXT NOT NULL,
                            alert_type TEXT NOT NULL,
                            event_id TEXT NOT NULL,
                            event_sequence INTEGER NOT NULL,
                            arrival_sequence INTEGER NOT NULL,
                            detection_delay INTEGER NOT NULL,
                            model_version TEXT NOT NULL,
                            evidence_json TEXT NOT NULL,
                            candidate_id TEXT,
                            outcome TEXT,
                            created_at REAL NOT NULL,
                            PRIMARY KEY (run_id, incident_id),
                            FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                        );
                    """)
                    conn.execute("INSERT OR IGNORE INTO incidents_new SELECT * FROM incidents;")
                    conn.execute("DROP TABLE incidents;")
                    conn.execute("ALTER TABLE incidents_new RENAME TO incidents;")

                # Record migration
                conn.execute(
                    "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?);",
                    (SCHEMA_VERSION, time.time()),
                )
                # Startup recovery: mark any unfinished runs as INTERRUPTED
                conn.execute(
                    """
                    UPDATE runs
                    SET state = 'INTERRUPTED', updated_at = ?
                    WHERE state IN ('INITIALIZING', 'WARMUP', 'RUNNING');
                    """,
                    (time.time(),),
                )

    def close(self) -> None:
        """Close active database connection."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # ------------------------------------------------------------------
    # Run Lifecycle
    # ------------------------------------------------------------------

    def create_run(
        self,
        run_id: str,
        scenario: str,
        seed: int,
        mode: str,
        config: Dict[str, Any],
        environment: Dict[str, Any],
        schema_version: str = "v1.0",
        parent_run_id: Optional[str] = None,
    ) -> None:
        """Create a new run record."""
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT INTO runs (
                        run_id, parent_run_id, scenario, seed, mode, schema_version, state,
                        config_json, environment_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'INITIALIZING', ?, ?, ?, ?);
                    """,
                    (
                        run_id,
                        parent_run_id,
                        scenario,
                        seed,
                        mode,
                        schema_version,
                        json.dumps(config),
                        json.dumps(environment),
                        now,
                        now,
                    ),
                )

    def update_run_state(
        self,
        run_id: str,
        state: str,
        completed: bool = False,
    ) -> None:
        """Update run execution state."""
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            with conn:
                if completed:
                    conn.execute(
                        """
                        UPDATE runs
                        SET state = ?, updated_at = ?, completed_at = ?
                        WHERE run_id = ?;
                        """,
                        (state, now, now, run_id),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE runs
                        SET state = ?, updated_at = ?
                        WHERE run_id = ?;
                        """,
                        (state, now, run_id),
                    )

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a run record by run_id."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute("SELECT * FROM runs WHERE run_id = ?;", (run_id,))
            row = cur.fetchone()
            if row is None:
                return None
            res = dict(row)
            res["config"] = json.loads(res["config_json"])
            res["environment"] = json.loads(res["environment_json"])
            return res

    def list_runs(self) -> List[Dict[str, Any]]:
        """List all runs ordered by creation time descending."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute("SELECT * FROM runs ORDER BY created_at DESC;")
            return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Model Version & Artifact Management
    # ------------------------------------------------------------------

    def save_model_version(
        self,
        run_id: str,
        version_tag: str,
        activation_sequence: int,
        model_obj: Any,
        preprocessor_obj: Any,
        parent_version_tag: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Serialize model and preprocessor to disk, compute SHA-256 hashes, and record model version.
        """
        model_bytes = pickle.dumps(model_obj)
        prep_bytes = pickle.dumps(preprocessor_obj)

        model_hash = hashlib.sha256(model_bytes).hexdigest()
        prep_hash = hashlib.sha256(prep_bytes).hexdigest()

        # Server-generated file paths
        model_filename = f"{run_id}_{version_tag}_model.pkl"
        prep_filename = f"{run_id}_{version_tag}_preprocessor.pkl"

        model_path = self.models_dir / model_filename
        prep_path = self.models_dir / prep_filename

        with open(model_path, "wb") as f:
            f.write(model_bytes)
        with open(prep_path, "wb") as f:
            f.write(prep_bytes)

        model_version_id = f"mv-{run_id}-{version_tag}"
        now = time.time()

        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT INTO model_versions (
                        model_version_id, run_id, version_tag, parent_version_tag,
                        activation_sequence, model_artifact_path, preprocessor_artifact_path,
                        model_artifact_hash, preprocessor_artifact_hash, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        model_version_id,
                        run_id,
                        version_tag,
                        parent_version_tag,
                        activation_sequence,
                        str(model_path),
                        str(prep_path),
                        model_hash,
                        prep_hash,
                        json.dumps(metadata or {}),
                        now,
                    ),
                )
        return model_version_id

    def get_model_versions(self, run_id: str) -> List[Dict[str, Any]]:
        """Retrieve all model versions recorded for a run."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute(
                "SELECT * FROM model_versions WHERE run_id = ? ORDER BY activation_sequence ASC;",
                (run_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Events & Predictions
    # ------------------------------------------------------------------

    def record_event(
        self,
        run_id: str,
        event: StreamEvent,
        processing_status: str = "ACCEPTED",
    ) -> bool:
        """
        Record a stream event.

        Returns True if inserted, False if duplicate identical event.
        Raises ValueError if conflicting duplicate.
        """
        features_json = json.dumps(event.features, sort_keys=True)
        now = time.time()

        with self._lock:
            conn = self._get_connection()
            # Check existing
            cur = conn.execute(
                "SELECT sequence, features_json FROM events WHERE run_id = ? AND event_id = ?;",
                (run_id, event.event_id),
            )
            existing = cur.fetchone()
            if existing is not None:
                if existing["sequence"] != event.sequence or existing["features_json"] != features_json:
                    raise ValueError(
                        f"Conflicting duplicate event '{event.event_id}' for run '{run_id}'."
                    )
                return False  # Identical duplicate: ignore

            with conn:
                conn.execute(
                    """
                    INSERT INTO events (
                        run_id, event_id, sequence, timestamp, received_at,
                        features_json, is_synthetic, processing_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        run_id,
                        event.event_id,
                        event.sequence,
                        event.timestamp,
                        now,
                        features_json,
                        int(event.is_synthetic),
                        processing_status,
                    ),
                )
            return True

    def record_prediction(
        self,
        run_id: str,
        pred: PredictionRecord,
        latency_ms: float = 0.0,
    ) -> None:
        """Record locked-in prediction."""
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT INTO predictions (
                        run_id, event_id, sequence, model_version,
                        predicted_label, predicted_proba, latency_ms, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        run_id,
                        pred.event_id,
                        pred.sequence,
                        getattr(pred, "model_version", "v1.0-frozen"),
                        pred.predicted_label,
                        pred.predicted_proba,
                        latency_ms,
                        now,
                    ),
                )

    # ------------------------------------------------------------------
    # Labels & Label Requests
    # ------------------------------------------------------------------

    def record_label_request(
        self,
        run_id: str,
        event_id: str,
        channel: str,
        requested_sequence: int,
        status: str = "ACQUIRED",
        cost: float = 1.0,
        budget_debit: int = 1,
    ) -> None:
        """Record label acquisition request and budget debit."""
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT INTO label_requests (
                        run_id, event_id, channel, cost, budget_debit, status, requested_sequence, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (run_id, event_id, channel, cost, budget_debit, status, requested_sequence, now),
                )

    def record_label(
        self,
        run_id: str,
        event_id: str,
        true_label: int,
        source: str,
        channel: str,
        delivery_sequence: int,
        arrival_sequence: int,
        validation_status: str = "VALID",
    ) -> bool:
        """
        Record delivered authorized label.

        Returns True if inserted, False if duplicate identical.
        Raises ValueError if conflicting label value.
        """
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute(
                "SELECT true_label FROM labels WHERE run_id = ? AND event_id = ?;",
                (run_id, event_id),
            )
            existing = cur.fetchone()
            if existing is not None:
                if existing["true_label"] != true_label:
                    raise ValueError(
                        f"Conflicting duplicate label for event '{event_id}' in run '{run_id}'."
                    )
                return False  # Duplicate identical label

            now = time.time()
            with conn:
                conn.execute(
                    """
                    INSERT INTO labels (
                        run_id, event_id, true_label, source, channel,
                        delivery_sequence, arrival_sequence, validation_status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        run_id,
                        event_id,
                        true_label,
                        source,
                        channel,
                        delivery_sequence,
                        arrival_sequence,
                        validation_status,
                        now,
                    ),
                )
            return True

    # ------------------------------------------------------------------
    # Incidents, Metrics & Evaluator Truth
    # ------------------------------------------------------------------

    def record_incident(
        self,
        run_id: str,
        alert: DriftAlert,
        candidate_id: Optional[str] = None,
        outcome: Optional[str] = None,
    ) -> None:
        """Record an error-change alert incident."""
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT INTO incidents (
                        incident_id, run_id, alert_type, event_id, event_sequence,
                        arrival_sequence, detection_delay, model_version, evidence_json,
                        candidate_id, outcome, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        alert.alert_id,
                        run_id,
                        alert.description,
                        alert.event_id,
                        alert.event_sequence,
                        alert.arrival_sequence,
                        alert.detection_delay_from_event,
                        alert.model_version,
                        json.dumps(alert.to_dict()),
                        candidate_id,
                        outcome,
                        now,
                    ),
                )

    def update_incident_outcome(
        self,
        run_id: str,
        incident_id: str,
        outcome: str,
        candidate_id: Optional[str] = None,
        extra_evidence: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update an incident's final outcome and evidence."""
        with self._lock:
            conn = self._get_connection()
            with conn:
                cur = conn.execute(
                    "SELECT evidence_json, candidate_id FROM incidents WHERE run_id = ? AND incident_id = ?;",
                    (run_id, incident_id),
                )
                row = cur.fetchone()
                if row is not None:
                    curr_ev = json.loads(row["evidence_json"]) if row["evidence_json"] else {}
                    if extra_evidence:
                        curr_ev.update(extra_evidence)
                    cid = candidate_id or row["candidate_id"]
                    conn.execute(
                        """
                        UPDATE incidents
                        SET outcome = ?, candidate_id = ?, evidence_json = ?
                        WHERE run_id = ? AND incident_id = ?;
                        """,
                        (outcome, cid, json.dumps(curr_ev, sort_keys=True), run_id, incident_id),
                    )

    def record_metric_window(
        self,
        run_id: str,
        start_sequence: int,
        end_sequence: int,
        window_type: str,
        method: str,
        metric_name: str,
        metric_value: Optional[float],
        sample_count: int,
        denominator: int,
        correct_count: int = 0,
        incorrect_count: int = 0,
    ) -> None:
        """Record a calculated evaluation or monitoring metric window."""
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT INTO metric_windows (
                        run_id, start_sequence, end_sequence, window_type,
                        method, metric_name, metric_value, sample_count,
                        correct_count, incorrect_count, denominator, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        run_id,
                        start_sequence,
                        end_sequence,
                        window_type,
                        method,
                        metric_name,
                        metric_value,
                        sample_count,
                        correct_count,
                        incorrect_count,
                        denominator,
                        now,
                    ),
                )

    def record_evaluator_truth(
        self,
        run_id: str,
        event_id: str,
        hidden_label: int,
        is_pre_drift: bool = True,
    ) -> None:
        """Record hidden ground truth into isolated evaluator table."""
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT INTO evaluator_truth (
                        run_id, event_id, hidden_label, is_pre_drift, created_at
                    ) VALUES (?, ?, ?, ?, ?);
                    """,
                    (run_id, event_id, hidden_label, int(is_pre_drift), now),
                )

    # ------------------------------------------------------------------
    # Query APIs
    # ------------------------------------------------------------------

    def get_paginated_runs(self, limit: int = 20, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        """Retrieve paginated runs and total count."""
        with self._lock:
            conn = self._get_connection()
            cur_cnt = conn.execute("SELECT COUNT(*) FROM runs;")
            total = cur_cnt.fetchone()[0]

            cur = conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                (limit, offset),
            )
            runs = []
            for r in cur.fetchall():
                rd = dict(r)
                rd["config"] = json.loads(rd["config_json"]) if rd.get("config_json") else {}
                rd["environment"] = json.loads(rd["environment_json"]) if rd.get("environment_json") else {}
                runs.append(rd)
            return runs, total

    def get_paginated_incidents(
        self, run_id: str, limit: int = 20, offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Retrieve paginated incidents and total count for a run."""
        with self._lock:
            conn = self._get_connection()
            cur_cnt = conn.execute("SELECT COUNT(*) FROM incidents WHERE run_id = ?;", (run_id,))
            total = cur_cnt.fetchone()[0]

            cur = conn.execute(
                "SELECT * FROM incidents WHERE run_id = ? ORDER BY arrival_sequence ASC LIMIT ? OFFSET ?;",
                (run_id, limit, offset),
            )
            incidents = []
            for r in cur.fetchall():
                rd = dict(r)
                rd["evidence"] = json.loads(rd["evidence_json"]) if rd.get("evidence_json") else {}
                incidents.append(rd)
            return incidents, total

    def get_event_with_prediction(self, run_id: str, event_id: str) -> Optional[Dict[str, Any]]:
        """Query single event with its original recorded prediction."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute(
                """
                SELECT e.run_id, e.event_id, e.sequence, e.timestamp, e.received_at,
                       e.features_json, e.is_synthetic, e.processing_status,
                       p.prediction_id, p.model_version, p.predicted_label,
                       p.predicted_proba, p.latency_ms, p.created_at AS prediction_created_at
                FROM events e
                LEFT JOIN predictions p ON e.run_id = p.run_id AND e.event_id = p.event_id
                WHERE e.run_id = ? AND e.event_id = ?;
                """,
                (run_id, event_id),
            )
            row = cur.fetchone()
            if row is None:
                return None
            res = dict(row)
            res["features"] = json.loads(res["features_json"]) if res.get("features_json") else {}
            return res

    def get_label_accounting(self, run_id: str) -> Dict[str, Any]:
        """Aggregate label acquisition and budget accounting from storage."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN source = 'warmup' THEN 1 ELSE 0 END) AS warmup_count,
                    SUM(CASE WHEN source = 'monitor' THEN 1 ELSE 0 END) AS monitor_count,
                    SUM(CASE WHEN source = 'selective' THEN 1 ELSE 0 END) AS selective_count,
                    COUNT(DISTINCT event_id) AS total_unique_labels
                FROM labels
                WHERE run_id = ?;
                """,
                (run_id,),
            )
            row = cur.fetchone()
            warmup = row["warmup_count"] or 0
            monitor = row["monitor_count"] or 0
            selective = row["selective_count"] or 0
            total_unique = row["total_unique_labels"] or 0
            post_warmup_unique = max(0, total_unique - warmup)

            cur2 = conn.execute(
                "SELECT SUM(budget_debit) AS total_debits FROM label_requests WHERE run_id = ? AND channel != 'warmup';",
                (run_id,),
            )
            debits = cur2.fetchone()["total_debits"] or 0

            return {
                "warmup_acquisitions": warmup,
                "monitor_acquisitions": monitor,
                "selective_acquisitions": selective,
                "post_warmup_acquisitions": post_warmup_unique,
                "total_unique_acquisitions": total_unique,
                "budget_debits": debits,
            }

    def get_events(self, run_id: str) -> List[Dict[str, Any]]:
        """Query all events for a run in sequence order."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute(
                "SELECT * FROM events WHERE run_id = ? ORDER BY sequence ASC;",
                (run_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def get_predictions(self, run_id: str) -> List[Dict[str, Any]]:
        """Query all predictions for a run in sequence order."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute(
                "SELECT * FROM predictions WHERE run_id = ? ORDER BY sequence ASC;",
                (run_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def get_labels(self, run_id: str) -> List[Dict[str, Any]]:
        """Query all delivered labels for a run in arrival sequence order."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute(
                "SELECT * FROM labels WHERE run_id = ? ORDER BY arrival_sequence ASC;",
                (run_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def get_incidents(self, run_id: str) -> List[Dict[str, Any]]:
        """Query all incidents recorded for a run."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute(
                "SELECT * FROM incidents WHERE run_id = ? ORDER BY arrival_sequence ASC;",
                (run_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def get_metric_windows(self, run_id: str) -> List[Dict[str, Any]]:
        """Query all metric windows recorded for a run."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute(
                "SELECT * FROM metric_windows WHERE run_id = ? ORDER BY window_id ASC;",
                (run_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def get_evaluator_truth(self, run_id: str) -> List[Dict[str, Any]]:
        """Query evaluator hidden truth records."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute(
                "SELECT * FROM evaluator_truth WHERE run_id = ? ORDER BY eval_truth_id ASC;",
                (run_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    # -----------------------------------------------------------------------
    # Theory Lab Experiment Persistence (Phase 6B)
    # -----------------------------------------------------------------------

    def create_theory_experiment(
        self,
        experiment_id: str,
        mode: str,
        seed: int,
        config_dict: Dict[str, Any],
        artifacts_dir: str,
    ) -> Dict[str, Any]:
        """Create a new theory experiment record in QUEUED state."""
        now = time.time()
        config_json = json.dumps(config_dict)
        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT INTO theory_experiments (
                        experiment_id, mode, status, seed, config_json,
                        artifacts_dir, created_at, updated_at
                    ) VALUES (?, ?, 'QUEUED', ?, ?, ?, ?, ?);
                    """,
                    (experiment_id, mode, seed, config_json, artifacts_dir, now, now),
                )
        return {
            "experiment_id": experiment_id,
            "mode": mode,
            "status": "QUEUED",
            "seed": seed,
            "config": config_dict,
            "artifacts_dir": artifacts_dir,
            "created_at": now,
            "updated_at": now,
        }

    def get_theory_experiment(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a theory experiment by its ID."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.execute(
                "SELECT * FROM theory_experiments WHERE experiment_id = ?;",
                (experiment_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            res = dict(row)
            try:
                res["config"] = json.loads(res["config_json"]) if res.get("config_json") else {}
            except Exception:
                res["config"] = {}
            try:
                res["results"] = json.loads(res["results_json"]) if res.get("results_json") else None
            except Exception:
                res["results"] = None
            return res

    def list_theory_experiments(
        self, limit: int = 50, offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List theory experiments with pagination, sorted newest first."""
        with self._lock:
            conn = self._get_connection()
            cur_count = conn.execute("SELECT COUNT(*) AS total FROM theory_experiments;")
            total = cur_count.fetchone()["total"]

            cur = conn.execute(
                """
                SELECT * FROM theory_experiments
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?;
                """,
                (limit, offset),
            )
            rows = []
            for r in cur.fetchall():
                item = dict(r)
                try:
                    item["config"] = json.loads(item["config_json"]) if item.get("config_json") else {}
                except Exception:
                    item["config"] = {}
                try:
                    item["results"] = json.loads(item["results_json"]) if item.get("results_json") else None
                except Exception:
                    item["results"] = None
                rows.append(item)
            return rows, total

    def update_theory_experiment_status(
        self,
        experiment_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Update operational status of a theory experiment."""
        now = time.time()
        completed_at = now if status in ("COMPLETED", "FAILED", "INTERRUPTED") else None
        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    UPDATE theory_experiments
                    SET status = ?, error_message = ?, updated_at = ?, completed_at = COALESCE(completed_at, ?)
                    WHERE experiment_id = ?;
                    """,
                    (status, error_message, now, completed_at, experiment_id),
                )

    def save_theory_experiment_results(
        self,
        experiment_id: str,
        results_dict: Dict[str, Any],
        summary_artifact_path: Optional[str] = None,
        data_artifact_path: Optional[str] = None,
    ) -> None:
        """Save results payload and artifact paths for a completed theory experiment."""
        now = time.time()
        results_json = json.dumps(results_dict)
        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    UPDATE theory_experiments
                    SET status = 'COMPLETED',
                        results_json = ?,
                        summary_artifact_path = ?,
                        data_artifact_path = ?,
                        updated_at = ?,
                        completed_at = ?
                    WHERE experiment_id = ?;
                    """,
                    (
                        results_json,
                        summary_artifact_path,
                        data_artifact_path,
                        now,
                        now,
                        experiment_id,
                    ),
                )

    def startup_recovery_theory(self) -> int:
        """
        Mark any experiments left in QUEUED or RUNNING states as INTERRUPTED on startup.
        Returns the number of interrupted experiments.
        """
        now = time.time()
        with self._lock:
            conn = self._get_connection()
            with conn:
                cur = conn.execute(
                    """
                    UPDATE theory_experiments
                    SET status = 'INTERRUPTED',
                        error_message = 'Interrupted due to server process shutdown',
                        updated_at = ?,
                        completed_at = ?
                    WHERE status IN ('QUEUED', 'RUNNING');
                    """,
                    (now, now),
                )
                interrupted_count = cur.rowcount
            return interrupted_count

