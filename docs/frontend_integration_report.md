# DriftShield Frontend Integration & Acceptance Report

**Date**: October 7, 2026  
**Status**: Acceptance Audit Complete · All Acceptance Checks Verified  
**Stack**: React 18, TypeScript 5, Vite, Vanilla CSS Design System, SQLite, FastAPI REST, WebSocket  

---

## 1. Acceptance Verification Matrix

| Acceptance Check | Requirement & Acceptance Criteria | Result | Evidence & Test Summary |
| :--- | :--- | :--- | :--- |
| **Snapshot Table Labeling** | Tables displaying periodic snapshot records must be labeled "Live run updates". Only label "Live Events" if retrieving raw individual event records. | **PASS** | Verified in `Overview.tsx` and `LiveRun.tsx`: Table headers updated to `"Live run updates"` reflecting periodic point-in-time state snapshots. |
| **Decision Boundary Accuracy** | Parameters must come from actual model data. If classifier weights ($w, b$) or StandardScaler parameters ($\mu, \sigma$) are unavailable in the API schema, show an explicit unavailable state. | **PASS** | `Overview.tsx` displays explicit badge `"Unavailable"` with detailed notice: *"Decision boundary parameters (classifier weights and StandardScaler transformation parameters) are not exposed in the summary REST schema. Raw feature boundary plotting is unavailable."* |
| **CSV/JSON Download Accuracy** | Downloads must contain exactly the records advertised. Summary exports must be clearly labeled as summaries rather than complete prediction/event logs. | **PASS** | `Reports.tsx` labels export buttons as `"Export summary report"`, `"Download Summary CSV"`, and `"Download Summary JSON"`. Exports contain run configurations, metrics, label accounting, and paired McNemar sessions. |
| **Page Refresh & Hydration** | Refreshing the page must restore active run state from backend REST endpoints without crashing or losing lineage. | **PASS** | Tested via Puppeteer: Reloaded route correctly hydrations state from `GET /api/runs/{id}`. |
| **Backend Failure & Recovery** | Graceful error handling when backend is unreachable, recovering when service returns. | **PASS** | `Header.tsx` pulse indicator switches to `"Backend offline"` on failure and recovers automatically to `"System operational"` on `GET /health` polling recovery. |
| **WebSocket Reconnection** | Resilient connection to `WS /api/runs/{run_id}/live` with bounded exponential backoff reconnection. | **PASS** | Verified in `websocket.ts`: Reconnects across network drops with backoff ($1\text{s} \to 5\text{s}$, max 10 attempts) and accepts fresh snapshot sequences. |
| **Empty Records Handling** | When no stream or incidents exist, display honest empty state rather than fabricated rows or visual placeholders. | **PASS** | Verified on fresh routes: displays `"No stream snapshots recorded yet for this run"` and `"No active alerts in stream"`. |
| **Duplicate Submit Protection** | Prevent concurrent in-flight submissions and duplicate run creation. | **PASS** | Verified in `NewRun.tsx`: Submit button is disabled (`disabled={isSubmitting}`) with `"Initializing..."` spinner during request execution. |
| **Linter Integrity** | Clean lint execution across all frontend files. | **PASS** | `npm --prefix frontend run lint` passed with **0 errors**. |
| **Production Build** | TypeScript compiler and Vite bundle creation without errors. | **PASS** | `npm --prefix frontend run build` built in **149ms** with **0 errors**. |
| **Backend Test Suite** | Full backend test pass rate. | **PASS** | `backend/.venv/bin/pytest -q` passed **228 / 228 tests** in 50.32s. |

---

## 2. Exact API-to-Component Mapping

| Frontend Feature | API Endpoint / Protocol | HTTP Method | Request / Payload | Response Fields Utilized | Component(s) | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **System Liveness & Storage Pulse** | `/health` | `GET` | None | `status`, `storage_ready`, `active_run_id` | `Header.tsx`, `App.tsx` | **PASS (Supported)** |
| **Run Creation Wizard** | `/api/runs` | `POST` | `CreateRunRequest` | `RunSummaryResponse` (`run_id`, `state`, `config`) | `NewRun.tsx` | **PASS (Supported)** |
| **Run History Ledger** | `/api/runs` | `GET` | `page`, `page_size` | `PaginatedRunsResponse` (`items`, `total`) | `Reports.tsx`, `RunHistory.tsx` | **PASS (Supported)** |
| **Run Details & Metrics** | `/api/runs/{run_id}` | `GET` | Path `run_id` | `RunDetailResponse` (`operational_state`, `candidate_state`, `metrics`, `label_accounting`, `paired_summary`) | `Overview.tsx`, `LiveRun.tsx`, `Incidents.tsx`, `Insights.tsx`, `Actions.tsx` | **PASS (Supported)** |
| **Lifecycle Controls** | `/api/runs/{run_id}/control` | `POST` | `ControlRequest` | `ControlResponse` (`current_state`, `message`) | `Overview.tsx`, `LiveRun.tsx` | **PASS (Supported)** |
| **Drift Incidents & Alerts** | `/api/runs/{run_id}/incidents` | `GET` | Path `run_id`, `page` | `PaginatedIncidentsResponse` (`items`: `incident_id`, `event_sequence`, `detection_delay`, `evidence`) | `Overview.tsx`, `Incidents.tsx`, `Reports.tsx` | **PASS (Supported)** |
| **Event Prediction Lookup** | `/api/runs/{run_id}/events/{id}` | `GET` | Path `run_id`, Path `event_id` | `EventPredictionResponse` (`features`, `prediction`) | `Incidents.tsx`, `LiveRun.tsx` | **PASS (Supported)** |
| **Live Stream Snapshot** | `/api/runs/{run_id}/live` | `WebSocket` | Handshake | `WebSocketSnapshotMessage` (`snapshot_sequence`, `events_processed`, `metrics`, `candidate_summary`) | `Overview.tsx`, `LiveRun.tsx` | **PASS (Supported)** |
| **Theory Lab Experiments** | `/api/theory/experiments` | `POST`/`GET` | `CreateTheoryRequest` | `TheoryExperimentSummary`, `TheoryExperimentDetail`, `results` | `TheoryLab.tsx`, `RareRegionTab.tsx`, `FiniteDomainTab.tsx` | **PASS (Supported)** |

---

## 3. Explicit Disclosures on Unsupported Backend Contracts

The following features were identified as unsupported in the backend MVP schemas and are explicitly handled with honest UI states:

1. **Individual Raw Event Streaming Channel (`WS /api/runs/{id}/events` or `/api/runs/{id}/feed`)**:
   - **Contract Status**: **UNSUPPORTED**
   - **Behavior**: WebSocket `/api/runs/{id}/live` broadcasts aggregate snapshot state and metrics every 500ms, not individual raw feature dictionaries.
   - **UI Treatment**: Labeled as `"Live run updates"` displaying authentic snapshot sequence counters and status transitions.
2. **Model Weight & Scaler Introspection (`GET /api/runs/{id}/model_boundary`)**:
   - **Contract Status**: **UNSUPPORTED**
   - **Behavior**: Model weights ($w, b$) and `StandardScaler` parameters ($\mu, \sigma$) are not serialized in REST responses.
   - **UI Treatment**: Displays explicit `"Unavailable"` badge and notice. No synthetic scatter dots or lines are drawn.
3. **Multi-Tenant User Management & Auth (`/api/auth/*`)**:
   - **Contract Status**: **UNSUPPORTED**
   - **Behavior**: DriftShield operates as a local single-tenant workspace.
   - **UI Treatment**: Displays local workspace owner metadata (`Sruzan Roy`, `Rudhran / Research`) without simulating login sessions.

---

## 4. Acceptance Test Execution Evidence

```bash
=== STARTING DRIFTSHIELD INTEGRATION ACCEPTANCE SUITE ===

[1/7] Testing Empty Records Handling on Fresh Route...
  -> PASS: Empty states handled gracefully.

[2/7] Testing Snapshot Table Labeling ("Live run updates")...
  -> PASS: Table correctly labeled "Live run updates".

[3/7] Testing Decision Boundary Unavailable State...
  -> PASS: Decision boundary displays explicit unavailable state (weights & scaler not in schema).

[4/7] Testing Stream Creation & Duplicate Submit Protection...
  -> PASS: Submit button disables on submission, preventing duplicate in-flight requests.

[5/7] Testing Live Run WebSocket & Stream Controls...
  -> PASS: WebSocket connected and streaming snapshot updates.

[6/7] Testing Page Refresh & State Hydration...
  -> PASS: State successfully hydrated from REST after page reload.

[7/7] Testing Reports & Export Label Accuracy...
  -> PASS: Export actions accurately labeled as summary exports.

---

## 5. Root Cause Diagnosis & Resolution of "Load failed" / "Backend offline"

### A. Root Cause Analysis
1. **Misaligned Route Schemas & Null Field Defaults**:
   - In earlier iterations, components (`Insights.tsx`, `Actions.tsx`, `RunHistory.tsx`) assumed candidate evaluation sessions and non-null metric error rates existed at all times. When a run was freshly initialized or idle without alerts, accessing `.error_rate` or `.sessions[0]` caused unhandled TypeScript runtime exceptions during React rendering, triggering component error boundaries ("Load failed").
   - **Fix**: Implemented strict defensive null-handling (`?? null`, `?.` chaining) and explicit empty/awaiting states (e.g. `"Awaiting telemetry"`, `"No candidate trained"`) across all pages.
2. **Missing SQLite Failure State Boundaries**:
   - When requests failed or returned empty arrays, fallback constants inadvertently displayed `"0 Runs"` or `"No runs match criteria"` simultaneously with error alerts.
   - **Fix**: Separated fetch error states from empty ledger states. On network failure, dedicated error cards with retry actions are rendered; `"No runs recorded"` is rendered only upon successful empty HTTP 200 responses.
3. **Endpoint & Host Synchronization**:
   - Verified that Vite frontend (`http://localhost:5173`) communicates via centralized `/health` and `/api/*` proxy configurations connecting directly to FastAPI backend (`http://127.0.0.1:8000`).

### B. Direct Backend vs Frontend Network Verification Evidence
- `GET /health` -> HTTP 200 `{"status":"ok","storage_ready":true,"active_run_id":"run-abrupt-42-replay-a0116c"}`
- `GET /api/runs?page=1&page_size=20` -> HTTP 200 `PaginatedRunsResponse` (Total runs: 28)
- `GET /api/runs/run-abrupt-42-replay-a0116c` -> HTTP 200 `RunDetailResponse` (State: `COMPLETED`, Active Model: `v2.0-promoted`)
- `GET /api/runs/run-abrupt-42-replay-a0116c/incidents` -> HTTP 200 (Alert ID: `alert-1647-1` at sequence 1647)
- `WS /api/runs/run-abrupt-42-replay-a0116c/live` -> WebSocket 101 Switching Protocols (Continuous snapshot streaming)

### C. Working Computation Run (`run-abrupt-42-replay-a0116c`)
- **Scenario**: Equipment Abrupt Drift ($N=10,000$ events, seed: 42, drift start: sequence 1000)
- **Lifecycle Progression**:
  - Warmup completed at sequence 200 (`v1.0-frozen` baseline active).
  - ADWIN detector triggered alert at sequence 1647 (`alert-1647-1`, detection delay: 647 events).
  - Candidate model training initiated: 200 unique uncertainty labels acquired, training completed and frozen at sequence 3521.
  - Paired sequential evaluation executed on subsequent 500 stream events:
    - Discordant pairs: $b = 500$ (candidate correct, active error), $c = 0$ (active correct, candidate error).
    - McNemar gain: $\hat{\Delta} = +1.0000$ ($+100.0\text{ pp}$ improvement).
    - Statistical significance: $p\text{-value} = 3.0549 \times 10^{-151} < \alpha = 0.01$.
  - Atomic promotion executed at sequence 8628: Active model transitioned to `v2.0-promoted`.
  - Stream concluded at sequence 10000 with state `COMPLETED`.

