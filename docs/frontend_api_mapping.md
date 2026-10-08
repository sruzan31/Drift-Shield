# DriftShield Frontend API & Component Mapping

**Date**: October 7, 2026  
**Document Version**: 1.0  
**Status**: Comprehensive Endpoint & Feature Audit  

---

## 1. REST & WebSocket API Endpoint Mapping

| Frontend Feature | API Endpoint / Protocol | HTTP Method / Transport | Request Parameters / Payload | Response Fields Utilized | Target Component(s) | Integration Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **System Liveness & Storage Status** | `/health` / `/api/health` | `GET` | None | `status`, `storage_ready`, `active_run_id`, `timestamp` | `Header.tsx`, `App.tsx` | **Supported & Connected** |
| **List Simulation Runs** | `/api/runs` | `GET` | `page` (int), `page_size` (int) | `items` (RunSummary[]), `total`, `page`, `page_size`, `total_pages` | `Reports.tsx`, `RunHistory.tsx`, `Overview.tsx` | **Supported & Connected** |
| **Get Run Detail** | `/api/runs/{run_id}` | `GET` | Path `run_id` (string) | `run_id`, `scenario`, `state`, `operational_state`, `candidate_state`, `active_model_version`, `events_processed`, `total_events`, `progress_percent`, `monitoring_coverage`, `config`, `label_accounting`, `metrics`, `monitoring_summary`, `candidate_summary`, `paired_summary` | `Overview.tsx`, `LiveRun.tsx`, `Incidents.tsx`, `Insights.tsx`, `Actions.tsx`, `Reports.tsx` | **Supported & Connected** |
| **Create New Stream / Run** | `/api/runs` | `POST` | `CreateRunRequest` (`scenario`, `n_events`, `warmup_size`, `label_budget`, `label_delay`, `seed`, `drift_start_sequence`, `gradual_window`, `recurrence_interval`, `rare_region_p`, `adversary_dwell`, `adwin_delta`, `target_training_labels`, `evaluation_target_events`, `events_per_second`, `run_id`, `idempotency_key`) | `RunSummaryResponse` (`run_id`, `scenario`, `seed`, `mode`, `state`, `created_at`, `config`) | `NewRun.tsx` | **Supported & Connected** |
| **Lifecycle Controls** | `/api/runs/{run_id}/control` | `POST` | Path `run_id`, Body `ControlRequest` (`action`: 'start' \| 'pause' \| 'resume' \| 'stop', `events_per_second`) | `ControlResponse` (`run_id`, `action`, `previous_state`, `current_state`, `message`) | `Overview.tsx`, `LiveRun.tsx` | **Supported & Connected** |
| **List Incidents & Drift Alerts** | `/api/runs/{run_id}/incidents` | `GET` | Path `run_id`, Query `page`, `page_size` | `PaginatedIncidentsResponse` (`items`: `incident_id`, `alert_type`, `event_id`, `event_sequence`, `detection_delay`, `model_version`, `candidate_id`, `outcome`, `evidence`, `created_at`) | `Overview.tsx`, `Incidents.tsx`, `Reports.tsx` | **Supported & Connected** |
| **Get Event & Prediction Record** | `/api/runs/{run_id}/events/{event_id}` | `GET` | Path `run_id`, Path `event_id` | `EventPredictionResponse` (`run_id`, `event_id`, `sequence`, `features`, `processing_status`, `prediction`: `prediction_id`, `model_version`, `predicted_label`, `predicted_proba`, `latency_ms`) | `Incidents.tsx`, `LiveRun.tsx` | **Supported & Connected** |
| **Live Stream WebSocket Snapshot** | `/api/runs/{run_id}/live` | `WebSocket` | Subprotocol / WS handshake | `WebSocketSnapshotMessage` (`run_id`, `snapshot_sequence`, `operational_state`, `candidate_state`, `events_processed`, `total_events`, `progress_percent`, `active_model_version`, `monitoring_coverage`, `label_accounting`, `metrics`, `monitoring_summary`, `candidate_summary`, `paired_summary`, `synthetic_data`, `timestamp`) | `Overview.tsx`, `LiveRun.tsx` | **Supported & Connected** |
| **Create Theory Experiment** | `/api/theory/experiments` | `POST` | `CreateTheoryRequest` (`name`, `mode`: 'rare-region' \| 'finite-domain', `d_range`, `p_rare`, `q_monitor`, `n_eval_queries`, `n_trials`, `k_features`, `seed`) | `TheoryExperimentSummary` (`experiment_id`, `name`, `mode`, `status`, `created_at`) | `TheoryLab.tsx`, `RareRegionTab.tsx`, `FiniteDomainTab.tsx` | **Supported & Connected** |
| **List Theory Experiments** | `/api/theory/experiments` | `GET` | `limit` (int), `offset` (int) | `PaginatedTheoryExperimentsResponse` (`items`, `total`, `limit`, `offset`) | `TheoryLab.tsx` | **Supported & Connected** |
| **Get Theory Experiment Detail** | `/api/theory/experiments/{id}` | `GET` | Path `experiment_id` | `TheoryExperimentDetail` (`experiment_id`, `name`, `mode`, `status`, `config`, `records_count`, `created_at`, `completed_at`) | `TheoryLab.tsx` | **Supported & Connected** |
| **Get Theory Experiment Results** | `/api/theory/experiments/{id}/results` | `GET` | Path `experiment_id` | Full JSON results object (`summary`, `theoretical_curve`, `empirical_curve`, `records`) | `TheoryLab.tsx` | **Supported & Connected** |
| **Export Theory Experiment** | `/api/theory/experiments/{id}/export` | `GET` | Path `experiment_id`, Query `format` ('json' \| 'csv') | Downloadable JSON or CSV file stream | `TheoryLab.tsx` | **Supported & Connected** |

---

## 2. Missing Backend Endpoints & Contract Gaps

The following capabilities are visible in enterprise UI mock designs but lack backend endpoint contracts in the MVP specification. They are handled honestly with explicit unavailable notices without fabricated data:

1. **Individual Raw Event Streaming Channel (`WS /api/runs/{id}/events` or `/api/runs/{id}/feed`)**:
   - **Current State**: WebSocket `/api/runs/{id}/live` broadcasts aggregate snapshot state and metrics every 500ms, not individual raw feature dictionaries.
   - **Frontend Treatment**: `LiveRun.tsx` and `Overview.tsx` display real point-in-time snapshot events (`Snapshot #{seq}`, `Events: {events_processed}`, `State: {state}`). No fake temperatures or sine-wave vibrations are generated.
   - **Minimum Backend Requirement**: If per-event streaming is desired in the future, add an optional event buffer channel to the WebSocket broadcaster.

2. **Model Hyperplane Parameters (`GET /api/runs/{id}/model_boundary`)**:
   - **Current State**: Model version tags are stored, but internal classifier weight vectors ($w, b$) are not exposed via REST response schemas.
   - **Frontend Treatment**: `Overview.tsx` and `Incidents.tsx` display the active model version and explanation rather than plotting fake scatter points.
   - **Minimum Backend Requirement**: Add model weight introspection field (`weights`, `intercept`, `feature_names`) to `RunDetailResponse`.

3. **Multi-Dimensional Sensor Cohort Slicing (`GET /api/runs/{id}/cohorts`)**:
   - **Current State**: Classification metrics are aggregated per run and monitoring channel, not sliced into a 5x3 sensor feature grid.
   - **Frontend Treatment**: `Insights.tsx` renders stream-level metrics and displays an informative note that cohort breakdown requires feature-level slicing.
   - **Minimum Backend Requirement**: Add cohort breakdown aggregate endpoint.

4. **Multi-Tenant User Authentication & RBAC (`/api/auth/*`)**:
   - **Current State**: DriftShield runs as a local single-tenant application with local SQLite storage.
   - **Frontend Treatment**: Displays local workspace owner (`Sruzan Roy`, `Rudhran / Research`) without simulating login cookies or JWT bearer tokens.

---

## 3. Data Flow Architecture

```
                                  ┌───────────────────────────┐
                                  │      FastAPI Backend      │
                                  │  (Port 8000, SQLite Store)│
                                  └─────────────┬─────────────┘
                                                │
                     ┌──────────────────────────┴──────────────────────────┐
                     │                                                     │
            REST API Calls                                        WebSocket Stream
        (api.ts / Fetch Client)                             (websocket.ts / RunWebSocketClient)
                     │                                                     │
      ┌──────────────┼──────────────┐                      ┌───────────────┼───────────────┐
      │              │              │                      │                               │
  Health &       Run Engine     Incidents &           Snapshot State              Operational State
 Storage Ready    Lifecycle     Paired Tests            & Metrics                    Transitions
      │              │              │                      │                               │
      ▼              ▼              ▼                      ▼                               ▼
 [Header.tsx]  [NewRun.tsx]   [Incidents.tsx]        [LiveRun.tsx]                  [Overview.tsx]
 [App.tsx]     [Reports.tsx]  [Actions.tsx]          [Insights.tsx]                 [RunHistory.tsx]
```
