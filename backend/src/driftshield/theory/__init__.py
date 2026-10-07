"""Theory package for DriftShield idealized drift detection experiments."""

from driftshield.theory.finite_domain import (
    AuditQueryRecord,
    FiniteDomainAuditor,
    FiniteDomainConfig,
    FiniteDomainExperiment,
    FiniteDomainResult,
    MembershipOracle,
    ScenarioType,
)
from driftshield.theory.rare_region import (
    FirstDisagreementDetector,
    RareRegionConfig,
    RareRegionExperiment,
    RareRegionResult,
    TrialRecord,
    binomial_confidence_interval,
    conditional_expected_detection_time,
    expected_acquired_labels,
    expected_observation_time,
    min_deadline,
    theoretical_miss_probability,
    uncensored_expected_detection_time,
)

__all__ = [
    "AuditQueryRecord",
    "FiniteDomainAuditor",
    "FiniteDomainConfig",
    "FiniteDomainExperiment",
    "FiniteDomainResult",
    "FirstDisagreementDetector",
    "MembershipOracle",
    "RareRegionConfig",
    "RareRegionExperiment",
    "RareRegionResult",
    "ScenarioType",
    "TrialRecord",
    "binomial_confidence_interval",
    "conditional_expected_detection_time",
    "expected_acquired_labels",
    "expected_observation_time",
    "min_deadline",
    "theoretical_miss_probability",
    "uncensored_expected_detection_time",
]
