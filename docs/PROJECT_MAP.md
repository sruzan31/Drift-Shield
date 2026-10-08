# Project Map

## A. Project setup and configuration
- **README.md** – Overview, quick start, and high‑level architecture.
- **pyproject.toml** – Python package configuration, dependencies, and build settings.
- **package.json** & **vite.config.ts** – Frontend tooling configuration (Vite, React plugin, proxy settings).
- **.gitignore**, **.pytest_cache**, **.venv** – Version‑control and environment files.
- **Frontend URL**: http://localhost:5173
- **Backend startup**: `PYTHONPATH=backend/src backend/.venv/bin/python -m uvicorn driftshield.api.app:app --host 127.0.0.1 --port 8000`


## B. Frontend entry point and navigation
- **frontend/src/main.tsx** – React entry point, mounts `<App />`.
- **frontend/src/App.tsx** – Root component, sets up routing and layout.
- **frontend/src/pages/** – Top‑level application pages (e.g., Dashboard, Settings).

## C. Pages and reusable components
- **frontend/src/pages/** – Contains page‑level components such as `HomePage.tsx`, `RunPage.tsx`.
- **frontend/src/components/** – Reusable UI pieces (e.g., `ControlBar.tsx`, `IncidentsTable.tsx`).

## D. API client and WebSocket connection
- **frontend/src/lib/** – Wrapper around `fetch`/`axios` for `/api/*` calls and WebSocket helper utilities.
- **frontend/src/types/** – Shared TypeScript interfaces matching backend Pydantic schemas.

## E. Backend API routes and schemas
- **backend/src/driftshield/api/app.py** – FastAPI factory, CORS, and error handling.
- **backend/src/driftshield/api/routes.py** – Primary REST endpoints for runs, predictions, and health checks.
- **backend/src/driftshield/api/schemas.py** – Pydantic request/response models.
- **backend/src/driftshield/api/websocket.py** – WebSocket router for live streaming of predictions.

## F. Simulator and CSV replay (implemented)
- **backend/src/driftshield/simulator.py** – Seeded stream generator with abrupt drift scenarios.
- **backend/src/driftshield/run_manager.py** – Orchestrates runs, stores artifacts, and writes CSV outputs.

## G. Prediction and label delivery (implemented)
- **backend/src/driftshield/engine.py** – Core prediction engine that consumes simulated events.
- **backend/src/driftshield/labeling.py** – Budget‑aware label acquisition and delayed delivery.

## H. Drift detection (not yet implemented)
- No source files currently implement drift detection algorithms; placeholders are reserved in the `theory/` package.

## I. Candidate training and paired evaluation (implemented)
- **backend/src/driftshield/paired_evaluation.py** – Evaluates paired models on the same data stream.
- **backend/src/driftshield/evaluator.py** – Independent evaluator that scores predictions using delivered labels.

## J. Model promotion (not yet implemented)
- No promotion logic exists in the current code base.

## K. Database and persistence (implemented)
- **backend/src/driftshield/storage.py** – SQLite wrapper storing runs, artifacts, and theory experiment state.

## L. Theory Lab (implemented)
- **backend/src/driftshield/theory/** – Experimental modules:
  - `finite_domain.py` – Finite‑domain drift models.
  - `rare_region.py` – Rare‑region synthetic drift.

## M. Tests, benchmarks, and screenshots
- **backend/tests/** – Pytest suite covering configuration, contracts, simulator, labeling, evaluator, and integration.
- **backend/scripts/** – Benchmark and verification scripts.
- **frontend/** – Contains Vite build output (`dist/`) and screenshots under `docs/screenshots/`.
- **outputs/** – Generated run artifacts (CSV/JSON) and benchmark results.

**Note:** Only files that exist in the repository are listed. Missing or future modules are intentionally omitted.
