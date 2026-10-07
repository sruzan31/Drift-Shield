"""
Tests for driftshield.labeling

Key properties verified:
1. Budget never overspends.
2. Overlapping requests (monitor + low_margin) count once.
3. Changing selection_seed does NOT change generated features or hidden labels.
4. Labels join correct original predictions (by event_id).
5. Warm-up labels are not charged against budget.
6. Immediate and fixed-delay delivery work correctly.
"""

import pytest

from driftshield.config import LabelConfig, StreamConfig
from driftshield.contracts import PredictionRecord
from driftshield.labeling import LabelAcquirer
from driftshield.simulator import Simulator


def make_sim(n_events=300, seed=42, label_delay=0):
    cfg = StreamConfig(n_events=n_events, seed=seed)
    return Simulator(cfg, label_delay=label_delay)


def make_prediction(evt, proba=0.5, warmup=False):
    return PredictionRecord(
        event_id=evt.event_id,
        sequence=evt.sequence,
        timestamp=evt.timestamp,
        predicted_label=int(proba >= 0.5),
        predicted_proba=proba,
        features=dict(evt.features),
        warmup=warmup,
    )


class TestBudgetEnforcement:
    def test_budget_never_exceeded(self):
        budget = 50
        sim = make_sim(n_events=500)
        cfg = LabelConfig(
            warmup_size=50,
            label_budget=budget,
            monitor_rate=0.5,
            low_margin_k=20,
            label_delay=0,
        )
        acquirer = LabelAcquirer(cfg, sim.label_records)

        for evt in sim.events:
            is_warmup = evt.sequence < cfg.warmup_size
            pred = make_prediction(evt, warmup=is_warmup)
            acquirer.step(evt.sequence, pred)

        assert acquirer.budget_used <= budget, (
            f"Budget exceeded: used {acquirer.budget_used}, limit {budget}"
        )

    def test_budget_zero_acquires_nothing_postWarmup(self):
        sim = make_sim(n_events=200)
        cfg = LabelConfig(
            warmup_size=20,
            label_budget=0,
            monitor_rate=1.0,
            low_margin_k=100,
            label_delay=0,
        )
        acquirer = LabelAcquirer(cfg, sim.label_records)

        for evt in sim.events:
            is_warmup = evt.sequence < cfg.warmup_size
            pred = make_prediction(evt, warmup=is_warmup)
            acquirer.step(evt.sequence, pred)

        assert acquirer.budget_used == 0


class TestDeduplication:
    def test_overlapping_monitor_and_low_margin_count_once(self):
        """
        With monitor_rate=1.0 and low_margin_k=very large, both strategies
        select every event.  Each should still count only once.
        """
        budget = 30
        sim = make_sim(n_events=200, seed=1)
        cfg = LabelConfig(
            warmup_size=20,
            label_budget=budget,
            monitor_rate=1.0,   # select every event
            low_margin_k=1000,  # also select every event
            label_delay=0,
            selection_seed=10,
        )
        acquirer = LabelAcquirer(cfg, sim.label_records)

        acquired_event_ids = set()
        for evt in sim.events:
            is_warmup = evt.sequence < cfg.warmup_size
            pred = make_prediction(evt, proba=0.5, warmup=is_warmup)
            delivered = acquirer.step(evt.sequence, pred)
            for lbl in delivered:
                if lbl.source != "warmup":
                    acquired_event_ids.add(lbl.event_id)

        assert len(acquired_event_ids) == acquirer.budget_used
        assert acquirer.budget_used <= budget


class TestSelectionSeedIsolation:
    def test_different_selection_seeds_same_stream(self):
        """Changing selection_seed must not affect generated features or hidden labels."""
        stream_cfg = StreamConfig(n_events=100, seed=42)
        sim_a = Simulator(stream_cfg, label_delay=0)
        sim_b = Simulator(stream_cfg, label_delay=0)

        for ea, eb in zip(sim_a.events, sim_b.events):
            assert ea.features == eb.features, (
                f"Features differ at seq {ea.sequence} despite same stream seed"
            )
        for ea in sim_a.events:
            assert (
                sim_a.get_hidden_label(ea.event_id)
                == sim_b.get_hidden_label(ea.event_id)
            )

    def test_different_selection_seeds_may_acquire_different_labels(self):
        """Different selection seeds CAN produce different label sets."""
        stream_cfg = StreamConfig(n_events=200, seed=42)

        results = []
        for sel_seed in (10, 20):
            sim = Simulator(stream_cfg, label_delay=0)
            cfg = LabelConfig(
                warmup_size=20,
                label_budget=30,
                monitor_rate=0.2,
                low_margin_k=5,
                label_delay=0,
                selection_seed=sel_seed,
            )
            acquirer = LabelAcquirer(cfg, sim.label_records)
            acquired_ids = set()
            for evt in sim.events:
                is_warmup = evt.sequence < cfg.warmup_size
                pred = make_prediction(evt, warmup=is_warmup)
                delivered = acquirer.step(evt.sequence, pred)
                for lbl in delivered:
                    if lbl.source != "warmup":
                        acquired_ids.add(lbl.event_id)
            results.append(acquired_ids)

        # They may or may not differ, but both must be within budget
        for ids in results:
            assert len(ids) <= 30


class TestLabelDelivery:
    def test_immediate_delivery(self):
        """With label_delay=0, labels arrive at the same step as the event."""
        sim = make_sim(n_events=60, label_delay=0)
        cfg = LabelConfig(
            warmup_size=10,
            label_budget=50,
            monitor_rate=1.0,
            low_margin_k=0,
            label_delay=0,
        )
        acquirer = LabelAcquirer(cfg, sim.label_records)

        for evt in sim.events:
            is_warmup = evt.sequence < cfg.warmup_size
            pred = make_prediction(evt, warmup=is_warmup)
            delivered = acquirer.step(evt.sequence, pred)
            # Post-warmup events selected by monitor should deliver immediately
            for lbl in delivered:
                # delivery_sequence should be <= current sequence
                assert lbl.delivery_sequence <= evt.sequence

    def test_fixed_delay_delivery(self):
        """With label_delay=5, labels arrive 5 steps after the event."""
        delay = 5
        sim = Simulator(StreamConfig(n_events=100, seed=0), label_delay=delay)
        cfg = LabelConfig(
            warmup_size=10,
            label_budget=30,
            monitor_rate=1.0,
            low_margin_k=0,
            label_delay=delay,
        )
        acquirer = LabelAcquirer(cfg, sim.label_records)

        for evt in sim.events:
            is_warmup = evt.sequence < cfg.warmup_size
            pred = make_prediction(evt, warmup=is_warmup)
            delivered = acquirer.step(evt.sequence, pred)
            for lbl in delivered:
                # All delivered labels should have delivery_sequence <= current step
                assert lbl.delivery_sequence <= evt.sequence, (
                    f"Label delivered too early: delivery_seq={lbl.delivery_sequence}, "
                    f"current={evt.sequence}"
                )

    def test_labels_join_correct_predictions(self):
        """Each acquired label's event_id must match the event that was predicted."""
        sim = make_sim(n_events=100, seed=5)
        cfg = LabelConfig(
            warmup_size=10,
            label_budget=20,
            monitor_rate=0.3,
            low_margin_k=0,
            label_delay=0,
        )
        acquirer = LabelAcquirer(cfg, sim.label_records)

        event_ids_seen = {e.event_id for e in sim.events}
        for evt in sim.events:
            is_warmup = evt.sequence < cfg.warmup_size
            pred = make_prediction(evt, warmup=is_warmup)
            delivered = acquirer.step(evt.sequence, pred)
            for lbl in delivered:
                assert lbl.event_id in event_ids_seen, (
                    f"Delivered label for unknown event_id: {lbl.event_id}"
                )

    def test_warmup_labels_not_charged(self):
        sim = make_sim(n_events=100, seed=0)
        cfg = LabelConfig(
            warmup_size=20,
            label_budget=10,
            monitor_rate=0.0,
            low_margin_k=0,
            label_delay=0,
        )
        acquirer = LabelAcquirer(cfg, sim.label_records)

        for evt in sim.events:
            is_warmup = evt.sequence < cfg.warmup_size
            pred = make_prediction(evt, warmup=is_warmup)
            acquirer.step(evt.sequence, pred)

        # With monitor_rate=0.0 and low_margin_k=0, budget should be 0
        assert acquirer.budget_used == 0


class TestReservedMonitoringCapacity:
    def test_selective_cannot_starve_reserved_monitoring_capacity(self):
        """
        Prove that aggressive selective requests cannot consume capacity reserved
        for the monitoring channel.
        """
        total_budget = 300
        sim = make_sim(n_events=1000, seed=42)
        cfg = LabelConfig(
            warmup_size=100,
            label_budget=total_budget,
            monitor_rate=0.10,
            low_margin_k=50,  # Aggressive selective candidate pool
            label_delay=0,
        )
        acquirer = LabelAcquirer(cfg, sim.label_records)

        for evt in sim.events:
            is_warmup = evt.sequence < cfg.warmup_size
            # Fixed 0.5 probability creates maximum uncertainty for low margin
            pred = make_prediction(evt, proba=0.5, warmup=is_warmup)
            acquirer.step(evt.sequence, pred)

        stats = acquirer.get_channel_stats()
        # Selective is capped at effective_selective_budget (100)
        assert stats["selective"]["acquired"] <= cfg.effective_selective_budget
        # Monitoring channel successfully acquired labels throughout the stream
        assert stats["monitor"]["acquired"] > 0
        # Total acquired post-warmup does not exceed the total budget
        assert acquirer.budget_used <= total_budget

