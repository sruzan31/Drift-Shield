# DriftShield Phase 4 — Candidate Adaptation & Paired Promotion Notes

## 1. Overview and Architecture

Phase 4 implements DriftShield's end-to-end adaptive lifecycle:
- **Phase 4A**: Candidate model initiation and post-alert incremental training.
- **Phase 4B**: Fresh paired evaluation and statistical promotion.

When River `ADWIN` detects statistical evidence of an error change, DriftShield does **not** mutate or replace the active serving model immediately. Instead:
1. Spawns an isolated candidate model trained strictly on post-epoch authorized labels.
2. Freezes the candidate model upon reaching 200 unique training labels.
3. Gathers a fresh sample of 500 post-freeze random-monitoring events with locked-in predictions from both active and candidate models.
4. Executes an exact one-sided McNemar / binomial sign test on disagreements ($b$ and $c$).
5. Promotes the candidate if $\text{gain} \ge 0.02$ and $p\text{-value} \le 0.01$, switching model ownership atomically and resetting ADWIN.

---

## 2. Adaptation Invariant Protocol (Phase 4A)

### 2.1 Adaptation Epoch Definition
The adaptation epoch is defined at the **actionable alert sequence** (the stream sequence when the label arrived and ADWIN emitted the alert), **not** the older historical event sequence of the triggering observation:
$$\text{epoch} = \text{alert.arrival\_sequence}$$

### 2.2 Strict Post-Epoch Data Filtering
- Only authorized labels belonging to events generated **strictly after** the epoch ($\text{event\_sequence} > \text{epoch}$) are eligible to train the candidate model.
- **Delayed Old Labels Excluded**: Any delayed labels from pre-epoch events ($\text{event\_sequence} \le \text{epoch}$) continue to score their original predictions in evaluation, but **must never** enter candidate training.
- Prevents contamination from pre-alert distributions without inventing unverified change-point estimators.

### 2.3 Preprocessor & Model Invariance
- **Frozen Preprocessor Reuse**: The candidate classifier reuses the run's `StandardScaler` fitted during warm-up. Feature scaling statistics are **never updated** during candidate training.
- **Independent Candidate Initialization**: The candidate classifier is instantiated as a fresh, independent River `LogisticRegression` instance with SGD.
- **Active Model Immutability**: The active serving model remains strictly frozen throughout candidate training.

### 2.4 Target Budget & Freezing
- Candidate training requires a predeclared budget of **200 unique post-epoch labels**.
- Overlapping channel labels (monitor + low-margin queries) are deduplicated by `event_id` and train the candidate model once.
- Once the 200th unique label is absorbed, the candidate model is **immediately frozen** and its state transitions to `READY_FOR_EVALUATION`.

---

## 3. Fresh Paired Evaluation Protocol (Phase 4B)

### 3.1 Evaluation Event Selection
- Starts strictly after candidate training freezes ($\text{sequence} > \text{candidate.freeze\_sequence}$).
- Selects the first $N = 500$ fresh **random-monitoring** events in stream sequence order.
- **Selective-Only Labels Excluded**: Low-margin / selective channel labels cannot enter paired evaluation because they are not representative of stream risk.
- **Training Separation**: Evaluation events cannot overlap candidate training events ($\text{freeze\_sequence} \ge \text{training events}$).

### 3.2 Locked-In Prediction Recording
- For every evaluation event, predictions from both active and candidate models are recorded at event arrival **before** revealing the ground-truth label:
  $$\hat{y}_{\text{active}}, \hat{P}_{\text{active}}, \hat{y}_{\text{candidate}}, \hat{P}_{\text{candidate}}$$
- Neither model is updated retrospectively.

### 3.3 Disagreement Classification & Statistical Test
Let:
- $b$: Number of evaluation events where the active model was **wrong** and the candidate model was **correct** ($y_{\text{true}} = \hat{y}_{\text{candidate}} \neq \hat{y}_{\text{active}}$).
- $c$: Number of evaluation events where the active model was **correct** and the candidate model was **wrong** ($y_{\text{true}} = \hat{y}_{\text{active}} \neq \hat{y}_{\text{candidate}}$).
- $n$: Total paired evaluation observations ($n = 500$).

The observed candidate risk gain is:
$$\text{Gain} = \frac{b - c}{n}$$

Under the null hypothesis $H_0: P(\text{candidate correct} \mid \text{disagreement}) \le 0.5$ (the candidate risk is no lower than active risk), the exact one-sided binomial sign test evaluates:
$$p\text{-value} = \text{scipy.stats.binomtest}(b, b + c, p=0.5, \text{alternative}=\text{"greater"}).pvalue$$

If $b + c = 0$ (zero disagreements), there is no evidence of improvement, and $p\text{-value} = 1.0, \text{gain} = 0.0$.

### 3.4 Promotion Decision Criteria
The candidate model is **PROMOTED** if and only if both conditions hold simultaneously:
1. $\text{Gain} = \frac{b - c}{n} \ge 0.02$ (minimum observed risk improvement of 2 percentage points).
2. $p\text{-value} \le 0.01$ (one-sided exact sign test significance).

If either condition fails, the candidate is **REJECTED**, and the active model is retained.

### 3.5 Single Decision & Delayed Label Handling
- Evaluation is executed **exactly once** after all 500 labels arrive. There is no continuous peeking or early stopping.
- If labels are delayed, the evaluation set is held until all 500 labels arrive or until a documented timeout / stream termination occurs.
- If the stream terminates or times out before all 500 labels arrive, the decision is declared **`INCOMPLETE`**, and no promotion occurs.

---

## 4. Statistical Error Budget & Limitations

### 4.1 Error Allocation
- **Comparison Cap**: At most **5 completed comparisons** (decisions of PROMOTED or REJECTED) are permitted per stream run.
- **Family-Wise Error Rate Bound**: Under fixed models, representative random-monitoring sampling, and i.i.d. observations, testing each candidate at $\alpha = 0.01$ ensures a total family-wise error allocation:
  $$\alpha_{\text{total}} \le 5 \times 0.01 = 0.05$$
  via the union bound / Bonferroni inequality.

### 4.2 Diagnostic Nature Under Non-I.I.D. or Continuing Drift
- **Assumption Scope**: The certified statistical error allocation applies under the specification's i.i.d. fixed-model assumptions.
- **Continuing Drift / Dependence**: For autocorrelated, dependent, or continuing-drift data streams, the reported $p$-value is explicitly documented as **diagnostic**.
- DriftShield reports empirical recovery and false-promotion rates rather than asserting an unverified i.i.d. guarantee for evolving non-stationary environments.

---

## 5. Atomic Promotion & Lifecycle Management

### 5.1 Next-Event Model Switching
- When a candidate is promoted, model ownership switches atomically between events.
- Active model version transitions from `v1.0-frozen` to `v2.0-promoted` (and sequentially `v3.0-promoted`, etc.).
- The very next stream event prediction uses the promoted classifier weights.

### 5.2 Reference Detector Reset
- Upon promotion, `ErrorChangeMonitor` resets River `ADWIN` with a fresh detector instance for the newly active model version.
- **Old-Version Label Isolation**: Delayed labels arriving for events predicted under previous model versions score their respective historical model versions in evaluation, but **must never** update the new version's ADWIN detector.
- Previous model artifacts, prediction logs, alerts, and evaluation summaries are preserved for complete auditability.

---

## 6. Output Artifacts and Export Summary

For each scenario, DriftShield exports:
- `{scenario}_predictions.csv`: Locked-in stream predictions with model version attribution and ground truth.
- `{scenario}_alerts.csv`: Audit log of all ADWIN error-change alerts with sequence, delay, estimation, and width.
- `{scenario}_candidate_training.csv`: Log of every authorized label absorbed during post-epoch candidate training.
- `{scenario}_candidate_summary.json`: Candidate lifecycle states, epoch, training counts, and transition logs.
- `{scenario}_paired_evaluation.csv`: Paired predictions from active and candidate models on evaluation events.
- `{scenario}_paired_summary.json`: Statistical evaluation results ($b, c, n$, gain, $p$-value, thresholds, decision, and reasons).
- `{scenario}_metrics.json`: Consolidated run metrics, config snapshot, and execution environment metadata.
