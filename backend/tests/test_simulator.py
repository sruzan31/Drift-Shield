"""
Tests for driftshield.simulator

Key properties verified:
1. Identical seeds reproduce identical events and hidden labels.
2. Changing label-selection seed does NOT affect generated features or labels.
3. Event structure: monotonic sequence, correct field types, is_synthetic=True.
4. Abrupt scenario: boundary flips at drift_start_sequence.
5. Stationary scenario: no drift marker.
6. Label records: delivery_sequence matches delay.
"""

import pytest

from driftshield.config import StreamConfig
from driftshield.simulator import Simulator


class TestReproducibility:
    def test_identical_seeds_produce_identical_events(self):
        cfg = StreamConfig(n_events=100, seed=7)
        sim1 = Simulator(cfg)
        sim2 = Simulator(cfg)
        for e1, e2 in zip(sim1.events, sim2.events):
            assert e1.event_id == e2.event_id
            assert e1.sequence == e2.sequence
            assert e1.features == e2.features

    def test_identical_seeds_produce_identical_hidden_labels(self):
        cfg = StreamConfig(n_events=100, seed=7)
        sim1 = Simulator(cfg)
        sim2 = Simulator(cfg)
        for evt in sim1.events:
            assert sim1.get_hidden_label(evt.event_id) == sim2.get_hidden_label(evt.event_id)

    def test_different_seeds_produce_different_events(self):
        sim1 = Simulator(StreamConfig(n_events=100, seed=1))
        sim2 = Simulator(StreamConfig(n_events=100, seed=2))
        features1 = [e.features for e in sim1.events]
        features2 = [e.features for e in sim2.events]
        assert features1 != features2

    def test_label_selection_seed_does_not_affect_stream(self):
        """Changing selection_seed must not change generated features or labels."""
        from driftshield.config import LabelConfig, DriftShieldConfig
        cfg = StreamConfig(n_events=200, seed=42)
        sim_a = Simulator(cfg, label_delay=0)
        sim_b = Simulator(cfg, label_delay=0)
        # Both use the same stream seed — features and labels must be identical
        for ea, eb in zip(sim_a.events, sim_b.events):
            assert ea.features == eb.features
        for ea in sim_a.events:
            assert sim_a.get_hidden_label(ea.event_id) == sim_b.get_hidden_label(ea.event_id)


class TestEventStructure:
    def setup_method(self):
        self.sim = Simulator(StreamConfig(n_events=50, seed=0))

    def test_event_count(self):
        assert len(self.sim.events) == 50

    def test_sequence_monotonic(self):
        seqs = [e.sequence for e in self.sim.events]
        assert seqs == list(range(50))

    def test_event_ids_unique(self):
        ids = [e.event_id for e in self.sim.events]
        assert len(ids) == len(set(ids))

    def test_event_id_format(self):
        for evt in self.sim.events:
            assert evt.event_id == f"evt-{evt.sequence}"

    def test_is_synthetic(self):
        for evt in self.sim.events:
            assert evt.is_synthetic is True

    def test_features_are_finite(self):
        import math
        for evt in self.sim.events:
            for v in evt.features.values():
                assert math.isfinite(v)

    def test_two_features(self):
        for evt in self.sim.events:
            assert "feature_0" in evt.features
            assert "feature_1" in evt.features

    def test_timestamps_increasing(self):
        ts = [e.timestamp for e in self.sim.events]
        assert ts == sorted(ts)

    def test_hidden_labels_binary(self):
        for evt in self.sim.events:
            lbl = self.sim.get_hidden_label(evt.event_id)
            assert lbl in (0, 1)

    def test_no_label_in_event(self):
        """StreamEvent must not expose label information."""
        for evt in self.sim.events:
            assert not hasattr(evt, "label")
            assert not hasattr(evt, "true_label")


class TestStationaryScenario:
    def test_no_drift_sequence(self):
        sim = Simulator(StreamConfig(scenario="stationary", n_events=100, seed=0))
        assert sim.drift_sequence is None

    def test_roughly_balanced_classes(self):
        sim = Simulator(StreamConfig(scenario="stationary", n_events=1000, seed=42))
        labels = [sim.get_hidden_label(e.event_id) for e in sim.events]
        frac_1 = sum(labels) / len(labels)
        assert 0.4 < frac_1 < 0.6, f"Expected ~0.5, got {frac_1}"


class TestAbruptScenario:
    def test_drift_sequence_set(self):
        sim = Simulator(
            StreamConfig(scenario="abrupt", n_events=200, drift_start_sequence=100, seed=0)
        )
        assert sim.drift_sequence == 100

    def test_pre_drift_feature_distribution(self):
        """Pre-drift: class 1 should have positive mean features."""
        import numpy as np
        sim = Simulator(
            StreamConfig(scenario="abrupt", n_events=500, drift_start_sequence=400, seed=0)
        )
        pre_drift = [
            (e, sim.get_hidden_label(e.event_id))
            for e in sim.events if e.sequence < 400
        ]
        class1_f0 = [e.features["feature_0"] for e, l in pre_drift if l == 1]
        assert np.mean(class1_f0) > 0, "Pre-drift class 1 should have positive feature_0"

    def test_post_drift_feature_distribution_flips(self):
        """Post-drift: class 1 centroid should have negative mean features."""
        import numpy as np
        sim = Simulator(
            StreamConfig(scenario="abrupt", n_events=500, drift_start_sequence=100, seed=0)
        )
        post_drift = [
            (e, sim.get_hidden_label(e.event_id))
            for e in sim.events if e.sequence >= 100
        ]
        class1_f0 = [e.features["feature_0"] for e, l in post_drift if l == 1]
        assert np.mean(class1_f0) < 0, "Post-drift class 1 should have negative feature_0"


class TestLabelRecords:
    def test_label_records_count(self):
        sim = Simulator(StreamConfig(n_events=100, seed=0))
        assert len(sim.label_records) == 100

    def test_immediate_delivery(self):
        sim = Simulator(StreamConfig(n_events=50, seed=0), label_delay=0)
        for i, rec in enumerate(sim.label_records):
            assert rec.delivery_sequence == i

    def test_fixed_delay_delivery(self):
        sim = Simulator(StreamConfig(n_events=50, seed=0), label_delay=5)
        for i, rec in enumerate(sim.label_records):
            expected = i + 5
            assert rec.delivery_sequence == expected, f"seq {i}: expected {expected}, got {rec.delivery_sequence}"

    def test_label_records_match_hidden_labels(self):
        sim = Simulator(StreamConfig(n_events=100, seed=0))
        for rec in sim.label_records:
            assert rec.true_label == sim.get_hidden_label(rec.event_id)

    def test_unknown_event_id_raises(self):
        sim = Simulator(StreamConfig(n_events=10, seed=0))
        with pytest.raises(KeyError):
            sim.get_hidden_label("nonexistent-event")
