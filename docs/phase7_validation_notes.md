# Phase 7A Validation Notes: Scenario Coverage & End-to-End Evaluation

**DriftShield ML Monitoring & Exact Adaptation Benchmark**  
*Document Version: Phase 7A Completed Verification*

---

## 1. Overview & Verified Scenarios

Phase 7A expands scenario coverage to all specification-defined MVP stream concepts under strict evaluator isolation, reproducible seeding, deterministic generators, and bounded resource constraints.

| Scenario ID | Concept Description | Mathematical / Generation Model | Ground Truth Evaluator Status |
| :--- | :--- | :--- | :--- |
| `stationary` | No concept drift across stream. | Fixed Gaussian clusters $C_0=(-1, -1), C_1=(+1, +1)$ with $\sigma=0.4$. | `drift_sequence = None`. Zero false alarms expected under stationary stream. |
| `abrupt` | Sharp concept flip at sequence $S$. | Pre-drift centroids flip post-$S$: $C_0=(+1, +1), C_1=(-1, -1)$. | `drift_sequence = S`. True post-drift starts immediately at event $S$. |
| `gradual` | Smooth mixture transition over window $W$. | At step $s \in [S, S+W)$, mixture probability $\alpha(s) = (s - S) / W$ interpolates $P(C_{\text{post}})$. For $s \ge S+W$, $\alpha(s) = 1.0$. | `drift_sequence = S`. Transition window $[S, S+W)$. Evaluator logs onset $S$, midpoint $S+W/2$, and completion $S+W$. |
| `recurring` | Periodic A-B-A concept oscillation. | Alternates between $C_{\text{pre}}$ and $C_{\text{post}}$ every $R = \text{recurrence\_interval}$ events after $S$. Phase $k = \lfloor (s - S) / R \rfloor \pmod 2$. | `drift_sequence = S`. Evaluator logs all transition boundaries $T_k = S + kR$. |
| `rare_region` | Stealth drift in small subpopulation. | Normal cluster distributions maintained; for $s \ge S$, instances in rare region of mass $p \le 0.05$ ($f_0 < z_p \sigma$) flip $0 \to 1$. | `drift_sequence = S`. Evaluator tracks rare subpopulation indicator. |
| `adversary` | Adaptive adversary maximizing past margins. | At dwell boundaries ($S, S+D, S+2D, \dots$), adversary inspects prior 200 recorded feature events and static baseline geometry; chooses rule $r^* \in \mathcal{C}$ maximizing past disagreement; commits before next arrival. | `drift_sequence = S`. Evaluator logs candidate set, cutoff sequence, selected rule $r^*$, and switch sequence. |

---

## 2. Adaptation Quotas & Lifecycle Policy

The candidate training and evaluation quotas strictly preserve the specification defaults:
- **Candidate Training Quota**: $N_{\text{train}} = 200$ unique post-epoch labels.
- **Paired Evaluation Target**: $N_{\text{eval}} = 500$ fresh random-monitoring evaluation events.
- **Minimum Gain Requirement**: $\Delta_{\text{min}} = 0.02$ (2 percentage points).
- **Significance Level**: $\alpha = 0.01$ via one-sided exact binomial sign test.
- **Concurrency Cap**: Maximum 1 active candidate per stream; maximum 5 completed comparisons per run.

---

## 3. Adaptive Adversary Specification & Information Boundary

1. **Past Information Consumed**:
   - The adversary inspects strictly the prior 200 recorded feature events $\mathbf{X}_{\text{past}} = \{\mathbf{x}_i\}_{i=t-200}^{t-1}$ buffer up to sequence $t-1$.
   - Margin scores are evaluated using the fixed geometric distance to the baseline decision boundary: $\text{margin}(\mathbf{x}) = |f_0 + f_1| / \sqrt{2}$. This represents the reference task geometry, distinct from dynamic internal weights of a retrained classifier.
2. **Causal Rule Commitment**:
   - The candidate rule $r^* \in \mathcal{C}$ maximizing disagreement on high-margin points ($\text{margin} \ge \text{median}$) is selected and committed strictly **before** event $t$ is sampled and emitted.
   - The adversary never peeks at the live model's uncommitted prediction for event $t$.
3. **No Unwarranted Worst-Case Claim**:
   - The adversary is a finite-candidate heuristic designed to test detector sensitivity against past-data-driven boundary shifts. It is not advertised or claimed to be a mathematically certified worst-case minimax optimal adversary.

---

## 4. Warmup vs. Post-Warmup Label Accounting

1. **Warmup Channel Isolation**:
   - Initial $W = \text{warmup\_size}$ events are labeled unconditionally to initialize the baseline classifier.
   - Warmup labels have `cost = 0.0`, `budget_debit = 0`, and are never charged against the post-warmup monitoring or selective budgets.
2. **Post-Warmup Budget Debits & Deduplication**:
   - Random monitoring and selective low-margin requests debit their respective channel budgets and the shared `label_budget`.
   - Overlapping requests for the same event are claimed once by the first channel (monitoring priority) and charged only once.
   - In SQLite storage, `label_requests` records all requests with exact channel provenance (`warmup`, `monitor`, `selective`).
3. **Pending Deliveries & Delay Invariance**:
   - When $\text{label\_delay} = D > 0$, labels become available strictly at sequence $t + D$.
   - The engine drains pending labels up to the current sequence ceiling and never leaks future labels prematurely.

---

## 5. Scenario-Aware Detection Delay Matching Semantics

Detection matching does not force every alarm into a successful detection:

### A. Gradual Drift Matching
- **Ground Truth Milestones**: Onset $T_{\text{onset}} = S$, Midpoint $T_{\text{midpoint}} = S + \lfloor W/2 \rfloor$, Completion $T_{\text{completion}} = S + W$.
- **Alert Classification**:
  - Alarms prior to $T_{\text{onset}}$ are classified as `early_alerts` and counted as `false_alarms`.
  - Alarms in $[T_{\text{onset}}, T_{\text{completion}}]$ are `transition_alerts`.
  - Alarms $> T_{\text{completion}}$ are `post_transition_alerts`.
- **Delays**: Evaluator reports delay from onset ($t_{\text{alert}} - T_{\text{onset}}$) and delay from midpoint ($t_{\text{alert}} - T_{\text{midpoint}}$).

### B. Recurring Drift Matching
- **Regime Windows**: $W_k = [S + kR, S + (k+1)R)$ for transition indices $k = 0, 1, 2, \dots$.
- **One-to-One Matching**: The first alert whose originating event sequence falls in regime $k$ matches transition $k$.
- **Duplicate Alerts**: Subsequent alerts originating within the same regime $k$ are recorded as `duplicate_alerts`.
- **Missed Transitions**: Transition regimes $k$ with zero alerts are flagged as `missed_transitions`.
- **Regime Boundary Crossing**: If event $t \in W_k$ has delivery sequence $t + D \ge S + (k+1)R$, the label arrives during regime $k+1$. The evaluator records this as a boundary-crossing alert with explicit originating vs arrival regime attribution.

---

## 6. Verified Test Suite & UI Evidence

### Full Backend Pytest Suite (226 / 226 Tests Passing)
```bash
backend/.venv/bin/pytest backend/tests
```
Output:
```
============================= 226 passed in 48.11s =============================
```

### End-to-End Browser UI Validation
- Automated Puppeteer script [`frontend/test_phase7_browser.mjs`](file:///Users/ksruzanroy/Desktop/Driftshield/frontend/test_phase7_browser.mjs) verified:
  1. All 6 scenario options selectable in `NewRun` form.
  2. Contextual parameter controls displayed and validated for `gradual_window`, `recurrence_interval`, `rare_region_p`, and `adversary_dwell`.
  3. Form submission creates a run in backend with exact parameters.
  4. Live Run view connects to WebSocket, starts stream execution, receives real-time snapshots, detects drift, evaluates candidate, and reaches `COMPLETED` state.
  5. Run History lists completed run with persisted metadata and metrics.
- Artifacts saved:
  - [`new_run_scenarios_verified.png`](file:///Users/ksruzanroy/.gemini/antigravity-ide/brain/7f73d383-81c0-45a1-89a2-fe0165842fb0/new_run_scenarios_verified.png)
  - [`live_run_scenario_completed.png`](file:///Users/ksruzanroy/.gemini/antigravity-ide/brain/7f73d383-81c0-45a1-89a2-fe0165842fb0/live_run_scenario_completed.png)
  - [`run_history_scenario_completed.png`](file:///Users/ksruzanroy/.gemini/antigravity-ide/brain/7f73d383-81c0-45a1-89a2-fe0165842fb0/run_history_scenario_completed.png)

---

## 7. Documented Limitations & Scope Constraints

1. **2D Continuous Numerical Features**: MVP stream generator models 2D Gaussian distributions with bounded noise. Arbitrary high-dimensional feature spaces are out of scope.
2. **Incomplete Adaptation on Truncated Runs**: Streams that terminate before accumulating 200 post-alert training labels or 500 evaluation labels legitimately leave candidate models in `INCOMPLETE` state. No artificial promotion is performed.
3. **Immutability of Historical Predictions**: Predictions recorded at event arrival remain immutable. Promoted candidate models apply strictly to subsequent events after promotion.
