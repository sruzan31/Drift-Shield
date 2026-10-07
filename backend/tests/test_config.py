"""
Tests for driftshield.config
"""

import pytest
from pydantic import ValidationError

from driftshield.config import DriftShieldConfig, LabelConfig, StreamConfig


class TestStreamConfig:
    def test_defaults_valid(self):
        cfg = StreamConfig()
        assert cfg.scenario == "stationary"
        assert cfg.n_events == 2000
        assert cfg.seed == 42

    def test_abrupt_scenario_valid(self):
        cfg = StreamConfig(scenario="abrupt", n_events=500, drift_start_sequence=250)
        assert cfg.drift_start_sequence == 250

    def test_abrupt_drift_at_or_beyond_n_events_raises(self):
        with pytest.raises(ValidationError, match="drift_start_sequence"):
            StreamConfig(scenario="abrupt", n_events=500, drift_start_sequence=500)

    def test_invalid_scenario_raises(self):
        with pytest.raises(ValidationError):
            StreamConfig(scenario="unsupported_drift")

    def test_negative_n_events_raises(self):
        with pytest.raises(ValidationError):
            StreamConfig(n_events=1)

    def test_zero_noise_raises(self):
        with pytest.raises(ValidationError):
            StreamConfig(noise_std=0.0)


class TestLabelConfig:
    def test_defaults_valid(self):
        cfg = LabelConfig()
        assert cfg.warmup_size == 200
        assert cfg.label_budget == 300

    def test_zero_budget_valid(self):
        cfg = LabelConfig(label_budget=0)
        assert cfg.label_budget == 0

    def test_monitor_rate_out_of_range(self):
        with pytest.raises(ValidationError):
            LabelConfig(monitor_rate=1.5)

    def test_negative_delay_raises(self):
        with pytest.raises(ValidationError):
            LabelConfig(label_delay=-1)


class TestDriftShieldConfig:
    def test_warmup_lt_n_events(self):
        with pytest.raises(ValidationError, match="warmup_size"):
            DriftShieldConfig(
                stream=StreamConfig(n_events=100),
                labels=LabelConfig(warmup_size=100),
            )

    def test_valid_combined(self):
        cfg = DriftShieldConfig(
            stream=StreamConfig(n_events=500, scenario="abrupt", drift_start_sequence=250),
            labels=LabelConfig(warmup_size=100, label_budget=150),
        )
        assert cfg.stream.n_events == 500
        assert cfg.labels.warmup_size == 100
