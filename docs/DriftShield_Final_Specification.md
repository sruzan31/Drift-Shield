# DriftShield — Consolidated Design and Build Specification

Status: design specification; no application implementation or benchmark results claimed.
Prepared for Problem 7, Online Concept-Drift Adaptation Engine, and Phase 1 Design & Planning.
Revision 2: promotion evaluation, buffer isolation, adaptive adversary, scope tiers, judge summary, and proof draft.

## 1. Decision and evidence base

This specification consolidates the problem statement, the Phase 1 judging sheet, the initial uploaded build specification, the subsequent comparative review, the four supplied proposals labeled ChatGPT, Gemini, Grok, and Perplexity, Claude's pasted proposal, and the technical discussion shared in this conversation. The second set of four uploads contains byte-identical copies and has been deduplicated. It does not claim to review additional research that has not been supplied.

Build a streaming classification monitoring and recovery product for ML engineers. Its distinctive feature is a Theory Lab connecting controlled experiments to precise information limits. The main application is a practical engine; the finite-domain exact algorithm is a proof demonstration, not the principal product.

| Research suggestion | Final decision | Reason |
|---|---|---|
| Universal perfect detection and instantaneous zero error | Refute formally | Explicitly permitted impossibility route; impossible without restrictions |
| Rare-region matching bound | Core theoretical result | Explicit lower bound and achievable detector |
| Finite-domain N-query result | Core theory demonstration | Matching exact identification bound under stated assumptions |
| Random and uncertainty label channels | Adopt | Separate representative monitoring from selective training |
| ADWIN on labeled loss | Adopt for practical monitoring | Established mechanism; no blanket false-alarm guarantee for our controller |
| Logistic regression and adaptive tree both inside custom adaptation | Simplify | Logistic regression is the MVP learner; adaptive tree is an optional benchmark |
| KS, PSI, and MMD together | Simplify | Periodic univariate KS diagnostics only; avoid redundant cost and unclear interpretation |
| Concept memory | Future feature | Requires label-based validation; fingerprints alone cannot identify a concept |
| Automatically escalating random label rate | Defer | Complicates budgets and the monitoring analysis |
| SMS/scam classification | Defer | Adds text preprocessing and data licensing before the core engine is validated |
| LLM explanations, RAG, agents | Remove | Structured evidence and templates suffice |
| PostgreSQL and independent worker services immediately | Defer | SQLite and one controlled local process fit the hackathon MVP |
| Offline execution and replay | Adopt | Reliable demonstration; replay must be explicitly labeled |
| Universal detection threshold based only on drift magnitude | Reject | Detectability depends on the observation channel, statistic, and assumptions |
| Perceptron mistake bound as exact finite-query adaptation | Reject | A mistake bound is not a total-label bound or certificate of zero population risk |
| Fixed-share ensemble as fallback without labels | Defer | Standard expert-feedback guarantees do not automatically survive missing/delayed/selective labels |
| Automatically classify any observed stream as possible/impossible | Reject | Hidden assumptions cannot generally be certified from a finite observation history |

## 2. Exact problem and product purpose

Operational problem: deployed classifiers can degrade when the relationship between features and labels changes. Labels are expensive or delayed, and engineers need evidence about degradation, a controlled recovery process, and an audit trail.

DriftShield accepts numerical feature events, produces binary predictions, joins later labels, monitors changes, trains a candidate replacement, and reports whether the replacement improves subsequent measured performance.

Primary user: an ML engineer operating a numerical binary classifier. A concrete deployment context is monitoring a classifier that identifies equipment operating states from numerical telemetry, with labels supplied by inspection or downstream outcomes. The hackathon demonstration uses controlled simulated telemetry-like streams, not a claimed field deployment.

Success means reproducible detection and recovery measurements, reliable event processing, visible label costs, and formal statements that match the demonstrated observation protocol. It does not mean solving arbitrary drift perfectly.

For classification risk, define R_t(h) = Pr[h(X) != Y] under the distribution at time t. Zero empirical mistakes and R_t(h)=0 are different claims.

## 3. Theory deliverables and boundaries

### T1. Unlabeled blindness

If the feature distribution is unchanged while the labeling relationship changes, the feature-only observation law can be identical before and after drift. Example: X is uniform on [0,1], and the label switches from 1[X>0.5] to its complement. No feature-only detector can perfectly distinguish these worlds.

### T2. No universal finite-label exact identification

For an unrestricted labeling class on an unrestricted domain, finitely many queries leave possible concepts that agree on all queried inputs and disagree elsewhere. Consequently, there is no uniform finite label budget guaranteeing exact identification for every concept. The domain/distribution can assign positive probability to an unqueried point, so this also defeats universal zero-risk adaptation.

### T3. No instantaneous guaranteed adaptation

At the first prediction after an unannounced change, two possible new concepts can produce opposite labels for the same input while sharing the learner's entire observed past. A randomized binary prediction has worst-case error at least 1/2; a deterministic one is wrong in one world. This is an information constraint before distinguishing feedback, not a statement about CPU speed.

### T4. Matching rare-region detection bound

Assume a known old deterministic rule f0; a fixed noiseless new rule f1; independent inputs from a fixed distribution; disagreement mass p = Pr[f0(X) != f1(X)]; independent random labeling probability q per event; immediate labels; and no side information disclosing the change.

Alert at the first labeled disagreement. Its false-alarm probability under no change is zero. After D events its missed-detection probability is exactly (1-qp)^D. Among zero-false-alarm detectors restricted to these observations, this is a matching lower bound: on histories without labeled disagreement, the evidence is compatible with no change.

For 0<qp<1, detection with probability at least 1-delta requires and is achieved by:

    D >= ceil( ln(1/delta) / [-ln(1-qp)] ).

Equivalently, for D>=1 and q>0, p >= [1-delta^(1/D)]/q. If the threshold exceeds 1, that deadline/reliability target is infeasible. If qp=0, this channel cannot detect the change. If qp=1, detection occurs at the first event.

In labeled samples rather than stream events, the miss probability after m labels is (1-p)^m. Expected labels until the first disagreement are 1/p for p>0; expected stream events are 1/(qp). These are noiseless restricted bounds, not guarantees for ADWIN or noisy streams.

### T5. Tight finite-domain exact adaptation

Assume a known domain of N inputs, noiseless deterministic labels, an exactly known old rule, a membership-label oracle, and a new rule fixed throughout audit and the subsequent guaranteed period. Querying every input once detects any labeling-function difference and learns the complete new rule. N queries suffice and are necessary in the worst case. Predictions after the completed audit are exact until the next change. This does not detect input-probability changes, guarantee predictions during the audit, or apply without query access.

### T6. Noise and frequent adversaries

An independent fair-coin label has Bayes error 1/2 even without drift. An unrestricted sequence of freshly unpredictable label choices also defeats universal prediction guarantees. Distinguish an oblivious adversary fixing a sequence in advance from an adaptive adversary using past predictions. A label chosen after seeing the current realized prediction is an even stronger protocol and must not be silently mixed into other experiments.

### Detectable/adaptable classes

| Class | Formal conclusion |
|---|---|
| Pure conditional drift observed through features only | Can be observationally indistinguishable |
| Known noiseless rule with disagreement mass p and random labels q | T4 gives a deadline-dependent detection characterization |
| Arbitrary deterministic functions on known finite domain with query oracle | T5 gives exact N-query identification |
| Stable realizable finite hypothesis class with iid labels | Consistent learning gives error <= epsilon with confidence 1-delta after ceil((ln|H|+ln(1/delta))/epsilon) labels |
| Unrestricted noise or unrestricted continuing drift | Universal exact adaptation unavailable |

The finite-class learning result assumes samples from the same stable new regime and a consistent learner. A detector's alert does not certify a clean change boundary. Label delay, censoring, and regime contamination must be addressed separately.

VC-dimension background rates are roughly (d+ln(1/delta))/epsilon in the realizable setting and (d+ln(1/delta))/epsilon^2 for agnostic excess error. These are not automatically achieved by our selected online algorithm. Likewise, a noisy mean-change detection rate involving 1/Delta^2 requires a specified noise model and testing protocol. We will not present unfinished general statements as proved engine guarantees.

## 4. MVP features and screens

1. Run configuration: choose scenario, seed, stream rate, random label rate, label budget, and label delay.
2. Live monitor: decision boundary for two-dimensional streams, rolling errors, label spend, throughput, and detector evidence.
3. Incident detail: warning reason, timestamps, reference model, candidate training/evaluation status, and promotion decision.
4. Theory Lab: feature-invisible drift; rare-region probability experiment; finite-domain N-query audit.
5. Benchmarks/history: saved configurations, baseline comparisons, uncertainty intervals, and downloadable results.

States: warming up, monitoring, candidate training, candidate evaluation, promoted, rejected, labels unavailable, degraded, paused, completed. Alerts say 'evidence of error change' or 'feature-distribution warning', not 'all drift confirmed'.

## 5. Complete user workflow

The engineer creates a run, selects a simulated source or approved numerical event source, defines a feature schema, sets a labeling policy, and starts the stream. Initial labeled events warm up the classifier. The live view then shows predictions and monitoring coverage. When evidence triggers an incident, the application opens candidate training while the active model keeps serving. After a fresh comparison period, it promotes or rejects the candidate and records the decision. The engineer inspects evidence, checks unresolved labels, compares baselines, and exports the run.

The Theory Lab is a separate workflow: select assumptions, run repeated experiments, inspect theoretical probabilities and empirical frequencies, then deliberately violate an assumption and observe why the original guarantee no longer applies.

## 6. Architecture and concurrency

React communicates with a FastAPI backend over HTTP and WebSocket. One serialized engine actor owns each run's mutable models, detectors, RNGs, and buffers. Heavy benchmark runs execute separately from the live run. A single database writer batches SQLite transactions. Bounded queues provide backpressure; CPU work must not execute directly on the API's asynchronous event loop.

Logical modules: input adapters; schema validation; event sequencer; prediction engine; label scheduler/joiner; monitor; adaptation controller; persistence/checkpoints; independent evaluator; dashboard publisher.

The simulator and independent evaluator can access hidden labels, concepts, and change schedules. The learning engine sees only feature events and the labels authorized by its policy. Public user controls for injected drift never become a detector trigger. A theory membership oracle is available only in explicitly labeled exact mode.

MVP deployment: one backend instance, a bounded number of runs, SQLite on persistent local disk. Do not start multiple independent engine owners for the same run. Production scaling partitions runs across workers, introduces a durable broker, and migrates shared state to PostgreSQL.

## 7. AI/ML and adaptation policy

Use River online logistic regression for the numerical binary MVP. Fit normalization using the initial warm-up data, then freeze it for that run; changing normalization silently changes the deployed function. Reject unexpected schemas. Logistic regression suits threshold and rotating-linear-boundary experiments. Use nonlinear scenarios later with an appropriate tree learner. A Hoeffding Adaptive Tree may be a benchmark, not a second controller inside our own replacement policy.

Freeze the active deployed model within each version. This makes reference-model error monitoring easier to interpret. Train replacement models separately. A continuously updating logistic regression is a baseline.

Random monitoring channel: choose events independently of their features/predictions with configured probability q; reserve its label budget. Uncertainty channel: request additional labels for low-margin events within a separate budget. Log the channel and deduplicate overlap. Selected labels can train candidates, but monitoring and representative candidate comparisons use random-channel events. Model confidence is a score, not a certified probability of correctness.

Use ADWIN on the frozen active model's random-channel binary loss. A detection event is practical statistical evidence; do not claim its configuration parameter is a global run-level false-alarm bound. Reset the reference detector after promotion. Periodic KS comparisons on selected numerical features produce diagnostics, with the number of tested features and windows logged. A feature warning alone does not replace a classifier.

Candidate policy: an error-change alert starts a fresh candidate, subject to an elevated recent error check, minimum labeled evidence, and cooldown. Define an adaptation epoch at the alert event sequence. Only authorized labels belonging to events strictly after that sequence train the candidate; delayed labels from earlier events remain eligible for their original prediction metrics but not for candidate training. Do not claim this is the true change boundary. This conservative choice discards potentially useful recent data but prevents intentional reuse of pre-alert training events. Continuing drift can still contaminate the new epoch. River ADWIN's retained width refers to its supplied loss observations, not a certified stream change point; a window-based optimization would require explicit loss-to-event mapping and its own assumptions.

After a predeclared training budget, freeze the candidate and active models for a paired evaluation on fresh random-channel events. For each evaluation event, record both predictions before its label arrives. Let b count active-wrong/candidate-correct events, c count active-correct/candidate-wrong events, and n count all evaluation events. The observed candidate gain is (b-c)/n. Under fixed models, iid evaluation observations, representative label sampling, and the null that the candidate's risk is no lower, the one-sided exact paired sign/McNemar-style test uses P[Binomial(b+c, 1/2)>=b]. If b+c=0, there is no evidence of improvement.

Evaluate once at the fixed sample count; do not repeatedly peek and stop early. Pilot defaults: 200 candidate-training labels, 500 evaluation labels, a minimum observed gain of 2 percentage points, and at most five completed comparisons per run. Allocate a run-level 0.05 error budget as 0.01 per comparison when the test assumptions hold. Promote only if both the gain requirement and the paired-test threshold pass. Otherwise retain the active model. These window sizes and gain requirements are engineering choices, not zero-risk guarantees. For temporally dependent or continuing-drift streams, label the p-value diagnostic unless a valid dependence-aware analysis is supplied; report empirical false-promotion results instead of claiming the iid error budget applies.

With delayed labels, the evaluation set is selected by event sequence, not fastest label arrival: the first configured number of random-channel selected evaluation events. Wait for all their labels or time out without promotion, preventing selective completion from silently redefining the sample. Cap memory and candidate concurrency, and preserve the old version.

Record candidate predictions at event arrival. Never calculate its earlier predictions retrospectively after training. Delayed labels score the model versions that actually predicted that event. If candidate evaluation data are insufficient or another change occurs, report incomplete/possibly contaminated evidence rather than certainty.

## 8. Data, schemas, and event flow

Primary data: seeded numerical generators with a documented initial concept and controlled change schedule. Start with two features and binary labels. Scenarios: stationary; abrupt threshold change; moving boundary; gradual concept mixture; recurring A-B-A; rare-region stealth; fast flip-flop; unchanged-feature label flip; label noise; delayed labels; and the adaptive adversary below.

Adaptive adversary: at a predeclared eligible boundary after a minimum dwell time, inspect only the prior 200 recorded feature events and deployed-model margins. Choose a new labeling rule from a finite set of threshold or linear-boundary candidates that maximizes disagreement with the model on those past high-margin events. Commit the rule before the next input and prediction, then hold it fixed for the configured dwell interval. Log the candidate set, past-information cutoff, selected rule, seed, and switch time in evaluator-only records. If no different rule meets the configured criterion, record no change. This is adaptive to past behavior, unlike a prewritten flip-flop schedule; it never chooses a current label after seeing the current prediction. The unconditional iid T4 formula is not advertised for this adaptive schedule.

Gradual mixtures can introduce irreducible ambiguity. Feature-only changes need not degrade a classifier. Label-noise corruption can be either a modeled stochastic environment or a compromised labeling channel; identify which protocol is tested.

Optional later data: a properly licensed public chronological stream or organization-supplied telemetry with trusted downstream labels. Without annotated real change events, report predictive performance and alert evidence, not ground-truth detection recall. Synthetic streams are labeled synthetic; no invented claims of deployment.

Feature event: run_id, event_id, sequence, event_time, schema_version, numerical features. Server adds received_time. Labels arrive separately: event_id, binary label, source/channel, arrival_time. Predictions store model version, predicted label, score, and latency. Hidden simulator truth is separately stored and inaccessible to the engine.

Flow: validate -> persist accepted event -> enqueue -> predict and record -> choose label requests -> publish result. On label arrival: authenticate/validate -> persist -> join original prediction -> score eligible monitors/comparisons -> train eligible candidate -> log transition. All mutations pass through the run owner.

For iid immediate-label theory experiments, process in event order. For practical delayed-label runs, process available labels in a logged deterministic arrival order. Label delay and arrival-order selection can bias monitoring; display coverage and delay distribution, and do not extend the iid theorem to them.

## 9. Real-time processing

Real-time means bounded ingestion-to-prediction latency and fresh operational displays, not instant detection. Initial performance targets: 100 events/second for one small stream, p95 accepted-event-to-prediction latency under 100 ms on the documented laptop, and chart refresh every 500 ms. Measure API overhead and persistence separately from model inference. These targets require benchmarks; no results exist yet.

Run-level queues are bounded. Return 429 or 503 with retry guidance when capacity is reached. Batch database writes and dashboard aggregates; do not send every historical event to the browser. Candidate work never waits in the critical prediction path. CPU saturation reduces the admitted stream rate rather than creating unlimited lag.

## 10. Database and API contracts

SQLite tables:

| Table | Key information |
|---|---|
| runs | configuration, seed, mode, schema, state, dependency versions |
| events | run/event unique key, sequence, times, features, processing status |
| predictions | event, model version, label, score, latency |
| labels | event, trusted source, channel, arrival, validation status |
| label_requests | event, channel, budget debit, request status |
| incidents | alert type, evidence, candidate, outcome |
| model_versions | model/preprocessor artifacts, checkpoint, activation sequence |
| metric_windows | time/sequence interval, method, metric, sample count |
| benchmarks | scenarios, seeds, configurations, artifact locations |
| evaluator_truth | synthetic labels and drift intervals; evaluator-only |

Store per-event records for reproducibility, then enforce retention/export policies. Keep chart aggregates separately. Use foreign keys, transaction boundaries, and unique event keys. Artifacts use server-generated paths and content hashes.

| Endpoint | Contract |
|---|---|
| POST /api/runs | Create validated configuration; idempotency key |
| POST /api/runs/{id}/control | Start, pause, resume, stop; injection permitted only for simulation |
| POST /api/runs/{id}/events | Accept bounded batch; 202 only after durable acceptance; event IDs returned |
| GET /api/runs/{id}/events/{event_id} | Processing status and recorded prediction |
| POST /api/runs/{id}/labels | Submit validated labels; deduplicate and reject conflicts |
| GET /api/runs/{id} | State, summary, coverage, backlog |
| GET /api/runs/{id}/incidents | Paginated evidence and decisions |
| GET /api/runs/{id}/report | Configuration and results export |
| POST /api/benchmarks | Queue bounded benchmark job |
| GET /api/benchmarks/{id} | Progress and results |
| WS /api/runs/{id}/live | Sequenced metrics, alerts, predictions |
| GET /health and GET /ready | Process liveness and persistence/engine readiness |

MVP WebSocket reconnect retrieves the latest run snapshot and resumes live aggregates. Lossless cursor replay is a production extension. Do not imply that every dropped browser message was replayed in the MVP.

## 11. Validation, reliability, and failure handling

| Situation | Defined response |
|---|---|
| Invalid feature, NaN, unexpected field or dimension | Reject with field-specific validation error |
| Duplicate identical event | Return existing status; no repeated prediction, learning, or budget charge |
| Duplicate conflicting event or label | Reject and audit conflict |
| Label before event processing | Persist pending join; apply once prediction exists |
| Missing/unavailable labels | Continue predictions with limited-observability status; no fabricated scores |
| Monitoring budget exhausted | Stop requests; mark monitoring coverage unavailable |
| Candidate timeout or worse comparison | Retain active model and record reason |
| Active model failure | Try last known valid version; otherwise return prediction unavailable |
| SQLite unavailable | Stop durable acceptance; no false 202 acknowledgements |
| Queue full | Backpressure response; no silent loss |
| Process failure | MVP marks interrupted runs and restarts reproducible simulations from their seed; checkpoint continuation is a production extension |
| WebSocket drop | Reconnect and retrieve current snapshot; lossless cursor replay deferred |
| Exact-mode assumption violation | Withdraw applicable guarantee; reject unsupported inputs |

Production checkpoint design records model state, run RNG state, label budget, detector state, pending labels, and last applied log sequence. Its recovery must avoid double learning and duplicate side effects, but that continuation mechanism is design-only for the hackathon MVP. MVP model mutations are serialized and benchmark jobs cannot share live mutable model instances. Saved input records and deterministic seed replay remain available; exact crash continuation is not claimed.

Meaningful MVP verification: labeled future data never enters past predictions; full seeded replay reproduces decisions; duplicates do not change counts; delayed labels retain correct model attribution; random monitoring remains independent; promotion uses only predictions recorded before evaluation labels; hidden truth never reaches the engine; backpressure is bounded; interrupted runs are accurately marked. Exact checkpoint continuation and lossless browser replay are production tests, not claimed MVP checks.

## 12. Security and privacy

Local demonstration binds to localhost and needs no login. A remotely accessible deployment requires authenticated operator controls and API credentials for ingestion/label submission, TLS, explicit CORS/origin rules, WebSocket authorization, rate limits, run ownership checks, body-size limits, and audit records. Keep credentials out of client code and logs.

Treat label submissions as privileged input because poisoning can manipulate adaptation. Log provenance; conflicting labels do not overwrite silently. Do not load user-supplied serialized Python models. Exports use server-created filenames and validated run access. Collect numerical features without personal identifiers for the MVP; field deployments require organization-specific retention, access, and sensitive-data policies.

## 13. Evaluation and evidence

Baselines: frozen model; continuously updated same learner; periodic reset/retraining; full DriftShield. Optional adaptive-tree baseline follows after the core comparison works. All receive identical events and authorized labels, with each method's label expenditure reported. An oracle using true boundaries is explicitly an unequal-information reference.

Tune on development seeds/schedules; evaluate on held-out seeds/schedules. Pilot with five seeds; increase to 30 when runtime permits. No '30 seeds' requirement is invented from the hackathon. Report run variation and intervals appropriate to the statistic.

Metrics: rolling and cumulative classification error; detection precision/recall with predeclared matching windows; false alarms per 10,000 events; detection delay in stream events, labeled observations, and time; recovery to a predefined absolute error target sustained over a specified window; labels requested/received; p50/p95/p99 latency; throughput; backlog; peak memory; missing-label coverage. Report unrecovered and missed cases rather than discarding them. Gradual drift uses annotated transition intervals.

The synthetic evaluator may score all predictions using hidden labels while the engine receives only authorized labels. For real streams, random-channel error estimates require appropriate sampling and delay assumptions. Do not compute full-stream accuracy from only uncertainty-selected labels.

Theory Lab: repeat independent rare-region trials at specified p, q, and D; compare empirical miss frequencies with (1-qp)^D using binomial intervals. Detection time is geometrically distributed in that experiment. A 'match' means statistically compatible results, not exact equality of measured curves. Show finite-domain full audit and an unqueried-point counterexample. Keep proof status and assumptions visible.

## 14. Deployment and scale path

Hackathon: React static build served with the backend or separately; one FastAPI service; SQLite database and trusted model files on persistent local storage; documented environment and pinned tested dependencies. Offline numerical simulation is the mandatory demonstration route. A clearly labeled saved replay is a fallback.

Optional hosted demo: static frontend, Python service with persistent process/WebSocket support, persistent disk or PostgreSQL, authenticated controls, and secrets configured server-side. Verify provider capabilities when deploying; do not assume free-tier uptime or ephemeral disk persistence. Docker packaging follows a working local application, not before the ML/evaluation core.

Production evolution: durable broker, one owner per partition/run, PostgreSQL, object storage, worker quotas, backups, authenticated tenant separation, and observable queue lag. This is an extension path, not a claim that the MVP is already horizontally scalable.

## 15. Implementation order and completion gates

| Stage | Work | Completion gate |
|---|---|---|
| 1 | Formal protocol, assumptions, proofs | Proof statements agree with experiment protocols |
| 2 | Rare-region Theory Lab | Repeated trial estimates compatible with exact probabilities |
| 3 | Simulator and evaluator | Deterministic seeds; hidden labels isolated; chronological scoring |
| 4 | Baselines and label channels | Equal-budget comparisons; no selective-label metric leakage |
| 5 | Monitoring and candidate lifecycle | Training/evaluation separation; reproducible decisions |
| 6 | API, SQLite, reliability | Basic event deduplication, label joins, bounded queues, seeded replay verified |
| 7 | Dashboard and incidents | Controls and displayed states reflect actual backend state |
| 8 | Adversarial and failure experiments | Limits and failures visible; no invented successes |
| 9 | Held-out evaluation | Metrics, configurations, seeds, and hardware recorded |
| 10 | Packaging and presentation | Offline run, labeled replay, proofs, and benchmark report ready |

Exact hackathon duration, team size, submission format, organizer meaning of 'recursive', and real data access remain unspecified. Do not promise a fixed timeline or judging score. Prioritize stages 1–5 and a minimal live view if time is tight.

Future improvements: validated concept memory; calibrated risk scores; noise-aware sequential testing with a complete analysis; carefully analyzed adaptive monitoring; multiclass and nonlinear streams; public/real integrations; operator-approved model promotion; resource-isolated workers. A weak-confidence score or cached model never substitutes for a proof.

## 16. Differentiator and presentation claim

The standout feature is a shared experiment interface with two explicitly separate detector tracks. The Theory Lab uses the known-rule, noiseless first-disagreement detector from T4. The practical product uses ADWIN on the possibly nonzero loss of a learned classifier. Judges vary information availability and drift difficulty, inspect each track's timeline and label costs, and see which assumptions support which bound. Shared visualization does not transfer the idealized detector's guarantees to ADWIN or logistic regression.

Submission claim: 'DriftShield establishes information limits for perfect adaptation under arbitrary drift, proves matching detection and finite-domain adaptation bounds in defined settings, and evaluates a reliable online monitoring and recovery engine under controlled adversarial streams.'

Final deliverables: working engine and dashboard; formal proof document; assumption/guarantee table; runnable seeded scenarios; held-out benchmark report; event/API specification; recovery checks; offline launch instructions; and a clearly labeled replay fallback. None are claimed implemented at this design stage.

## 17. Review of the additional LLM proposals

| Proposal | Useful contribution | Correction or exclusion |
|---|---|---|
| ChatGPT attachment | Explicit protocol, finite-concept separation idea, theory status and label accounting | Cannot automatically determine universal identifiability from observed data; illustrative confidence numbers and zero-error badges are not evidence |
| Gemini | Margin-based classifiers, active querying, hypothesis tracking | Perceptron R^2/gamma^2 is a mistake bound, not finite total queries guaranteeing zero population risk; finite epsilon bisection rates do not imply finite exact identification |
| Grok | Strong theoretical focus, small reproducible engine, isolation of hidden truth | A failure to detect does not certify that a stream is outside a class; finite VC dimension alone does not ensure exact finite-sample recovery |
| Perplexity | Careful definitions, distinctions between empirical and population error, reproducible evaluation | 'Largest meaningful class' is not a proved maximality result; select specific characterized classes rather than claiming maximality |
| Claude | Champion/challenger lifecycle, explicit adversaries, theory overlay, compact deployment | Universal TV-distance inverse-square detection claim, unqualified switching-regret bounds, and unlabeled ensemble fallback are unsupported for this protocol |

### Specific mathematical corrections

Claude's total-variation claim is not a universal lower bound for every pair of distributions. For example, no-drift labels can be constantly 0 while the changed law produces label 1 with probability Delta. TV distance is Delta; the first 1 identifies change with zero false alarms, with miss probability (1-Delta)^m and order ln(1/delta)/Delta samples. Other noisy overlapping families can exhibit inverse-square scaling. The statistical family must be specified.

A positive-alpha sequential false-alarm bound is not zero false alarms. Ville's inequality requires a valid nonnegative supermartingale (or properly constructed e-process) under the null. Writing an arbitrary product of feature scores does not establish that condition, and exchangeability alone does not make the proposed product valid. Familywise false-alarm probability and false discovery rate are different quantities.

Perceptron convergence on a separable sequence bounds mistakes when correct labels are available for updates. It does not tell the learner that all possible future mistakes have been exhausted after a particular finite sample, bound every label it must inspect, or turn zero training error into zero population risk. A geometric parameter movement also need not imply positive disagreement mass under the actual input distribution.

Covariate shift need not alter the Bayes decision rule, but can change deployed-model risk and approximation requirements by emphasizing new regions. Do not state that it never requires adaptation.

Standard switching-expert regret concerns a defined finite expert set, loss protocol, and feedback model. It does not prove immediate adaptation to arbitrary new concepts or provide a label-free fallback. Dynamic regret is omitted from the MVP rather than displayed against an unspecified oracle.

Some theoretical assumptions can be controlled in simulation, others can be supplied as a deployment contract, and many cannot be verified from finite data. UI fields use 'controlled in this experiment', 'assumed', 'observed violation', or 'unknown'; no automatic global 'guarantee valid' classifier is promised.

### Optional stronger finite-concept theorem

For a known finite H, a fixed noiseless target h* in H, iid post-change labeled samples from a fixed D, and separation Pr_D[h(X)!=h*(X)]>=gamma for every competing h, version-space elimination leaves only h* with probability at least 1-delta when:

    m >= ceil( ln((|H|-1)/delta) / [-ln(1-gamma)] )

for |H|>=2 and 0<gamma<1. Proof: each competitor survives m labels with probability at most (1-gamma)^m; union-bound over competitors. Handle gamma=1 separately (one label eliminates every competitor). This is an identification upper bound, not a claimed matching lower bound for every H. On successful identification, risk is exactly zero while the target stays fixed, but the success probability is less than one. A singleton version space based on corrupted or wrong-regime labels need not contain the true target.

This can extend Theory Lab after the mandatory matching-bound experiments work. It does not replace them or become a claim about logistic regression.

### Label accounting and repeated guarantees

Record labels used for detection, candidate training, and candidate evaluation; count each unique acquired label once in total cost even when it has multiple uses. The engine does not know exact 'labels since true drift' on a real stream: show labels since alert, with evaluator-only true-boundary costs in synthetic benchmarks.

For repeated finite-probability experiments, per-change guarantees do not imply an unchanged lifetime guarantee. A finite K-run family can allocate delta/K to each run; an unbounded sequence requires a summable error-budget allocation and the corresponding assumptions per episode. We do not claim the practical detector implements that analysis.

## 18. Verified primary references

- River ADWIN documentation: https://riverml.xyz/dev/api/drift/ADWIN/ — implementation, configurable checking frequency and windows. Does not establish our controller's global false-alarm rate.
- Bifet and Gavalda, Learning from Time-Changing Data with Adaptive Windowing: https://www.cs.upc.edu/~gavalda/papers/adwin06.pdf — adaptive-window detection and conditional statistical analysis.
- Berkeley consistency/PAC notes: https://people.eecs.berkeley.edu/~nika/courses/cs272/f25/02-consistency-pac.pdf — finite realizable-class consistent-learning bound and iid assumptions.
- Hanneke, The Optimal Sample Complexity of PAC Learning, JMLR 2016: https://jmlr.org/papers/v17/15-389.html and https://www.jmlr.org/papers/volume17/15-389/15-389.pdf — direct classical realizable PAC reference; the optimal construction is not our deployed learner. The paper also discusses the earlier Blumer et al. bounds.
- Blumer, Ehrenfeucht, Haussler, and Warmuth, Learnability and the Vapnik-Chervonenkis Dimension, JACM 1989, DOI 10.1145/76359.76371 — historical reference; use the verified discussion in Hanneke for the earlier logarithmic-factor upper bound rather than pretending the original full paper was independently checked here.
- SciPy binomtest documentation: https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binomtest.html — exact binomial test implementation; the paired-test model assumptions must still be justified.
- Arunachalam and de Wolf, Optimal Quantum Sample Complexity of Learning Algorithms, JMLR 2018: https://jmlr.csail.mit.edu/papers/v19/18-195.html — abstract states the classical realizable and agnostic VC sample-complexity rates.
- Cornell perceptron lecture: https://www.cs.cornell.edu/courses/cs4780/2017sp/lectures/lecturenote03.html — margin-based mistake bound; does not supply the claimed universal finite-query zero-risk result.

The elementary impossibility and matching-bound constructions above must be written out and checked in the proof deliverable. They are not claimed as new research discoveries. Product differentiation comes from the implementation and transparent evidence, not claiming novelty for established information limits.


## 19. MVP versus production scope

| Capability | Hackathon MVP | Production design only |
|---|---|---|
| Event identity | Unique run/event keys and simple deduplication | Distributed idempotency and cross-worker guarantees |
| Persistence | SQLite records, saved configuration, model artifacts | Backups, shared database, retention automation |
| Restart | Mark interrupted; rerun simulation from seed | Atomic checkpoints and exact continuation |
| Live reconnect | Current-state snapshot | Durable cursor replay |
| Benchmarks | Bounded in-process job with progress; interrupted jobs marked | Durable broker and restartable worker queue |
| Access | Localhost-only demonstration | Remote operator authentication, tenant roles, audit policy |
| Security if publicly hosted | Token-protected controls, TLS, limits, origin rules required | Full enterprise identity and tenant separation |
| Promotion | Frozen paired evaluation and logged decision | Dependence-aware/sequential policy with completed analysis |

A full production capability cannot be advertised as built merely because its design is documented. Basic deduplication, label integrity, bounded queues, and honest error states remain MVP requirements. The lean scope is intended to preserve the core research and live demonstration.

Terminology: interpret the organizer's 'recursive' as recurring A -> B -> A for the current plan, explicitly pending organizer confirmation. No organizer contact has been made or authorized.

## 20. Judge summary — proposed submission

**DriftShield: online model monitoring and recovery with visible information limits.**

A classifier can become unreliable when its labeling relationship changes, while the labels needed to diagnose and repair it are limited or delayed. Problem 7 demands perfect detection and instantaneous zero-error adaptation under arbitrary drift, but explicitly permits an impossibility result. Our submission takes that route and pairs it with a practical engineering prototype.

**Three headline theoretical contributions:** (1) an indistinguishability argument showing why universally correct detection/adaptation is impossible without distinguishing information; (2) a matching rare-region detection result, with miss probability (1-qp)^D under a known noiseless old rule and random labels; (3) a tight N-query result for exact adaptation on a known finite domain with a label oracle. These are elementary constructions presented precisely, not claims of novel learning theory.

**Product:** a numerical streaming classifier, separate monitoring/training label channels, evidence-based alerts, a candidate replacement evaluated against the deployed model, and an auditable live dashboard. The idealized theorem detector and the practical ADWIN detector are visibly separate.

**Live demonstration:** unchanged-feature label flip; rare-region stealth; abrupt and recurring changes; delayed labels; and a past-dependent adversary choosing a new boundary before the next prediction. Theory Lab compares repeated measurements with exact probabilities and uncertainty intervals. Practical benchmarks report detection delay, error, recovery, label cost, and false promotions against equal-budget baselines.

**Feasibility:** CPU-based Python/FastAPI/River, React/TypeScript, SQLite, and offline seeded experiments. No external AI API or GPU is needed. The design includes bounded queues, event validation, delayed-label joins, and an explicit interrupted-run state.

**Headline claim:** DriftShield proves limits of universal perfect adaptation, establishes tight guarantees in defined settings, and demonstrates measurable online recovery without extending those guarantees beyond their assumptions.

This summary describes the proposed work. The product, proofs, and benchmark results must be completed and verified before presentation as a finished submission.

## 21. First-pass proof document

Draft status: elementary proof sketches expanded into statements and arguments. Assumptions and quantifiers are explicit below; this draft is not an external peer review or a completed implementation verification.

### P1 / T1 — feature-only indistinguishability

Let features X_1,...,X_D be iid Uniform[0,1] in two worlds. Their shared past is generated by f0(x)=1[x>1/2]. At a potential boundary, world W0 continues f0; world W1 switches to f1(x)=1-f0(x). The detector sees only the feature sequence and its own independent random seed.

Its observed input law is identical in both worlds. Therefore the probability of an alert by D is identical. If that probability is zero under W0, it is zero under W1; it cannot have both zero false alarms and certain finite-deadline detection. More generally, if false-alarm probability by D is at most alpha, detection probability by D is at most alpha in this construction. This proves impossibility for this observation channel, not for labeled detection.

### P2 / T3 — first-prediction information lower bound

Fix an observed past and the first post-boundary input x. Consider two allowed new concepts that give labels 0 and 1 respectively at x, with no new feedback disclosed before the prediction. Both worlds supply identical evidence. Let r be the learner's probability of predicting 1, conditioned on that evidence.

Its conditional error is r in world W0 and 1-r in world W1. Thus max(r,1-r)>=1/2. For a deterministic learner r is 0 or 1, so one world's error is 1. A uniform zero-error guarantee for the first prediction is impossible. If the new input distribution concentrates on x, this is also a risk lower bound. The world may be selected knowing the algorithm, without inspecting its current realized random prediction.

### P3 / T4 — rare-region matching lower and upper bounds

Fix deterministic f0,f1 and a feature law mu. Let A={x:f0(x)!=f1(x)} have mu(A)=p. Each post-boundary X_t is independently mu-distributed; independently, Q_t is Bernoulli(q). Only labels with Q_t=1 are revealed, immediately. The same feature law and query process hold in the no-change world, with labels f0. There are no other concept-revealing observations.

Let E_D be the event that no t<=D has both X_t in A and Q_t=1. Independence gives Pr(E_D)=(1-qp)^D. Couple the feature sequence, query indicators, and learner random seed in both worlds. On E_D their observed histories are identical. The restriction of the changed-world observation law on E_D is dominated by the no-change law, since every disclosed label still equals f0. Consequently, a detector with zero no-change alarm probability cannot alert on E_D except on a null event. Its miss probability by D is at least Pr(E_D).

The first-disagreement detector never alerts under no change. Under f1 it alerts exactly when a labeled input in A first appears. It therefore misses precisely on E_D and attains the lower bound. Solving (1-qp)^D<=delta yields the stated ceiling formula for 0<qp<1. Degenerate cases qp=0 and qp=1 are handled separately.

This does not assume that the learner knows which region changed. It does assume exact knowledge of f0, noiseless feedback, fixed independent random sampling, and an unchanged feature law. It is a detection proof, not an adaptation theorem for the practical classifier.

### P4 / T5 — exact finite-domain N-query bound

Let X={x1,...,xN}, with N>=1. The old deterministic rule f0 is known; the fixed new target f is an arbitrary binary function on X. An oracle reveals f(x) when queried. Correctness must hold for all inputs, or equivalently for any distribution with full support on X. No other information discloses f.

Upper bound: query each xi once. Store the N answers. Compare the resulting table with f0 to decide whether any labeling-function change occurred. Lookup predicts f correctly everywhere. N queries suffice, and the result remains valid while f stays fixed.

Lower bound: suppose a deterministic algorithm stops after fewer than N distinct queries on the transcript obtained from f0. Choose an unqueried xj. The target f0 and a target f1 that differs from f0 only at xj give the same transcript. The algorithm must output the same drift decision and labeling rule in both worlds, so it cannot guarantee either exact identification or correct change/no-change decision for both.

For a randomized algorithm with fewer than N queries and probability-one guarantees, at least one point has positive probability of remaining unqueried on the f0 transcript. Choose such a point xj and couple random seeds under f0 and its one-point modification. On the positive-probability event that xj is unqueried, outputs are identical and cannot be correct in both worlds. Hence randomness does not remove the worst-case N-query requirement for sure correctness.

The lower bound concerns arbitrary labeling functions, full-domain correctness, and noiseless membership queries. Structured classes can require fewer queries. The guarantee begins after the complete audit, not during it, and covers neither feature-probability changes nor unknown additional changes during the audit.

### Rubric mapping

| Phase 1 criterion in the supplied judging sheet | Evidence in this specification |
|---|---|
| Understand and clearly define the problem | Sections 2–3 and proof draft |
| Identify target users, requirements, real-world needs | Sections 2, 4–5 |
| Plan solution and implementation | Sections 7, 15, 19 |
| Design architecture/workflow | Sections 6, 8–10 |
| Select technologies/tools/methods | Sections 6–7, 10, 14 |
| Demonstrate feasibility and innovation | Sections 13, 16, 20 |

Phase 1 is worth 25 marks in the supplied sheet. This mapping supports coverage, not a promised score.
