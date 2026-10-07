"""
driftshield.simulator
=====================
Reproducible numerical-stream simulator for DriftShield Phase 7A.

Design guarantees
-----------------
* **Reproducibility**: given the same ``StreamConfig.seed``, every run
  produces identical ``StreamEvent`` objects and identical hidden labels.
* **Isolation**: the data-generation RNG is seeded from ``StreamConfig.seed``
  only; changing ``LabelConfig.selection_seed`` has zero effect on generated
  data.
* **Hidden truth**: the ``Simulator`` stores true labels internally. It
  exposes them ONLY through ``get_hidden_label(event_id)`` (called by the
  evaluator) and through the ``LabelRecord`` list returned by
  ``get_label_records()``. The public ``StreamEvent`` objects contain no
  label information.
* **Synthetic flag**: every ``StreamEvent`` carries ``is_synthetic=True``.

Scenarios
---------
* ``stationary``: features drawn from two fixed Gaussian clusters.
  Class 0 -> centred at (-1, -1); Class 1 -> centred at (+1, +1).
* ``abrupt``: identical to stationary before ``drift_start_sequence``.
  At the drift point the boundary flips: Class 0 cluster moves to (+1, +1)
  and Class 1 cluster moves to (-1, -1).
* ``gradual``: concept mixture transitioning over ``gradual_window`` events
  starting at ``drift_start_sequence``, smoothly shifting mixture probability
  from 0.0 to 1.0.
* ``recurring``: periodic A-B-A concept oscillation switching between pre-drift
  and post-drift centroids every ``recurrence_interval`` events.
* ``rare_region``: stealth drift where instances falling in a small sub-region
  of mass ``rare_region_p`` flip their target label, testing subtle drift detection.
* ``adversary``: adaptive adversary inspecting prior 200 recorded events and model
  margins at dwell boundaries to commit worst-case labeling rules without peeking
  at future events.
"""

from __future__ import annotations

import math
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import numpy as np

from .config import StreamConfig
from .contracts import LabelRecord, StreamEvent


class Simulator:
    """
    Generates a finite stream of ``StreamEvent`` objects with hidden labels.

    Parameters
    ----------
    config : StreamConfig

    Attributes
    ----------
    events : List[StreamEvent]
        All generated events in sequence order (no labels).
    label_records : List[LabelRecord]
        All label records (truth + delivery info). Access via
        ``get_label_records()`` or ``get_hidden_label()``.
    drift_sequence : Optional[int]
        Sequence index at which drift begins (``None`` for stationary).
    evaluator_drift_info : Dict[str, Any]
        Evaluator-only ground truth metadata.
    """

    # Feature centroids for each class before and after standard drift
    _PRE_DRIFT_CENTROIDS: Dict[int, Tuple[float, float]] = {
        0: (-1.0, -1.0),
        1: (1.0, 1.0),
    }
    _POST_DRIFT_CENTROIDS: Dict[int, Tuple[float, float]] = {
        0: (1.0, 1.0),
        1: (-1.0, -1.0),
    }

    def __init__(self, config: StreamConfig, label_delay: int = 0) -> None:
        self._config = config
        self._label_delay = label_delay
        self._rng = np.random.default_rng(config.seed)

        self.drift_sequence: Optional[int] = (
            config.drift_start_sequence if config.scenario != "stationary" else None
        )
        self.evaluator_drift_info: Dict[str, Any] = {
            "scenario": config.scenario,
            "seed": config.seed,
            "drift_start_sequence": self.drift_sequence,
            "n_events": config.n_events,
            "label_delay": label_delay,
        }
        if config.scenario == "gradual":
            self.evaluator_drift_info.update({
                "gradual_window": config.gradual_window,
                "onset_sequence": config.drift_start_sequence,
                "midpoint_sequence": config.drift_start_sequence + config.gradual_window // 2,
                "completion_sequence": config.drift_start_sequence + config.gradual_window,
            })
        elif config.scenario == "recurring":
            num_transitions = max(1, (config.n_events - config.drift_start_sequence) // config.recurrence_interval + 1)
            self.evaluator_drift_info.update({
                "recurrence_interval": config.recurrence_interval,
                "transition_sequences": [
                    config.drift_start_sequence + k * config.recurrence_interval
                    for k in range(num_transitions)
                    if config.drift_start_sequence + k * config.recurrence_interval < config.n_events
                ],
            })
        elif config.scenario == "rare_region":
            self.evaluator_drift_info["rare_region_p"] = config.rare_region_p
        elif config.scenario == "adversary":
            self.evaluator_drift_info["adversary_dwell"] = config.adversary_dwell

        self.events: List[StreamEvent] = []
        self._hidden_labels: Dict[str, int] = {}   # event_id -> true label
        self.label_records: List[LabelRecord] = []

        self._generate()

    @property
    def label_delay(self) -> int:
        return self._label_delay

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_hidden_label(self, event_id: str) -> int:
        """Return the hidden true label for *event_id* (evaluator use only)."""
        try:
            return self._hidden_labels[event_id]
        except KeyError:
            raise KeyError(f"Unknown event_id: '{event_id}'")

    def get_label_records(self, label_delay: Optional[int] = None) -> List[LabelRecord]:
        """
        Return all label records, optionally overriding the delivery delay.
        """
        if label_delay is None:
            return list(self.label_records)
        delay = label_delay
        return [
            LabelRecord(
                event_id=r.event_id,
                true_label=r.true_label,
                delivery_sequence=self.events[i].sequence + delay,
            )
            for i, r in enumerate(self.label_records)
        ]

    def iter_events(self) -> Iterator[StreamEvent]:
        """Iterate over events in sequence order."""
        yield from self.events

    # ------------------------------------------------------------------
    # Internal generation
    # ------------------------------------------------------------------

    def _generate(self) -> None:
        """Generate all events and hidden labels according to configured scenario."""
        base_ts = 1_700_000_000.0  # 2023-11-14 (arbitrary, fixed epoch)
        step_secs = 1.0

        # State tracking for adaptive adversary
        adversary_switches: List[Dict[str, Any]] = []
        active_adversary_rule: Optional[str] = "r0_baseline"
        past_features_buffer: List[Tuple[float, float]] = []

        # Candidate adversary rules: (f0, f1) -> int
        adversary_rules: Dict[str, Callable[[float, float], int]] = {
            "r0_baseline": lambda f0, f1: int((f0 + f1) > 0.0),
            "r1_inverted": lambda f0, f1: int((f0 + f1) < 0.0),
            "r2_vertical": lambda f0, f1: int(f0 > 0.0),
            "r3_horizontal": lambda f0, f1: int(f1 > 0.0),
            "r4_orthogonal": lambda f0, f1: int((f0 - f1) > 0.0),
        }

        for seq in range(self._config.n_events):
            # 1. Sample features and label based on scenario
            if self._config.scenario == "stationary":
                label, f0, f1 = self._sample_stationary()

            elif self._config.scenario == "abrupt":
                label, f0, f1 = self._sample_abrupt(seq)

            elif self._config.scenario == "gradual":
                label, f0, f1 = self._sample_gradual(seq)

            elif self._config.scenario == "recurring":
                label, f0, f1 = self._sample_recurring(seq)

            elif self._config.scenario == "rare_region":
                label, f0, f1 = self._sample_rare_region(seq)

            elif self._config.scenario == "adversary":
                # Check for adaptive rule switch boundary
                drift_start = self._config.drift_start_sequence
                dwell = self._config.adversary_dwell

                if (
                    seq >= drift_start
                    and (seq - drift_start) % dwell == 0
                    and len(past_features_buffer) >= 50
                ):
                    # Inspect prior up to 200 feature events
                    inspect_window = past_features_buffer[-200:]
                    # Calculate baseline margins |f0 + f1| / sqrt(2)
                    margins = [abs(px + py) / 1.41421356 for px, py in inspect_window]
                    med_margin = float(np.median(margins))
                    high_margin_events = [
                        ev for ev, m in zip(inspect_window, margins) if m >= med_margin
                    ]
                    if not high_margin_events:
                        high_margin_events = inspect_window

                    # Select candidate rule maximizing disagreement with r0_baseline
                    best_rule_name = "r1_inverted"
                    best_disagreements = -1

                    for rname, rfunc in adversary_rules.items():
                        if rname == "r0_baseline":
                            continue
                        disagreements = sum(
                            1
                            for px, py in high_margin_events
                            if rfunc(px, py) != adversary_rules["r0_baseline"](px, py)
                        )
                        if disagreements > best_disagreements:
                            best_disagreements = disagreements
                            best_rule_name = rname

                    active_adversary_rule = best_rule_name
                    adversary_switches.append({
                        "switch_sequence": seq,
                        "cutoff_sequence": seq - 1,
                        "selected_rule": best_rule_name,
                        "high_margin_count": len(high_margin_events),
                        "disagreements": best_disagreements,
                    })

                label, f0, f1 = self._sample_adversary(active_adversary_rule or "r0_baseline")
                past_features_buffer.append((f0, f1))

            else:
                label, f0, f1 = self._sample_stationary()

            event_id = f"evt-{seq}"
            ts = base_ts + seq * step_secs

            event = StreamEvent(
                event_id=event_id,
                sequence=seq,
                timestamp=ts,
                features={"feature_0": float(f0), "feature_1": float(f1)},
                is_synthetic=True,
            )
            delivery_seq = seq + self._label_delay
            label_rec = LabelRecord(
                event_id=event_id,
                true_label=int(label),
                delivery_sequence=delivery_seq,
            )

            self.events.append(event)
            self._hidden_labels[event_id] = int(label)
            self.label_records.append(label_rec)

        if adversary_switches:
            self.evaluator_drift_info["adversary_switches"] = adversary_switches

    # ------------------------------------------------------------------
    # Scenario Samplers
    # ------------------------------------------------------------------

    def _sample_stationary(self) -> Tuple[int, float, float]:
        label = int(self._rng.integers(0, 2))
        cx, cy = self._PRE_DRIFT_CENTROIDS[label]
        f0 = cx + self._rng.normal(0.0, self._config.noise_std)
        f1 = cy + self._rng.normal(0.0, self._config.noise_std)
        return label, f0, f1

    def _sample_abrupt(self, seq: int) -> Tuple[int, float, float]:
        if seq >= self._config.drift_start_sequence:
            centroids = self._POST_DRIFT_CENTROIDS
        else:
            centroids = self._PRE_DRIFT_CENTROIDS
        label = int(self._rng.integers(0, 2))
        cx, cy = centroids[label]
        f0 = cx + self._rng.normal(0.0, self._config.noise_std)
        f1 = cy + self._rng.normal(0.0, self._config.noise_std)
        return label, f0, f1

    def _sample_gradual(self, seq: int) -> Tuple[int, float, float]:
        drift_start = self._config.drift_start_sequence
        window = max(1, self._config.gradual_window)

        if seq < drift_start:
            centroids = self._PRE_DRIFT_CENTROIDS
        elif seq >= drift_start + window:
            centroids = self._POST_DRIFT_CENTROIDS
        else:
            alpha = (seq - drift_start) / float(window)
            # Sample from post-drift with probability alpha
            if self._rng.uniform(0.0, 1.0) < alpha:
                centroids = self._POST_DRIFT_CENTROIDS
            else:
                centroids = self._PRE_DRIFT_CENTROIDS

        label = int(self._rng.integers(0, 2))
        cx, cy = centroids[label]
        f0 = cx + self._rng.normal(0.0, self._config.noise_std)
        f1 = cy + self._rng.normal(0.0, self._config.noise_std)
        return label, f0, f1

    def _sample_recurring(self, seq: int) -> Tuple[int, float, float]:
        drift_start = self._config.drift_start_sequence
        interval = max(1, self._config.recurrence_interval)

        if seq < drift_start:
            centroids = self._PRE_DRIFT_CENTROIDS
        else:
            period_idx = (seq - drift_start) // interval
            if period_idx % 2 == 0:
                centroids = self._POST_DRIFT_CENTROIDS
            else:
                centroids = self._PRE_DRIFT_CENTROIDS

        label = int(self._rng.integers(0, 2))
        cx, cy = centroids[label]
        f0 = cx + self._rng.normal(0.0, self._config.noise_std)
        f1 = cy + self._rng.normal(0.0, self._config.noise_std)
        return label, f0, f1

    def _sample_rare_region(self, seq: int) -> Tuple[int, float, float]:
        # Pre-drift clusters
        label = int(self._rng.integers(0, 2))
        cx, cy = self._PRE_DRIFT_CENTROIDS[label]
        f0 = cx + self._rng.normal(0.0, self._config.noise_std)
        f1 = cy + self._rng.normal(0.0, self._config.noise_std)

        # In post-drift events, instances falling into rare quadrant flip 0 -> 1
        if seq >= self._config.drift_start_sequence:
            # Cutoff for rare subregion: approximate mass rare_region_p
            # For p=0.05, tail threshold z ≈ -1.645 * noise_std
            p = self._config.rare_region_p
            z_thresh = -1.0 - (1.645 * (1.0 - 2.0 * p)) * self._config.noise_std
            if label == 0 and f0 < z_thresh:
                label = 1  # stealth flip in rare subpopulation

        return label, f0, f1

    def _sample_adversary(self, rule_name: str) -> Tuple[int, float, float]:
        # Draw from continuous background space
        f0 = float(self._rng.normal(0.0, 1.2))
        f1 = float(self._rng.normal(0.0, 1.2))

        # Evaluate committed deterministic rule
        if rule_name == "r1_inverted":
            label = int((f0 + f1) < 0.0)
        elif rule_name == "r2_vertical":
            label = int(f0 > 0.0)
        elif rule_name == "r3_horizontal":
            label = int(f1 > 0.0)
        elif rule_name == "r4_orthogonal":
            label = int((f0 - f1) > 0.0)
        else:  # r0_baseline
            label = int((f0 + f1) > 0.0)

        # Add minor measurement noise to features
        f0 += float(self._rng.normal(0.0, self._config.noise_std * 0.5))
        f1 += float(self._rng.normal(0.0, self._config.noise_std * 0.5))
        return label, f0, f1

