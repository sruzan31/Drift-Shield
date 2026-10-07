"""Theory Lab: Idealized Rare-Region Detection Experiment (T4).

Implements the idealized matching rare-region detection experiment from Section 3 (T4)
and Section 21 (P3/T4) of the DriftShield specification:
- Independent X drawn uniformly from [0, 1].
- Known old rule f0(x) = 0.
- New fixed rule f1(x) = 1 when x < p, otherwise 0.
- Independent random labeling probability q per event.
- Immediate noiseless labels.
- Zero-false-alarm alert at the first disclosed disagreement with f0.
- Evaluator / Detector isolation: detector receives features and authorized labels only;
  unqueried labels and the changed region p are evaluator-only.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import statistics
from typing import Any, Callable, List, Optional, Tuple

import numpy as np
from pydantic import BaseModel, ConfigDict, Field


# =====================================================================
# Analytical Math Functions
# =====================================================================

def theoretical_miss_probability(p: float, q: float, D: int) -> float:
    """Calculate theoretical missed-detection probability after D events.

    Formula: (1 - q*p)^D.

    Boundary cases:
    - D == 0: 1.0 (no events observed, miss is certain).
    - q*p == 0: 1.0 (no disagreement can ever be disclosed).
    - q*p == 1: 0.0 for D >= 1, 1.0 for D == 0.
    """
    if D < 0:
        raise ValueError(f"Observation deadline D must be non-negative, got {D}")
    if not (0.0 <= p <= 1.0):
        raise ValueError(f"Disagreement mass p must be in [0, 1], got {p}")
    if not (0.0 <= q <= 1.0):
        raise ValueError(f"Labeling probability q must be in [0, 1], got {q}")

    if D == 0:
        return 1.0

    qp = q * p
    if qp <= 0.0:
        return 1.0
    if qp >= 1.0:
        return 0.0

    # Numerically stable calculation for (1 - qp)^D:
    # math.log1p(-qp) accurately computes ln(1 - qp) even for small qp
    log_miss = D * math.log1p(-qp)
    return math.exp(log_miss)


def min_deadline(p: float, q: float, delta: float) -> Optional[int]:
    """Calculate minimum observation deadline D* to achieve miss probability <= delta.

    Formula for 0 < q*p < 1:
        D* = ceil( ln(1/delta) / -ln(1 - q*p) )

    Returns:
    - Smallest non-negative integer D such that (1 - q*p)^D <= delta.
    - None if q*p == 0 (impossible to detect, miss prob is always 1 > delta).
    - 1 if q*p == 1 for any 0 < delta < 1.
    """
    if not (0.0 <= p <= 1.0):
        raise ValueError(f"Disagreement mass p must be in [0, 1], got {p}")
    if not (0.0 <= q <= 1.0):
        raise ValueError(f"Labeling probability q must be in [0, 1], got {q}")
    if not (0.0 < delta < 1.0):
        raise ValueError(f"Target miss probability delta must be in (0, 1), got {delta}")

    qp = q * p
    if qp <= 0.0:
        return None
    if qp >= 1.0:
        return 1

    # Raw analytical ceiling: ceil(ln(delta) / ln(1 - qp))
    log_delta = math.log(delta)
    log_1_minus_qp = math.log1p(-qp)
    raw_d = math.ceil(log_delta / log_1_minus_qp)
    cand_d = max(1, int(raw_d))

    # Numerical verification loop to ensure cand_d is strictly the smallest integer satisfying target
    while cand_d > 1 and theoretical_miss_probability(p, q, cand_d - 1) <= delta:
        cand_d -= 1
    while theoretical_miss_probability(p, q, cand_d) > delta:
        cand_d += 1

    return cand_d


def uncensored_expected_detection_time(p: float, q: float) -> Optional[float]:
    """Calculate uncensored expected detection time: 1 / (q * p).

    Returns None if q * p == 0 (disclosed disagreement is impossible).
    Delays are measured as 1-based stream event counts.
    """
    if not (0.0 <= p <= 1.0):
        raise ValueError(f"Disagreement mass p must be in [0, 1], got {p}")
    if not (0.0 <= q <= 1.0):
        raise ValueError(f"Labeling probability q must be in [0, 1], got {q}")

    r = q * p
    if r <= 0.0:
        return None
    return 1.0 / r


def conditional_expected_detection_time(p: float, q: float, D: int) -> Optional[float]:
    """Calculate expected detection time conditional on detection occurring by deadline D.

    Formula for 0 < r < 1 and D >= 1 (where r = q * p):
        E[T | T <= D] = 1/r - (D * (1 - r)^D) / (1 - (1 - r)^D)

    Returns:
    - None if r == 0 or D == 0 (no detection is possible, conditional distribution undefined).
    - 1.0 if r == 1.0 and D >= 1.
    - Delays are measured as 1-based stream event counts.
    """
    if D < 0:
        raise ValueError(f"Observation deadline D must be non-negative, got {D}")
    if not (0.0 <= p <= 1.0):
        raise ValueError(f"Disagreement mass p must be in [0, 1], got {p}")
    if not (0.0 <= q <= 1.0):
        raise ValueError(f"Labeling probability q must be in [0, 1], got {q}")

    if D == 0:
        return None

    r = q * p
    if r <= 0.0:
        return None
    if r >= 1.0:
        return 1.0

    miss_prob = theoretical_miss_probability(p, q, D)
    detect_prob = 1.0 - miss_prob
    if detect_prob <= 0.0:
        return None

    return (1.0 / r) - (D * miss_prob / detect_prob)


def expected_observation_time(p: float, q: float, D: int) -> float:
    """Calculate expected observation time until detection or deadline D: min(T, D).

    Formula for r > 0 (where r = q * p):
        E[min(T, D)] = (1 - (1 - r)^D) / r

    For r == 0:
        E[min(T, D)] = D
    """
    if D < 0:
        raise ValueError(f"Observation deadline D must be non-negative, got {D}")
    if not (0.0 <= p <= 1.0):
        raise ValueError(f"Disagreement mass p must be in [0, 1], got {p}")
    if not (0.0 <= q <= 1.0):
        raise ValueError(f"Labeling probability q must be in [0, 1], got {q}")

    if D == 0:
        return 0.0

    r = q * p
    if r <= 0.0:
        return float(D)
    if r >= 1.0:
        return 1.0

    detect_prob = 1.0 - theoretical_miss_probability(p, q, D)
    return detect_prob / r


def expected_acquired_labels(p: float, q: float, D: int) -> float:
    """Calculate expected acquired labels until detection or deadline D.

    Formula for r > 0 (where r = q * p):
        E[Labels] = q * E[min(T, D)] = q * (1 - (1 - r)^D) / r = (1 - (1 - r)^D) / p

    For r == 0:
        E[Labels] = q * D
    """
    if D < 0:
        raise ValueError(f"Observation deadline D must be non-negative, got {D}")
    if not (0.0 <= p <= 1.0):
        raise ValueError(f"Disagreement mass p must be in [0, 1], got {p}")
    if not (0.0 <= q <= 1.0):
        raise ValueError(f"Labeling probability q must be in [0, 1], got {q}")

    if D == 0 or q == 0.0:
        return 0.0

    return q * expected_observation_time(p, q, D)


def binomial_confidence_interval(
    k: int,
    n: int,
    confidence: float = 0.95,
) -> Tuple[float, float]:
    """Calculate Wilson score interval for binomial proportion k / n.

    Handles boundary proportions 0 and 1 cleanly and maintains valid coverage.
    """
    if n <= 0:
        return 0.0, 1.0
    if not (0.0 < confidence < 1.0):
        raise ValueError(f"Confidence level must be in (0, 1), got {confidence}")

    alpha = 1.0 - confidence
    z = statistics.NormalDist().inv_cdf(1.0 - alpha / 2.0)
    p_hat = k / n

    z2 = z * z
    denominator = 1.0 + z2 / n
    center_adj = p_hat + z2 / (2.0 * n)
    half_width = z * math.sqrt((p_hat * (1.0 - p_hat) / n) + (z2 / (4.0 * n * n)))

    lower = max(0.0, (center_adj - half_width) / denominator)
    upper = min(1.0, (center_adj + half_width) / denominator)
    return lower, upper


# =====================================================================
# Configuration & Result Models
# =====================================================================

class RareRegionConfig(BaseModel):
    """Configuration for the T4 Rare-Region Experiment."""
    model_config = ConfigDict(frozen=True)

    p: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="Disagreement mass / rare region size",
    )
    q: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
        description="Independent random label query probability per event",
    )
    deadline: int = Field(
        default=100,
        ge=0,
        description="Observation deadline D in stream events",
    )
    delta: float = Field(
        default=0.05,
        gt=0.0,
        lt=1.0,
        description="Target miss probability",
    )
    trials: int = Field(
        default=10000,
        ge=1,
        description="Number of independent trials",
    )
    seed: int = Field(
        default=42,
        description="Master seed for feature generation",
    )
    query_seed: Optional[int] = Field(
        default=None,
        description="Optional distinct seed for query RNG stream",
    )
    no_change: bool = Field(
        default=False,
        description="If True, f1(x) = f0(x) = 0 (tests zero false-alarm rate)",
    )


class TrialRecord(BaseModel):
    """Execution record for a single independent trial."""
    model_config = ConfigDict(frozen=True)

    trial_index: int
    detected: bool
    detection_delay: Optional[int] = None  # 1-based stream event count upon alert
    labels_acquired: int
    total_events: int
    queried_disagreements: int
    unqueried_disagreements: int


class RareRegionResult(BaseModel):
    """Consolidated summary and trial results of the rare-region experiment."""
    model_config = ConfigDict(frozen=True)

    config: RareRegionConfig
    theoretical_miss_probability: float
    theoretical_detection_probability: float
    min_deadline: Optional[int] = None

    # Theoretical time and acquisition metrics
    uncensored_expected_detection_time: Optional[float] = None
    conditional_expected_detection_time: Optional[float] = None
    expected_observation_time: float = 0.0
    expected_acquired_labels: float = 0.0

    # Backwards-compatibility aliases
    expected_stream_events_to_detection: Optional[float] = None
    expected_labels_to_detection: Optional[float] = None

    trials_count: int
    empirical_miss_count: int
    empirical_miss_frequency: float
    empirical_detection_count: int
    empirical_detection_frequency: float
    ci_lower: float
    ci_upper: float
    confidence_level: float = 0.95

    mean_detection_delay: Optional[float] = None  # 1-based stream event counts
    mean_observation_time: float = 0.0
    mean_labels_acquired: float = 0.0
    total_labels_acquired: int = 0
    trials: List[TrialRecord] = Field(default_factory=list)


# =====================================================================
# Isolated First-Disagreement Detector
# =====================================================================

class FirstDisagreementDetector:
    """Isolated T4 Detector.

    Receives features and authorized labels only.
    Knows the reference rule f0(x) = 0.
    Alerts at the very first disclosed disagreement with f0.
    Has zero false-alarm probability under f0.
    """

    def __init__(self, f0: Optional[Callable[[float], int]] = None) -> None:
        self._f0 = f0 if f0 is not None else (lambda x: 0)
        self._alerted: bool = False
        self._alert_step: Optional[int] = None

    @property
    def alerted(self) -> bool:
        return self._alerted

    @property
    def alert_step(self) -> Optional[int]:
        return self._alert_step

    def observe(self, event_sequence: int, x: float, label: Optional[int] = None) -> bool:
        """Process incoming stream event and optional authorized label.

        Returns True if an alert is triggered at this event (1-based sequence).
        """
        if self._alerted:
            return False

        if label is not None:
            expected = self._f0(x)
            if label != expected:
                self._alerted = True
                self._alert_step = event_sequence
                return True

        return False


# =====================================================================
# Experiment Runner
# =====================================================================

class RareRegionExperiment:
    """Executes independent trials for the T4 Rare-Region Detection Experiment."""

    def __init__(self, config: RareRegionConfig) -> None:
        self.config = config
        self.effective_query_seed = (
            config.query_seed if config.query_seed is not None else (config.seed + 1_000_000)
        )

    def run_trial(
        self,
        trial_index: int,
        feature_rng: np.random.Generator,
        query_rng: np.random.Generator,
    ) -> TrialRecord:
        """Run a single trial up to deadline D or first alert."""
        detector = FirstDisagreementDetector()

        p = self.config.p
        q = self.config.q
        D = self.config.deadline
        no_change = self.config.no_change

        labels_acquired = 0
        queried_disagreements = 0
        unqueried_disagreements = 0
        total_events = 0
        detected = False
        detection_delay: Optional[int] = None

        for t in range(1, D + 1):
            total_events = t
            # Feature drawn uniformly from [0, 1]
            x_t = float(feature_rng.uniform(0.0, 1.0))

            # Query decision drawn independently from Bernoulli(q)
            u_t = float(query_rng.uniform(0.0, 1.0))
            is_queried = (u_t < q) if q > 0.0 else False

            # Evaluator-only hidden label
            if no_change:
                y_t = 0
                is_disagreement = False
            else:
                y_t = 1 if (x_t < p) else 0
                is_disagreement = (y_t == 1)

            if is_disagreement:
                if is_queried:
                    queried_disagreements += 1
                else:
                    unqueried_disagreements += 1

            # Authorized label delivered to detector
            if is_queried:
                labels_acquired += 1
                authorized_label: Optional[int] = y_t
            else:
                authorized_label = None

            # Detector processes event (1-based count t)
            alert_now = detector.observe(event_sequence=t, x=x_t, label=authorized_label)
            if alert_now:
                detected = True
                detection_delay = t
                break

        return TrialRecord(
            trial_index=trial_index,
            detected=detected,
            detection_delay=detection_delay,
            labels_acquired=labels_acquired,
            total_events=total_events,
            queried_disagreements=queried_disagreements,
            unqueried_disagreements=unqueried_disagreements,
        )

    def run(self) -> RareRegionResult:
        """Run all independent trials and compute theoretical and empirical metrics."""
        feature_rng = np.random.default_rng(self.config.seed)
        query_rng = np.random.default_rng(self.effective_query_seed)

        trials: List[TrialRecord] = []
        for i in range(self.config.trials):
            record = self.run_trial(
                trial_index=i,
                feature_rng=feature_rng,
                query_rng=query_rng,
            )
            trials.append(record)

        # Theoretical metrics
        p = self.config.p if not self.config.no_change else 0.0
        q = self.config.q
        D = self.config.deadline
        delta = self.config.delta

        theo_miss = theoretical_miss_probability(p, q, D)
        theo_detect = 1.0 - theo_miss
        m_deadline = min_deadline(p, q, delta) if p > 0 and q > 0 else None

        uncensored_t = uncensored_expected_detection_time(p, q)
        cond_t = conditional_expected_detection_time(p, q, D)
        exp_obs = expected_observation_time(p, q, D)
        exp_lbls = expected_acquired_labels(p, q, D)

        # Empirical metrics
        n = len(trials)
        detection_count = sum(1 for tr in trials if tr.detected)
        miss_count = n - detection_count
        empirical_miss_freq = miss_count / n
        empirical_detect_freq = detection_count / n

        ci_lower, ci_upper = binomial_confidence_interval(miss_count, n, confidence=0.95)

        detected_delays = [tr.detection_delay for tr in trials if tr.detection_delay is not None]
        mean_delay = float(np.mean(detected_delays)) if detected_delays else None

        observed_times = [tr.total_events for tr in trials]
        mean_obs_time = float(np.mean(observed_times)) if observed_times else 0.0

        total_labels = sum(tr.labels_acquired for tr in trials)
        mean_labels = total_labels / n

        return RareRegionResult(
            config=self.config,
            theoretical_miss_probability=theo_miss,
            theoretical_detection_probability=theo_detect,
            min_deadline=m_deadline,
            uncensored_expected_detection_time=uncensored_t,
            conditional_expected_detection_time=cond_t,
            expected_observation_time=exp_obs,
            expected_acquired_labels=exp_lbls,
            expected_stream_events_to_detection=uncensored_t,
            expected_labels_to_detection=(1.0 / p) if p > 0 else None,
            trials_count=n,
            empirical_miss_count=miss_count,
            empirical_miss_frequency=empirical_miss_freq,
            empirical_detection_count=detection_count,
            empirical_detection_frequency=empirical_detect_freq,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            confidence_level=0.95,
            mean_detection_delay=mean_delay,
            mean_observation_time=mean_obs_time,
            mean_labels_acquired=mean_labels,
            total_labels_acquired=total_labels,
            trials=trials,
        )

    def export(self, result: RareRegionResult, output_dir: Path) -> Tuple[Path, Path]:
        """Export trials.csv and summary.json to output directory."""
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / "trials.csv"
        json_path = output_dir / "summary.json"

        # 1. Export CSV
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "trial_index",
                "detected",
                "detection_delay",
                "labels_acquired",
                "total_events",
                "queried_disagreements",
                "unqueried_disagreements",
            ])
            for tr in result.trials:
                writer.writerow([
                    tr.trial_index,
                    tr.detected,
                    tr.detection_delay if tr.detection_delay is not None else "",
                    tr.labels_acquired,
                    tr.total_events,
                    tr.queried_disagreements,
                    tr.unqueried_disagreements,
                ])

        # 2. Export JSON Summary
        summary_dict = {
            "parameters": {
                "p": result.config.p,
                "q": result.config.q,
                "deadline": result.config.deadline,
                "delta": result.config.delta,
                "trials": result.config.trials,
                "seed": result.config.seed,
                "query_seed": result.config.query_seed,
                "no_change": result.config.no_change,
            },
            "theoretical": {
                "miss_probability": result.theoretical_miss_probability,
                "detection_probability": result.theoretical_detection_probability,
                "min_deadline_for_delta": result.min_deadline,
                "uncensored_expected_detection_time": result.uncensored_expected_detection_time,
                "conditional_expected_detection_time": result.conditional_expected_detection_time,
                "expected_observation_time": result.expected_observation_time,
                "expected_acquired_labels": result.expected_acquired_labels,
                "expected_stream_events_to_detection": result.expected_stream_events_to_detection,
                "expected_labels_to_detection": result.expected_labels_to_detection,
            },
            "empirical": {
                "trials_count": result.trials_count,
                "miss_count": result.empirical_miss_count,
                "miss_frequency": result.empirical_miss_frequency,
                "detection_count": result.empirical_detection_count,
                "detection_frequency": result.empirical_detection_frequency,
                "confidence_interval_95": [result.ci_lower, result.ci_upper],
                "mean_detection_delay": result.mean_detection_delay,
                "mean_observation_time": result.mean_observation_time,
                "mean_labels_acquired": result.mean_labels_acquired,
                "total_labels_acquired": result.total_labels_acquired,
            },
        }

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary_dict, f, indent=2)

        return csv_path, json_path
