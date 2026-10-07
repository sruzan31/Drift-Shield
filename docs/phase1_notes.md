# DriftShield Phase 1 — Implementation Notes

## Status: Phase 1 repairs complete (post-review)

---

## Root Causes of Original Issues

### 1. Evaluation Gap
**Problem**: The evaluator only scored predictions that received an acquired label.
With a budget of 300 over 1800 post-warmup events (default config), the budget
exhausted on pre-drift data, so 0 post-drift predictions were ever scored.

**Fix**: Added a `full_synthetic_eval()` path in the `Evaluator`. For synthetic
runs, the evaluator compares every post-warmup prediction against the simulator's
hidden truth directly — no label acquisition required. The acquired-label channels
(monitor, selective) produce separate channel-level metrics.

### 2. Premature Warmup Flush Bypassed Fixed Delay
**Problem**: At the last warmup step (sequence `warmup_size - 1`), the runner
called `flush_all_pending(event.sequence)`. This delivered warmup labels whose
`delivery_sequence` was in the *future* (e.g., `warmup_size - 1 + delay`),
bypassing the delay guarantee.

**Fix**: Warmup flushing now uses the actual drain logic — only labels whose
`delivery_sequence <= current_sequence` are delivered. Delayed warmup labels
are delivered during the production stream loop as time advances.

**Consequence for warmup training**: With fixed delay, some warmup labels
arrive during the production phase (post-freeze). Those labels are accepted
by the baseline if it is not yet frozen; the freeze is deferred until all
warmup labels are delivered or the warmup window has fully elapsed.

### 3. Single Shared Budget vs. Separate Monitoring/Selective Budgets
**Problem**: A single `label_budget` covered both monitoring and selective
(low-margin) acquisition. The monitor rate of 0.10 × 1800 ≈ 180 events;
the selective channel added more until the shared budget of 300 was exhausted,
all before drift at seq 1000.

**Fix**: Added `monitor_budget` and `selective_budget` as separate fields.
Each channel has its own cap. Deduplication (an event selected by both channels
counts once, charged to the channel that selected it first) is preserved.

### 4. Label Accounting
**Added**: Per-channel counters for requested, delivered, pending, rejected.

### 5. Null vs. Zero
**Fix**: When a category has zero scored examples, `error_rate` is `None`
(serialized as `null` in JSON), not `0.0`.

---

## Evaluation Channels

### Full Synthetic Evaluation
- Uses simulator hidden truth for all predictions made post-freeze (`sequence >= evaluation_start_sequence`).
- Denominator: `n_events - evaluation_start_sequence` (1800 for delay=0, 1790 for delay=10).
- Broken down by pre-drift / post-drift (abrupt only).

### Random Monitoring Channel
- Uses only predictions selected by the monitor.
- Independent of model confidence.
- Denominator: number of monitor-selected labels acquired.

### Selective (Low-Margin) Channel
- Uses only predictions selected by low-margin query.
- Clearly identified as selectively sampled.
- Denominator: number of selective labels acquired.

---

## Warm-up / Freeze & Evaluation Protocol

1. During warmup, `register_warmup_features(event)` feeds the scaler incrementally.
2. Warmup labels are acquired unconditionally (source=`warmup`, not budget-charged).
3. Fixed label delivery equals `event_sequence + label_delay` (unclipped).
4. With `label_delay=0`: warmup label delivered at same step as event; `learn()` called immediately. Model freezes at sequence `warmup_size - 1` (199). Evaluation starts at sequence 200 (1800 evaluated predictions).
5. With `label_delay=N`: warmup label delivered N steps later; `learn()` called then if model not frozen. Model freeze is deferred until sequence `warmup_size - 1 + label_delay` (e.g. 209 for delay=10) after all warmup labels arrive and are learned. Evaluation starts at sequence 210 (1790 evaluated predictions: 790 pre-drift, 1000 post-drift).
6. End-of-stream draining advances logical time to `last_seq + label_delay` to drain all remaining pending labels.
7. After freeze, `learn()` raises `RuntimeError`; no post-freeze training occurs.

---

## Reserved Monitoring Capacity

- `effective_selective_budget` is capped at `selective_budget` (or `label_budget // 3` by default: 100 out of 300).
- `effective_monitor_budget` reserves the remaining capacity (at least 200 out of 300).
- Overlapping requests deduplicate by event ID and count once towards total unique budget.

---

## Verified Scenarios & Outputs

- `outputs_delay0/`
  - `stationary_predictions.csv`, `stationary_metrics.json`: evaluated=1800, error_rate=0.0000
  - `abrupt_predictions.csv`, `abrupt_metrics.json`: evaluated=1800, pre-drift=0.0000 (800), post-drift=1.0000 (1000), total=0.5556
- `outputs_delay10/`
  - `stationary_predictions.csv`, `stationary_metrics.json`: evaluated=1790, error_rate=0.0000
  - `abrupt_predictions.csv`, `abrupt_metrics.json`: evaluated=1790, pre-drift=0.0000 (790), post-drift=1.0000 (1000), total=0.5587

