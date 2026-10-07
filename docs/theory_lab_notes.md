# DriftShield Theory Lab — Formal Theory Notes

## 1. Overview and Purpose

The Theory Lab provides an isolated, mathematically verifiable environment to study fundamental limits of drift detection and online adaptation under formal information constraints.

- **Phase 2A (T4)**: Matching rare-region detection bounds under random stream sampling.
- **Phase 2B (T5)**: Tight finite-domain exact adaptation bounds under active membership query access.

---

## 2. Phase 2A: Rare-Region Detection Experiment (T4)

### 2.1 Exact Theoretical Assumptions

1. **Known Reference Rule $f_0$**: $f_0: [0, 1] \to \{0, 1\}$ is deterministic and known to the detector (default $f_0(x) = 0$).
2. **Fixed Deterministic Target Rule $f_1$**: After change onset, true rule $f_1: [0, 1] \to \{0, 1\}$ is deterministic and static across post-drift events ($f_1(x) = 1$ when $x < p$, else $0$).
3. **Disagreement Mass $p$**: Inputs $X_t \sim \text{Uniform}[0, 1]$ i.i.d., with disagreement mass $p = \Pr[f_0(X) \ne f_1(X)]$.
4. **Independent Random Labeling $q$**: At each event $t$, query indicator $Q_t \sim \text{Bernoulli}(q)$ is independent of $X_t$ and past events.
5. **Immediate, Noiseless Feedback**: When $Q_t = 1$, true label $y_t = f_1(X_t)$ arrives immediately with zero label noise.
6. **Detector Isolation**: The detector receives only features $X_t$ and authorized labels $y_t$ when $Q_t = 1$. Unqueried labels, change timestamps, and the boundary $p$ remain evaluator-only.
7. **First-Disagreement Detector**: Alerts at the first stream event where an authorized label differs from $f_0(X_t)$. False-alarm probability under $f_0$ is strictly $0.0$.

### 2.2 Mathematical Formulations

Let $r = q \cdot p$. Delays and times are measured as **1-based stream event counts** (i.e. if an alert fires on the 1st event, delay is 1).

1. **Theoretical Miss Probability After Deadline $D$**:
   $$P(\text{miss} \mid D) = (1 - r)^D$$
   For $p=0.05, q=0.20, D=100$: $P(\text{miss}) = 0.99^{100} \approx 0.366032$.
   At $D=299$: $P(\text{miss}) = 0.99^{299} \approx 0.049536257 \le 0.05$.

2. **Minimum Deadline $D^*$ for Target Miss Probability $\delta$**:
   $$D^* = \left\lceil \frac{\ln(1/\delta)}{-\ln(1 - r)} \right\rceil$$
   For $p=0.05, q=0.20, \delta=0.05$: $D^* = \left\lceil \frac{\ln(20)}{-\ln(0.99)} \right\rceil = 299$.

3. **Uncensored Expected Detection Time**:
   $$\mathbb{E}[T] = \frac{1}{r} \quad (\text{for } r > 0)$$
   At $p=0.05, q=0.20$: $\mathbb{E}[T] = 100.00$ stream events.

4. **Mean Time Conditional on Detection by $D$**:
   $$\mathbb{E}[T \mid T \le D] = \frac{1}{r} - \frac{D (1 - r)^D}{1 - (1 - r)^D} \quad (\text{for } 0 < r < 1, D \ge 1)$$
   At $p=0.05, q=0.20, D=100$:
   $$\mathbb{E}[T \mid T \le 100] = 100 - \frac{100 \times 0.99^{100}}{1 - 0.99^{100}} \approx 42.263247 \text{ events}$$

5. **Expected Observation Time Until Detection or Deadline**:
   $$\mathbb{E}[\min(T, D)] = \frac{1 - (1 - r)^D}{r} \quad (\text{for } r > 0)$$
   At $p=0.05, q=0.20, D=100$: $\mathbb{E}[\min(T, 100)] \approx 63.396766 \text{ events}$.

6. **Expected Acquired Labels Until Detection or Deadline**:
   $$\mathbb{E}[\text{Labels}] = q \cdot \mathbb{E}[\min(T, D)] = \frac{q (1 - (1 - r)^D)}{r} = \frac{1 - (1 - r)^D}{p}$$
   At $p=0.05, q=0.20, D=100$: $\mathbb{E}[\text{Labels}] \approx 12.679353 \text{ labels}$.

### 2.3 Degenerate Cases
- $r = 0$: Uncensored and conditional detection times are undefined (`None` / null). Expected observation time is $D$. Expected labels is $q \cdot D$.
- $r = 1, D \ge 1$: Uncensored, conditional, and observation times are $1.0$. Expected labels is $1.0$.
- $D = 0$: Conditional detection mean is `None`. Observation time and labels are $0.0$.

---

## 3. Phase 2B: Tight Finite-Domain Exact Adaptation (T5)

### 3.1 Problem Setting
Let $\mathcal{X} = \{x_1, \dots, x_N\}$ be a known finite domain of $N \ge 1$ distinct inputs.
- The learner knows the domain $\mathcal{X}$ and the prior deterministic rule $f_0: \mathcal{X} \to \{0, 1\}$.
- A change replaces $f_0$ with an arbitrary fixed binary target $f_1: \mathcal{X} \to \{0, 1\}$.
- The learner can perform active membership queries to an oracle that reveals $f_1(x_i)$ noiselessly.

### 3.2 Matching Upper and Lower Bounds

#### Upper Bound ($N$ Queries Suffice)
By querying every input $x_i \in \mathcal{X}$ exactly once ($N$ queries total):
1. The learner constructs a complete lookup table $T(x_i) = f_1(x_i)$ for all $x_i \in \mathcal{X}$.
2. The learner detects whether any drift occurred by checking if $T(x_i) \ne f_0(x_i)$ for any $x_i$.
3. Subsequent predictions using $T$ achieve zero error across the entire domain as long as $f_1$ remains fixed.

#### Lower Bound ($N$ Queries are Necessary in Worst Case)
Suppose an algorithm stops after $M < N$ queries on a transcript matching $f_0$.
1. There exists at least one unqueried input $x_j \in \mathcal{X}$.
2. Consider two candidate worlds:
   - World $W_0$: true rule is $f_0$.
   - World $W_1$: true rule is $f_1$ which agrees with $f_0$ everywhere except at $x_j$ where $f_1(x_j) = 1 - f_0(x_j)$.
3. Because $x_j$ was not queried, both worlds generate the identical observed query transcript.
4. Any deterministic or randomized algorithm must output the same prediction and drift verdict on that transcript.
5. Therefore, the algorithm is wrong in at least one world. Exact identification on the entire domain is impossible with $< N$ queries.

### 3.3 Audit State Machine & Prediction Contract
- **During Audit ($M < N$)**: Unqueried inputs are marked **unresolved**. The auditor does not advertise zero-risk predictions for unqueried inputs.
- **Post Audit ($M = N$)**: Audit status transitions to **COMPLETE**. Zero-risk lookup predictions are authorized.

---

## 4. Key Takeaways & Scope Boundaries

1. **ADWIN Contrast**: T4 guarantees do not transfer to ADWIN or logistic regression, which operate under continuous loss distributions, estimation variance, and non-zero false-alarm budgets ($\delta_{\text{adwin}} > 0$).
2. **Cost Semantics**: Acquired labels represent physical oracle costs incurred during stream monitoring, not merely scored evaluation denominators.
3. **Role of Experiments**: The empirical runs illustrate and validate the mathematical formulas; the proofs establish the universal lower and upper bounds.
