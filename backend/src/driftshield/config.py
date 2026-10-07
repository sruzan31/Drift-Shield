"""
driftshield.config
==================
Validated configuration for all DriftShield Phase-1 components.

All public fields are documented; Pydantic v2 raises ValidationError on
bad inputs so callers get explicit error messages rather than silent
mis-configuration.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Sub-configs
# ---------------------------------------------------------------------------


class StreamConfig(BaseModel):
    """Parameters that control stream generation."""

    scenario: Literal[
        "stationary",
        "abrupt",
        "gradual",
        "recurring",
        "rare_region",
        "adversary",
    ] = Field(
        "stationary",
        description=(
            "stationary — no drift; "
            "abrupt — decision boundary shifts sharply at drift_start_sequence; "
            "gradual — concept mixture transitioning over gradual_window; "
            "recurring — periodic A-B-A concept switches every recurrence_interval; "
            "rare_region — subtle stealth drift affecting a small region of mass rare_region_p; "
            "adversary — adaptive adversary inspecting past margins at dwell boundaries."
        ),
    )
    n_events: int = Field(
        2000, ge=2, description="Total number of events to emit, including warm-up."
    )
    seed: int = Field(42, description="Master seed for the data-generation RNG.")
    noise_std: float = Field(
        0.4, gt=0.0, description="Gaussian noise applied to each feature."
    )
    drift_start_sequence: int = Field(
        1000,
        ge=1,
        description="Sequence index at which drift begins or first switch occurs.",
    )
    # Scenario-specific configuration
    gradual_window: int = Field(
        400,
        ge=10,
        description="Length of transition window in events for gradual drift.",
    )
    recurrence_interval: int = Field(
        500,
        ge=10,
        description="Event period between recurring concept switches.",
    )
    rare_region_p: float = Field(
        0.05,
        gt=0.0,
        le=0.5,
        description="Fraction of feature space affected by rare-region stealth drift.",
    )
    adversary_dwell: int = Field(
        300,
        ge=50,
        description="Minimum dwell interval in events between adaptive adversary rule switches.",
    )

    @model_validator(mode="after")
    def _drift_within_stream(self) -> "StreamConfig":
        if self.scenario != "stationary":
            if self.drift_start_sequence >= self.n_events:
                raise ValueError(
                    f"drift_start_sequence ({self.drift_start_sequence}) must be "
                    f"less than n_events ({self.n_events})."
                )
        return self


class LabelConfig(BaseModel):
    """Parameters controlling label acquisition and delivery."""

    warmup_size: int = Field(
        200,
        ge=10,
        description=(
            "Number of initial events used for warm-up. "
            "All warm-up labels are always acquired (they are needed to train the "
            "initial model). Warm-up predictions are excluded from evaluation."
        ),
    )
    label_budget: int = Field(
        300,
        ge=0,
        description=(
            "Maximum number of UNIQUE post-warm-up labels that may be acquired "
            "across all channels. Individual acquisitions deduplicate by event ID."
        ),
    )
    monitor_budget: Optional[int] = Field(
        None,
        ge=0,
        description=(
            "Maximum number of UNIQUE post-warm-up labels that the random-monitoring "
            "channel may acquire. If None, defaults to label_budget."
        ),
    )
    selective_budget: Optional[int] = Field(
        None,
        ge=0,
        description=(
            "Maximum number of UNIQUE post-warm-up labels that the selective "
            "(low-margin) channel may acquire. If None, defaults to label_budget."
        ),
    )
    monitor_rate: float = Field(
        0.10,
        ge=0.0,
        le=1.0,
        description=(
            "Probability that each post-warm-up event is selected for random "
            "monitoring. Applied independently per event, using the selection RNG."
        ),
    )
    low_margin_k: int = Field(
        50,
        ge=0,
        description=(
            "At each step, the k most uncertain predictions (smallest |P - 0.5|) "
            "from all unlabeled post-warm-up events so far are eligible for "
            "low-margin (selective) label acquisition."
        ),
    )
    label_delay: int = Field(
        0,
        ge=0,
        description=(
            "Fixed number of sequence steps after which an acquired label is "
            "delivered. 0 = immediate delivery. Delivery is joined by event_id."
        ),
    )
    selection_seed: int = Field(
        99,
        description=(
            "Seed for the label-selection RNG. Changing this must NOT affect "
            "generated features or hidden labels."
        ),
    )

    # ------------------------------------------------------------------
    # Derived convenience properties
    # ------------------------------------------------------------------

    @property
    def total_budget(self) -> int:
        """Upper bound on total unique post-warm-up labels that can be charged."""
        return self.label_budget

    @property
    def effective_selective_budget(self) -> int:
        if self.selective_budget is not None:
            return self.selective_budget
        if self.monitor_budget is not None:
            return max(0, self.label_budget - self.monitor_budget)
        return self.label_budget // 3

    @property
    def effective_monitor_budget(self) -> int:
        if self.monitor_budget is not None:
            return self.monitor_budget
        return max(0, self.label_budget - self.effective_selective_budget)

    @model_validator(mode="after")
    def _validate_label_config(self) -> "LabelConfig":
        return self


class MonitoringConfig(BaseModel):
    """Parameters controlling error-change monitoring via River ADWIN."""

    adwin_delta: float = Field(
        0.002,
        gt=0.0,
        lt=1.0,
        description="Confidence parameter delta for ADWIN change detection.",
    )
    adwin_clock: int = Field(
        32,
        ge=1,
        description="ADWIN clock parameter (frequency of bucket compression checks).",
    )
    adwin_max_buckets: int = Field(
        5,
        ge=1,
        description="ADWIN maximum buckets per tier.",
    )
    adwin_min_window_length: int = Field(
        5,
        ge=1,
        description="ADWIN minimum window length.",
    )
    adwin_grace_period: int = Field(
        10,
        ge=1,
        description="ADWIN grace period (minimum observations before drift can trigger).",
    )


class AdaptationConfig(BaseModel):
    """Parameters controlling candidate model training and adaptation."""

    target_training_labels: int = Field(
        200,
        ge=1,
        description="Target number of unique post-epoch labels required to train a candidate.",
    )
    cooldown_events: int = Field(
        50,
        ge=0,
        description="Minimum number of stream events after an alert before a new candidate can start.",
    )
    min_error_rate_threshold: float = Field(
        0.05,
        ge=0.0,
        le=1.0,
        description="Minimum estimated ADWIN error rate required to trigger candidate training.",
    )
    learning_rate: float = Field(
        0.01,
        gt=0.0,
        description="SGD learning rate for candidate LogisticRegression.",
    )
    l2: float = Field(
        1e-4,
        ge=0.0,
        description="L2 regularization for candidate LogisticRegression.",
    )
    evaluation_target_events: int = Field(
        500,
        ge=1,
        description="Number of fresh random-monitoring evaluation events required for paired comparison.",
    )
    min_gain_threshold: float = Field(
        0.02,
        ge=0.0,
        le=1.0,
        description="Minimum observed candidate risk gain (b-c)/n required for promotion (default: 2 percentage points).",
    )
    max_pvalue_threshold: float = Field(
        0.01,
        gt=0.0,
        le=1.0,
        description="Maximum p-value from one-sided exact binomial sign test required for promotion.",
    )
    max_comparisons: int = Field(
        5,
        ge=1,
        description="Maximum completed candidate comparisons per stream run (error budget allocation cap).",
    )
    evaluation_timeout_events: Optional[int] = Field(
        None,
        ge=1,
        description="Optional timeout in stream events after freeze before evaluation is declared INCOMPLETE.",
    )


class DriftShieldConfig(BaseModel):
    """Top-level configuration assembled from sub-configs."""

    stream: StreamConfig = Field(default_factory=StreamConfig)
    labels: LabelConfig = Field(default_factory=LabelConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    adaptation: AdaptationConfig = Field(default_factory=AdaptationConfig)
    output_dir: str = Field(
        "outputs",
        description="Directory (relative to CWD) where CSV/JSON results are saved.",
    )

    @model_validator(mode="after")
    def _warmup_lt_n_events(self) -> "DriftShieldConfig":
        if self.labels.warmup_size >= self.stream.n_events:
            raise ValueError(
                f"warmup_size ({self.labels.warmup_size}) must be less than "
                f"n_events ({self.stream.n_events})."
            )
        return self
