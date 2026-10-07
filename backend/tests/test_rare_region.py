"""Unit and integration tests for T4 Rare-Region Detection Experiment."""

import json
import math
from pathlib import Path
import pytest
import numpy as np

from driftshield.theory.rare_region import (
    FirstDisagreementDetector,
    RareRegionConfig,
    RareRegionExperiment,
    RareRegionResult,
    binomial_confidence_interval,
    conditional_expected_detection_time,
    expected_acquired_labels,
    expected_observation_time,
    min_deadline,
    theoretical_miss_probability,
    uncensored_expected_detection_time,
)


# =====================================================================
# Analytical Math Tests
# =====================================================================

class TestTheoreticalMissProbability:
    def test_standard_case(self) -> None:
        p = 0.05
        q = 0.20
        D = 100
        # (1 - 0.01)^100
        expected = 0.99 ** 100
        actual = theoretical_miss_probability(p, q, D)
        assert math.isclose(actual, expected, rel_tol=1e-9)

    def test_miss_probability_at_min_deadline_299(self) -> None:
        p = 0.05
        q = 0.20
        D = 299
        actual = theoretical_miss_probability(p, q, D)
        # Matches user prompt specification 0.049536257
        assert math.isclose(actual, 0.049536257, rel_tol=1e-6)

    def test_deadline_zero(self) -> None:
        assert theoretical_miss_probability(0.05, 0.20, 0) == 1.0
        assert theoretical_miss_probability(1.0, 1.0, 0) == 1.0
        assert theoretical_miss_probability(0.0, 0.0, 0) == 1.0

    def test_zero_p_or_zero_q(self) -> None:
        assert theoretical_miss_probability(0.0, 0.5, 100) == 1.0
        assert theoretical_miss_probability(0.5, 0.0, 100) == 1.0
        assert theoretical_miss_probability(0.0, 0.0, 100) == 1.0

    def test_qp_one(self) -> None:
        assert theoretical_miss_probability(1.0, 1.0, 1) == 0.0
        assert theoretical_miss_probability(1.0, 1.0, 50) == 0.0

    def test_invalid_inputs_raise(self) -> None:
        with pytest.raises(ValueError, match="deadline"):
            theoretical_miss_probability(0.05, 0.20, -1)
        with pytest.raises(ValueError, match="Disagreement mass"):
            theoretical_miss_probability(-0.01, 0.20, 100)
        with pytest.raises(ValueError, match="Disagreement mass"):
            theoretical_miss_probability(1.05, 0.20, 100)
        with pytest.raises(ValueError, match="Labeling probability"):
            theoretical_miss_probability(0.05, -0.1, 100)
        with pytest.raises(ValueError, match="Labeling probability"):
            theoretical_miss_probability(0.05, 1.1, 100)


class TestMinDeadline:
    def test_standard_case(self) -> None:
        # p=0.05, q=0.20 -> qp=0.01. For delta=0.05, ceil(ln(20)/-ln(0.99)) = 299
        p = 0.05
        q = 0.20
        delta = 0.05
        d_star = min_deadline(p, q, delta)
        assert d_star == 299

        # Verify optimality: D=299 meets target, D=298 does not
        assert theoretical_miss_probability(p, q, 299) <= delta
        assert theoretical_miss_probability(p, q, 298) > delta

    def test_boundary_cases(self) -> None:
        # qp = 0 -> None
        assert min_deadline(0.0, 0.5, 0.05) is None
        assert min_deadline(0.5, 0.0, 0.05) is None

        # qp = 1 -> D* = 1 for any delta in (0, 1)
        assert min_deadline(1.0, 1.0, 0.01) == 1
        assert min_deadline(1.0, 1.0, 0.50) == 1

    @pytest.mark.parametrize(
        "p,q,delta",
        [
            (0.1, 0.5, 0.01),
            (0.01, 0.1, 0.10),
            (0.5, 0.8, 0.001),
            (0.02, 0.25, 0.05),
        ],
    )
    def test_optimality_across_ranges(self, p: float, q: float, delta: float) -> None:
        d_star = min_deadline(p, q, delta)
        assert d_star is not None
        assert theoretical_miss_probability(p, q, d_star) <= delta
        if d_star > 1:
            assert theoretical_miss_probability(p, q, d_star - 1) > delta

    def test_invalid_delta_raises(self) -> None:
        with pytest.raises(ValueError, match="delta"):
            min_deadline(0.05, 0.20, 0.0)
        with pytest.raises(ValueError, match="delta"):
            min_deadline(0.05, 0.20, 1.0)
        with pytest.raises(ValueError, match="delta"):
            min_deadline(0.05, 0.20, -0.05)


class TestExpectedTimesAndLabels:
    def test_values_at_p005_q020_d100(self) -> None:
        p = 0.05
        q = 0.20
        D = 100

        # Uncensored expected detection time 1 / (q*p) = 100.0
        uncensored = uncensored_expected_detection_time(p, q)
        assert uncensored is not None
        assert math.isclose(uncensored, 100.0, rel_tol=1e-9)

        # Conditional detection mean 1/r - D*(1-r)^D / (1-(1-r)^D)
        cond_mean = conditional_expected_detection_time(p, q, D)
        assert cond_mean is not None
        assert math.isclose(cond_mean, 42.26324724318385, rel_tol=1e-7)

        # Expected observation time: (1 - (1-r)^D) / r
        obs_time = expected_observation_time(p, q, D)
        assert math.isclose(obs_time, 63.39676587267706, rel_tol=1e-7)

        # Expected acquired labels: q * (1 - (1-r)^D) / r
        acq_labels = expected_acquired_labels(p, q, D)
        assert math.isclose(acq_labels, 12.679353174535413, rel_tol=1e-7)

    def test_degenerate_cases(self) -> None:
        # r = 0 (p = 0 or q = 0)
        assert uncensored_expected_detection_time(0.0, 0.2) is None
        assert uncensored_expected_detection_time(0.05, 0.0) is None
        assert conditional_expected_detection_time(0.0, 0.2, 100) is None
        assert conditional_expected_detection_time(0.05, 0.0, 100) is None
        assert expected_observation_time(0.0, 0.2, 100) == 100.0
        assert expected_acquired_labels(0.0, 0.2, 100) == 20.0
        assert expected_acquired_labels(0.05, 0.0, 100) == 0.0

        # D = 0
        assert conditional_expected_detection_time(0.05, 0.2, 0) is None
        assert expected_observation_time(0.05, 0.2, 0) == 0.0
        assert expected_acquired_labels(0.05, 0.2, 0) == 0.0

        # r = 1.0 (p = 1, q = 1)
        assert uncensored_expected_detection_time(1.0, 1.0) == 1.0
        assert conditional_expected_detection_time(1.0, 1.0, 10) == 1.0
        assert expected_observation_time(1.0, 1.0, 10) == 1.0
        assert expected_acquired_labels(1.0, 1.0, 10) == 1.0


class TestWilsonConfidenceInterval:
    def test_coverage_and_ordering(self) -> None:
        lower, upper = binomial_confidence_interval(k=3660, n=10000, confidence=0.95)
        assert 0.0 <= lower <= 0.3660 <= upper <= 1.0
        assert upper - lower < 0.03

    def test_zero_successes(self) -> None:
        lower, upper = binomial_confidence_interval(k=0, n=100, confidence=0.95)
        assert lower == 0.0
        assert 0.0 < upper < 0.05

    def test_all_successes(self) -> None:
        lower, upper = binomial_confidence_interval(k=100, n=100, confidence=0.95)
        assert 0.95 < lower < 1.0
        assert upper == 1.0

    def test_invalid_inputs(self) -> None:
        assert binomial_confidence_interval(k=0, n=0) == (0.0, 1.0)
        with pytest.raises(ValueError, match="Confidence level"):
            binomial_confidence_interval(k=5, n=10, confidence=1.5)


# =====================================================================
# Detector Tests
# =====================================================================

class TestFirstDisagreementDetector:
    def test_no_labels_never_alerts(self) -> None:
        detector = FirstDisagreementDetector()
        for t in range(1, 50):
            alert = detector.observe(event_sequence=t, x=0.01, label=None)
            assert not alert
        assert not detector.alerted
        assert detector.alert_step is None

    def test_agreement_labels_never_alert(self) -> None:
        detector = FirstDisagreementDetector()
        for t in range(1, 50):
            alert = detector.observe(event_sequence=t, x=0.5, label=0)
            assert not alert
        assert not detector.alerted

    def test_disagreement_label_triggers_alert(self) -> None:
        detector = FirstDisagreementDetector()
        assert not detector.observe(1, 0.8, label=0)
        assert not detector.observe(2, 0.02, label=None)  # unqueried disagreement
        alert = detector.observe(3, 0.02, label=1)
        assert alert
        assert detector.alerted
        assert detector.alert_step == 3  # 1-based sequence count

        # Subsequent events after alert
        assert not detector.observe(4, 0.01, label=1)
        assert detector.alert_step == 3


# =====================================================================
# Experiment Runner Integration Tests
# =====================================================================

class TestRareRegionExperiment:
    def test_no_change_zero_false_alarms(self) -> None:
        config = RareRegionConfig(
            p=0.10,
            q=0.50,
            deadline=50,
            trials=200,
            seed=123,
            no_change=True,
        )
        exp = RareRegionExperiment(config)
        res = exp.run()

        assert res.empirical_detection_count == 0
        assert res.empirical_miss_count == 200
        assert res.empirical_miss_frequency == 1.0
        assert res.mean_detection_delay is None

    def test_unlabeled_stream_never_alerts(self) -> None:
        config = RareRegionConfig(
            p=0.50,
            q=0.0,
            deadline=50,
            trials=100,
            seed=999,
        )
        exp = RareRegionExperiment(config)
        res = exp.run()

        assert res.empirical_detection_count == 0
        assert res.empirical_miss_count == 100
        assert res.total_labels_acquired == 0
        total_unqueried = sum(tr.unqueried_disagreements for tr in res.trials)
        assert total_unqueried > 0

    def test_deterministic_detection_qp1(self) -> None:
        config = RareRegionConfig(
            p=1.0,
            q=1.0,
            deadline=10,
            trials=50,
            seed=42,
        )
        exp = RareRegionExperiment(config)
        res = exp.run()

        assert res.empirical_detection_count == 50
        assert res.empirical_miss_count == 0
        assert res.mean_detection_delay == 1.0
        assert res.mean_labels_acquired == 1.0

    def test_seed_reproducibility(self) -> None:
        config1 = RareRegionConfig(p=0.05, q=0.20, deadline=100, trials=100, seed=42)
        config2 = RareRegionConfig(p=0.05, q=0.20, deadline=100, trials=100, seed=42)

        res1 = RareRegionExperiment(config1).run()
        res2 = RareRegionExperiment(config2).run()

        assert res1.empirical_miss_count == res2.empirical_miss_count
        assert res1.total_labels_acquired == res2.total_labels_acquired
        for t1, t2 in zip(res1.trials, res2.trials):
            assert t1.model_dump() == t2.model_dump()

    def test_query_rng_independence(self) -> None:
        feature_seed = 42
        c1 = RareRegionConfig(p=0.05, q=0.20, deadline=100, trials=50, seed=feature_seed, query_seed=111)
        c2 = RareRegionConfig(p=0.05, q=0.20, deadline=100, trials=50, seed=feature_seed, query_seed=999)

        r1 = RareRegionExperiment(c1).run()
        r2 = RareRegionExperiment(c2).run()

        labels1 = [t.labels_acquired for t in r1.trials]
        labels2 = [t.labels_acquired for t in r2.trials]
        assert labels1 != labels2

    def test_export_and_summary_consistency(self, tmp_path: Path) -> None:
        config = RareRegionConfig(p=0.05, q=0.20, deadline=100, trials=100, seed=42)
        exp = RareRegionExperiment(config)
        res = exp.run()

        csv_path, json_path = exp.export(res, tmp_path)
        assert csv_path.exists()
        assert json_path.exists()

        with open(json_path, "r", encoding="utf-8") as f:
            summary_data = json.load(f)

        assert summary_data["empirical"]["trials_count"] == 100
        assert summary_data["empirical"]["miss_count"] == res.empirical_miss_count
        assert summary_data["theoretical"]["min_deadline_for_delta"] == 299
        assert "uncensored_expected_detection_time" in summary_data["theoretical"]
        assert "conditional_expected_detection_time" in summary_data["theoretical"]
        assert "expected_observation_time" in summary_data["theoretical"]
        assert "expected_acquired_labels" in summary_data["theoretical"]

        with open(csv_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 101
