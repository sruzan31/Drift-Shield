"""
driftshield.labeling
====================
Budgeted label-acquisition subsystem for DriftShield Phase 1.

Two selection strategies run in parallel, each with its own budget cap:

1. **Random monitoring** — each post-warm-up event is independently selected
   with probability ``monitor_rate``. Uses the selection RNG only.
   Independent of model confidence. Budget: ``monitor_budget``.

2. **Low-margin (selective) selection** — at each step the ``low_margin_k``
   events with the smallest margin ``|P(label=1) - 0.5|`` among all
   unlabelled post-warm-up events so far are queued. Budget: ``selective_budget``.

Deduplication and budget enforcement
-------------------------------------
* If both strategies select the same event, it is counted **once** and charged
  to the channel that selected it first (monitor takes priority).
* Each channel's budget is tracked independently.
* The total unique labels acquired is at most ``monitor_budget + selective_budget``,
  and may be less due to overlap.

Isolation guarantee
-------------------
The ``LabelAcquirer`` uses a *separate* ``np.random.default_rng`` seeded from
``LabelConfig.selection_seed``. Changing ``selection_seed`` does **not** affect
stream generation.

Warm-up labels
--------------
All warm-up labels are acquired unconditionally (needed to train the initial
model). They are NOT charged against any budget.

Delay guarantee
---------------
A label is never delivered before its scheduled ``delivery_sequence``. The
``flush_all_pending`` helper drains labels up to a supplied sequence ceiling;
callers are responsible for advancing time correctly.

Label accounting
----------------
For each channel the acquirer tracks:
* ``requested``: how many times a label was requested (before budget/dedup check)
* ``acquired``: how many unique labels were charged against the budget
* ``pending``: how many acquired labels are still waiting for delivery
* ``rejected``: how many requests were refused (budget exhausted or duplicate)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import numpy as np

from .config import LabelConfig
from .contracts import AcquiredLabel, LabelRecord, PredictionRecord


@dataclass
class ChannelStats:
    """Per-channel label acquisition statistics."""
    requested: int = 0    # labels requested (pre-dedup, pre-budget)
    acquired: int = 0     # unique labels charged to this channel
    delivered: int = 0    # acquired labels that have been delivered
    pending: int = 0      # acquired labels not yet delivered
    rejected: int = 0     # requests refused (budget or duplicate)

    def to_dict(self) -> dict:
        return {
            "requested": self.requested,
            "acquired": self.acquired,
            "delivered": self.delivered,
            "pending": self.pending,
            "rejected": self.rejected,
        }


class LabelAcquirer:
    """
    Manages label acquisition with per-channel budgets, deduplication, and delay.

    Parameters
    ----------
    config : LabelConfig
    all_label_records : List[LabelRecord]
        Full set of label records from the simulator (including hidden truth).
        Keyed internally by event_id.
    """

    def __init__(
        self,
        config: LabelConfig,
        all_label_records: List[LabelRecord],
    ) -> None:
        self._cfg = config
        self._rng = np.random.default_rng(config.selection_seed)

        # Map event_id -> LabelRecord for O(1) lookup
        self._truth: Dict[str, LabelRecord] = {
            r.event_id: r for r in all_label_records
        }

        # Per-event tracking — which channel (if any) claimed this event_id
        self._claimed: Dict[str, str] = {}   # event_id -> channel name

        # Warmup tracking (separate, free pool)
        self._warmup_acquired: Set[str] = set()

        # Per-channel budget counters
        self._monitor_used: int = 0
        self._selective_used: int = 0

        # Per-channel stats
        self._monitor_stats = ChannelStats()
        self._selective_stats = ChannelStats()
        self._warmup_stats = ChannelStats()

        # Pending-delivery queue: delivery_sequence -> list of AcquiredLabel
        self._pending_delivery: Dict[int, List[AcquiredLabel]] = {}

        # Pool of unlabelled post-warmup predictions available for low-margin
        self._unlabelled_preds: Dict[str, PredictionRecord] = {}

        # Audit queue of label requests for persistence
        self._new_requests: List[Dict[str, Any]] = []
        self._current_sequence: int = 0

    def pop_new_requests(self) -> List[Dict[str, Any]]:
        """Return and clear newly recorded label requests."""
        reqs = list(self._new_requests)
        self._new_requests.clear()
        return reqs

    @property
    def monitor_used(self) -> int:
        """Unique monitor labels acquired (charged to monitor_budget)."""
        return self._monitor_used

    @property
    def selective_used(self) -> int:
        """Unique selective labels acquired (charged to selective_budget)."""
        return self._selective_used

    @property
    def total_acquired(self) -> int:
        """Total unique post-warmup labels acquired across both channels."""
        return self._monitor_used + self._selective_used

    @property
    def monitor_budget_remaining(self) -> int:
        return max(0, min(self._cfg.effective_monitor_budget - self._monitor_used, self._cfg.label_budget - self.total_acquired))

    @property
    def selective_budget_remaining(self) -> int:
        return max(0, min(self._cfg.effective_selective_budget - self._selective_used, self._cfg.label_budget - self.total_acquired))

    # legacy alias kept for backward compat with tests
    @property
    def budget_used(self) -> int:
        return self.total_acquired

    @property
    def budget_remaining(self) -> int:
        return max(0, self._cfg.label_budget - self.total_acquired)

    def get_channel_stats(self) -> dict:
        """Return per-channel stats dict (for reporting/JSON)."""
        return {
            "warmup": self._warmup_stats.to_dict(),
            "monitor": self._monitor_stats.to_dict(),
            "selective": self._selective_stats.to_dict(),
        }

    def was_monitor_acquired(self, event_id: str) -> bool:
        """Return True if event was acquired by the random-monitoring channel."""
        return self._claimed.get(event_id) in ("monitor", "both")

    def step(
        self,
        current_sequence: int,
        prediction: Optional[PredictionRecord],
    ) -> List[AcquiredLabel]:
        """
        Process one stream step.

        1. If ``prediction`` is a warm-up prediction, acquire its label
           unconditionally (not charged against any budget).
        2. If ``prediction`` is a post-warm-up prediction, apply random
           monitoring (using the selection RNG) and register it for
           low-margin selection.
        3. Apply low-margin selection over all unlabelled predictions.
        4. Deliver labels whose ``delivery_sequence <= current_sequence``.

        Parameters
        ----------
        current_sequence : int
        prediction : PredictionRecord or None

        Returns
        -------
        List[AcquiredLabel]
            Labels delivered at this step (may be empty).
        """
        self._current_sequence = current_sequence
        if prediction is not None:
            if prediction.warmup:
                self._acquire_warmup(prediction.event_id)
            else:
                event_id = prediction.event_id
                # Register for low-margin pool (before monitor decision)
                self._unlabelled_preds[event_id] = prediction

                # --- Random monitoring (uses RNG; independent of confidence) ---
                self._monitor_stats.requested += 1
                selected_monitor = self._rng.random() < self._cfg.monitor_rate
                if selected_monitor:
                    self._try_acquire(event_id, "monitor")
                else:
                    # RNG was consumed above; no acquisition
                    pass

        # --- Low-margin (selective) selection ---
        self._apply_low_margin()

        # --- Deliver due labels ---
        delivered = self._deliver(current_sequence)
        # Update delivered/pending stats
        for lbl in delivered:
            if lbl.source == "warmup":
                self._warmup_stats.delivered += 1
                self._warmup_stats.pending -= 1
            elif lbl.source == "monitor":
                self._monitor_stats.delivered += 1
                self._monitor_stats.pending -= 1
            elif lbl.source in ("selective", "both"):
                self._selective_stats.delivered += 1
                self._selective_stats.pending -= 1
        return delivered

    def flush_pending_up_to(self, up_to_sequence: int) -> List[AcquiredLabel]:
        """
        Deliver all labels whose delivery_sequence <= up_to_sequence.

        This respects the delay guarantee: labels are never delivered early.
        Callers must pass the correct logical time.

        Parameters
        ----------
        up_to_sequence : int
            The maximum delivery sequence to drain.
        """
        delivered = self._deliver(up_to_sequence)
        for lbl in delivered:
            if lbl.source == "warmup":
                self._warmup_stats.delivered += 1
                self._warmup_stats.pending -= 1
            elif lbl.source == "monitor":
                self._monitor_stats.delivered += 1
                self._monitor_stats.pending -= 1
            elif lbl.source in ("selective", "both"):
                self._selective_stats.delivered += 1
                self._selective_stats.pending -= 1
        return delivered

    def flush_all_pending(self, current_sequence: int) -> List[AcquiredLabel]:
        """
        Backwards-compatible alias for flush_pending_up_to.
        Only delivers labels due at or before current_sequence.
        """
        return self.flush_pending_up_to(current_sequence)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _acquire_warmup(self, event_id: str) -> None:
        """Acquire a warm-up label unconditionally (free, not budgeted)."""
        if event_id in self._warmup_acquired:
            return
        self._warmup_acquired.add(event_id)
        self._warmup_stats.requested += 1
        self._warmup_stats.acquired += 1
        rec = self._truth[event_id]
        acquired = AcquiredLabel(
            event_id=event_id,
            true_label=rec.true_label,
            delivery_sequence=rec.delivery_sequence,
            source="warmup",
        )
        self._schedule(acquired)
        self._warmup_stats.pending += 1
        self._new_requests.append({
            "event_id": event_id,
            "channel": "warmup",
            "cost": 0.0,
            "budget_debit": 0,
            "status": "ACQUIRED",
            "requested_sequence": self._current_sequence,
        })

    def _try_acquire(self, event_id: str, channel: str) -> bool:
        """
        Attempt to acquire a post-warm-up label for the given channel.

        Returns True if a new acquisition was made.
        Deduplicates: if the event was already claimed by another channel,
        it is counted once (charged to the first claiming channel).
        """
        # Already claimed by any channel: skip (deduplication)
        if event_id in self._claimed:
            if channel == "monitor":
                self._monitor_stats.rejected += 1
            else:
                self._selective_stats.rejected += 1
            return False

        # Total budget check
        if self.total_acquired >= self._cfg.label_budget:
            if channel == "monitor":
                self._monitor_stats.rejected += 1
            else:
                self._selective_stats.rejected += 1
            return False

        # Budget check for this channel
        if channel == "monitor":
            if self._monitor_used >= self._cfg.effective_monitor_budget:
                self._monitor_stats.rejected += 1
                return False
            self._monitor_used += 1
            self._monitor_stats.acquired += 1
            stats = self._monitor_stats
        else:  # selective
            if self._selective_used >= self._cfg.effective_selective_budget:
                self._selective_stats.rejected += 1
                return False
            self._selective_used += 1
            self._selective_stats.acquired += 1
            stats = self._selective_stats

        self._claimed[event_id] = channel
        # Remove from unlabelled pool
        self._unlabelled_preds.pop(event_id, None)

        rec = self._truth[event_id]
        acquired = AcquiredLabel(
            event_id=event_id,
            true_label=rec.true_label,
            delivery_sequence=rec.delivery_sequence,
            source=channel,
        )
        self._schedule(acquired)
        stats.pending += 1
        self._new_requests.append({
            "event_id": event_id,
            "channel": channel,
            "cost": 1.0,
            "budget_debit": 1,
            "status": "ACQUIRED",
            "requested_sequence": self._current_sequence,
        })
        return True

    def _apply_low_margin(self) -> None:
        """
        Select the top-k most uncertain unlabelled predictions for the
        selective channel.
        """
        if not self._unlabelled_preds or self._cfg.low_margin_k <= 0:
            return
        if (
            self.total_acquired >= self._cfg.label_budget
            or self._selective_used >= self._cfg.effective_selective_budget
        ):
            return

        # Sort by ascending margin (most uncertain first)
        sorted_preds = sorted(
            self._unlabelled_preds.values(),
            key=lambda p: abs(p.predicted_proba - 0.5),
        )
        candidates = sorted_preds[: self._cfg.low_margin_k]

        for pred in candidates:
            if (
                self.total_acquired >= self._cfg.label_budget
                or self._selective_used >= self._cfg.effective_selective_budget
            ):
                break
            self._selective_stats.requested += 1
            self._try_acquire(pred.event_id, "selective")

    def _schedule(self, acquired: AcquiredLabel) -> None:
        """Add to pending-delivery queue keyed by delivery_sequence."""
        seq = acquired.delivery_sequence
        if seq not in self._pending_delivery:
            self._pending_delivery[seq] = []
        self._pending_delivery[seq].append(acquired)

    def _deliver(self, current_sequence: int) -> List[AcquiredLabel]:
        """Return and remove all labels due at or before current_sequence.

        This is the ONLY place labels leave the pending queue.
        Labels are never delivered before their delivery_sequence.
        """
        delivered: List[AcquiredLabel] = []
        due_seqs = [s for s in self._pending_delivery if s <= current_sequence]
        for s in sorted(due_seqs):
            delivered.extend(self._pending_delivery.pop(s))
        return delivered
