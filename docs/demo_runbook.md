# DriftShield Demo Runbook

**ML Monitoring, Statistical Adaptation & Theory Lab Prototype**  
*Document Version: Phase 7B Production Verification*

---

## 1. System Architecture & Prerequisites

DriftShield is an end-to-end streaming ML monitoring and exact adaptation prototype. It contains:
- **FastAPI Backend**: Reusable event-by-event execution engine, SQLite persistent storage, REST control APIs, and real-time WebSocket state broadcasting.
- **React + TypeScript Frontend**: Vite single-page application with Live Dashboard, Run History, New Run configuration form, and Theory Lab interface.
- **Analytical Theory Lab**: Isolated workers for Theorem 4 (Rare-Region Disagreement Detection) and Theorem 5 (Finite-Domain Complete Audit).

### Prerequisites
- Python 3.9+ with virtualenv configured in `backend/.venv`
- Node.js 18+ and npm
- Chrome / Chromium for browser testing

---

## 2. Startup Commands

### Step 1: Start the Backend Server
From the repository root:
```bash
source backend/.venv/bin/activate
export PYTHONPATH=backend/src
uvicorn driftshield.api.app:app --host 127.0.0.1 --port 8000 --reload
```
- Health Check: `http://127.0.0.1:8000/api/health`
- REST Documentation: `http://127.0.0.1:8000/docs`

### Step 2: Start the Frontend Application
In a separate terminal:
```bash
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173
```
- Open Browser: `http://127.0.0.1:5173/`

---

## 3. Step-by-Step Demo Walkthrough

### Scenario A: Create & Execute an Abrupt Concept Drift Run
1. Click **New Run** in the top navigation bar.
2. Select **Abrupt Drift (Concept Shift)** in the Scenario dropdown.
3. Configure parameters:
   - Total Stream Events: `5000`
   - Warmup Events: `200`
   - Drift Start Sequence: `1000`
   - Post-Warmup Label Budget: `1000`
   - Label Delivery Delay: `0` (immediate)
   - RNG Seed: `42`
4. Click **Initialize & Open Dashboard**.
5. On the Live Run screen, click **Start Stream**.
6. Observe:
   - **Streaming Progress**: Events increment monotonically at configured pacing.
   - **Error Rate Chart**: Pre-drift error stays near 0%. Post-drift at event 1000 error rises.
   - **ADWIN Alert**: Alert card triggers upon statistical evidence of loss increase.
   - **Candidate Lifecycle**: State transitions `IDLE` $\to$ `TRAINING` $\to$ `READY_FOR_EVALUATION` $\to$ `EVALUATING` $\to$ `PROMOTED`.
   - **Post-Promotion Accuracy**: Active model version switches to `v2.0-promoted` and classification error drops back to baseline.

### Scenario B: Verify Lifecycle Controls (Pause / Resume / Stop)
1. In an active run, click **Pause**.
2. Verify stream freezes immediately; state updates to `PAUSED` on dashboard and WebSocket.
3. Click **Resume**; verify processing continues without event drops or prediction corruption.
4. Click **Stop**; confirm in modal; verify engine cleanly drains in-flight labels and transitions to `STOPPED`.

### Scenario C: Theory Lab — Theorem 4 Rare-Region Verification
1. Click **Theory Lab** in the navigation bar.
2. Under **Theorem 4 (Rare-Region Detection)**:
   - Subpopulation Mass $p$: `0.05`
   - Labeling Probability $q$: `0.20`
   - Observation Deadline $D$: `100`
   - Target Miss Probability $\delta$: `0.05`
   - Trials: `10,000`
3. Click **Run T4 Experiment**.
4. Observe:
   - Progress updates with live elapsed time.
   - Verified agreement between empirical success rate ($1 - \hat{\beta}$) and theoretical lower bound ($1 - (1-qp)^D$).

### Scenario D: Theory Lab — Theorem 5 Finite-Domain Audit
1. Click the **T5 Finite-Domain Exact Adaptation** tab.
2. Select Domain Size $N=32$, Scenario **Single-Last Change**.
3. Click **Run T5 Finite-Domain Audit**.
4. Observe:
   - Point queries executed sequentially $0 \dots N-1$.
   - Unqueried entries marked `Unresolved` until queried.
   - At query $N=32$, audit status becomes `100% Verified` with exact zero-risk guarantee.

---

## 4. Automated Headless Validation

To run all automated end-to-end tests:
```bash
# 1. Full Backend Test Suite (226 tests)
PYTHONPATH=backend/src backend/.venv/bin/pytest backend/tests

# 2. Frontend Production Build
npm --prefix frontend run build

# 3. Headless Browser E2E Suite
node frontend/test_phase7_browser.mjs
node frontend/test_theory_ui.mjs

# 4. Comprehensive Benchmark Suite
PYTHONPATH=backend/src backend/.venv/bin/python3 backend/scripts/run_benchmarks.py
```
