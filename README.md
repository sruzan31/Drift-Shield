# DriftShield — Phase 1: ML Foundation

> **Synthetic data only.** DriftShield Phase 1 implements a reproducible
> numerical-stream simulator, independent evaluator, and genuine logistic-regression
> baseline. No drift detection or recovery is implemented yet.

---

## Overview

DriftShield is a framework for studying concept drift in production ML systems
under budget-constrained label acquisition. Phase 1 establishes the executable
foundation: reproducible data generation, honest evaluation, and a frozen baseline.

## Architecture

```
Stream Simulator ──► BaselineClassifier ──► PredictionRecord (locked)
      │                                              │
      │              LabelAcquirer ─────────────────►│
      │              (monitor + low-margin, budgeted) │
      │                                              │
      └─────────────► Evaluator ◄────────────────────┘
                      (hidden truth only)
                             │
                             ▼
                      EvaluationMetrics + CSV/JSON
```

## Tested Environment

| Component | Version |
|---|---|
| Python | 3.9.6 |
| river | 0.21.2 |
| numpy | <2.0 |
| pydantic | ≥2.0, <3.0 |
| scikit-learn | ≥1.3 |
| pytest | ≥7.4 |

## Quick Start

```bash
# 1. Create and activate the virtual environment
python3 -m venv backend/.venv
source backend/.venv/bin/activate   # Windows: backend\.venv\Scripts\activate

# 2. Install the package and dev dependencies
cd backend
pip install -e ".[dev]"

# 3. Run the tests
pytest tests/ -v

# 4. Run both CLI scenarios
python -m driftshield.run_baseline --output-dir outputs
```

## File Structure

```
backend/
├── pyproject.toml
├── src/driftshield/
│   ├── __init__.py
│   ├── config.py        # Pydantic config with full validation
│   ├── contracts.py     # Frozen dataclass contracts (StreamEvent, PredictionRecord, …)
│   ├── simulator.py     # Seeded stream generator (stationary + abrupt scenarios)
│   ├── labeling.py      # Budgeted label acquisition (monitor + low-margin, deduplicated)
│   ├── baseline.py      # River logistic regression: fit on warm-up, frozen thereafter
│   ├── evaluator.py     # Independent evaluator: scores locked predictions only
│   └── run_baseline.py  # CLI entry point; saves CSV + JSON outputs
└── tests/
    ├── test_config.py
    ├── test_contracts.py
    ├── test_simulator.py
    ├── test_labeling.py
    ├── test_evaluator.py
    └── test_integration.py
docs/
└── DriftShield_Final_Specification.md
```

## CLI Options

```
python -m driftshield.run_baseline [OPTIONS]

Options:
  --output-dir PATH   Output directory for CSV/JSON (default: outputs)
  --n-events INT      Total events per scenario (default: 2000)
  --warmup INT        Warm-up window size (default: 200)
  --budget INT        Post-warmup label budget (default: 300)
  --delay INT         Label delivery delay in steps (default: 0)
  --seed INT          Stream seed (default: 42)
```

## Design Decisions

### Hidden Labels
`StreamEvent` contains **no label field**. The `Simulator` stores hidden labels
internally and exposes them only to the `Evaluator`. This makes label leakage
to the learner physically impossible.

### Frozen Baseline
The `BaselineClassifier` fits a `StandardScaler` and River `LogisticRegression`
on warm-up data, then freezes both. Calling `learn()` after `freeze()` raises
`RuntimeError`. Post-freeze performance degradation under drift is expected and
correct — it is what the evaluator measures.

### Separate RNGs
- **Data generation RNG**: seeded from `StreamConfig.seed`. Controls all features
  and hidden labels.
- **Label selection RNG**: seeded from `LabelConfig.selection_seed`. Changing
  this seed does not affect any generated data.

### Budget and Deduplication
`LabelAcquirer` runs random monitoring and low-margin selection in parallel.
When both select the same event, it counts **once** against the budget. Each
acquired label is scheduled for delivery at `sequence + label_delay`.

### Evaluator Integrity
The `Evaluator` scores a prediction only after its label is delivered, never
before. Each `event_id` is scored at most once (idempotent). Warm-up predictions
are excluded from all reported metrics.

## Test Suite

```bash
pytest tests/ -v
# 82 passed in ~1s
```

| Test file | What it verifies |
|---|---|
| `test_config.py` | Pydantic validation: invalid scenarios, budgets, delays |
| `test_contracts.py` | StreamEvent/PredictionRecord frozen, NaN/inf rejection |
| `test_simulator.py` | Reproducibility, monotonic sequence, abrupt drift flip |
| `test_labeling.py` | Budget enforcement, deduplication, seed isolation, delay |
| `test_evaluator.py` | Warm-up exclusion, future-label isolation, error consistency |
| `test_integration.py` | End-to-end pipeline, CLI output files, abrupt > stationary error |

## Actual Measured Metrics (seed=42, n=2000, warmup=200, budget=300)

| Scenario | Scored | Error Rate | Labels Acquired |
|---|---|---|---|
| stationary | 300 | 0.0000 | 300 |
| abrupt | 300 | 0.0000 | 300 |

> **Note**: Both show 0% error because the budget of 300 is exhausted on
> pre-drift data (drift starts at seq 1000, post-warmup window starts at seq 200).
> When the budget covers post-drift events the error rate rises to **1.0000**,
> confirming the frozen model completely mis-classifies inverted-boundary data.
> This is correct and expected behaviour, not a bug.

## Limitations (Phase 1)

1. **No drift detection**: The system does not detect when drift occurs.
2. **No adaptation**: The baseline model is frozen after warm-up. Online
   learning and retraining are planned for future phases.
3. **Budget-limited scoring**: Only predictions for which a label is acquired
   are scored. With a small budget the scored window may not cover post-drift events.
4. **Two features only**: The simulator always generates `feature_0` and
   `feature_1`. Multi-feature support is a future enhancement.
5. **No real data connectors**: All data is synthetic.

## What Is NOT Implemented

- Drift detection algorithms (ADWIN, DDM, etc.)
- Model adaptation / online learning
- REST API or frontend UI
- Database persistence
- Real data connectors
# Drift-Shield
