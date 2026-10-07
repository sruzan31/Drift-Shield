"""
Tests for driftshield.contracts
"""

import pytest
from driftshield.contracts import AcquiredLabel, LabelRecord, PredictionRecord, StreamEvent


class TestStreamEvent:
    def test_valid_event(self):
        evt = StreamEvent(
            event_id="evt-0",
            sequence=0,
            timestamp=1234567890.0,
            features={"feature_0": 0.5, "feature_1": -0.3},
        )
        assert evt.event_id == "evt-0"
        assert evt.is_synthetic is True

    def test_empty_event_id_raises(self):
        with pytest.raises(ValueError, match="event_id"):
            StreamEvent(
                event_id="",
                sequence=0,
                timestamp=1234567890.0,
                features={"feature_0": 0.5},
            )

    def test_negative_sequence_raises(self):
        with pytest.raises(ValueError, match="sequence"):
            StreamEvent(
                event_id="evt-x",
                sequence=-1,
                timestamp=1234567890.0,
                features={"feature_0": 0.5},
            )

    def test_empty_features_raises(self):
        with pytest.raises(ValueError, match="features"):
            StreamEvent(
                event_id="evt-0",
                sequence=0,
                timestamp=1234567890.0,
                features={},
            )

    def test_non_numeric_feature_raises(self):
        with pytest.raises(TypeError, match="numeric"):
            StreamEvent(
                event_id="evt-0",
                sequence=0,
                timestamp=1234567890.0,
                features={"feature_0": "bad"},
            )

    def test_nan_feature_raises(self):
        import math
        with pytest.raises(ValueError, match="non-finite"):
            StreamEvent(
                event_id="evt-0",
                sequence=0,
                timestamp=1234567890.0,
                features={"feature_0": float("nan")},
            )

    def test_inf_feature_raises(self):
        with pytest.raises(ValueError, match="non-finite"):
            StreamEvent(
                event_id="evt-0",
                sequence=0,
                timestamp=1234567890.0,
                features={"feature_0": float("inf")},
            )

    def test_frozen(self):
        evt = StreamEvent(
            event_id="evt-0",
            sequence=0,
            timestamp=1234567890.0,
            features={"feature_0": 0.5},
        )
        with pytest.raises((AttributeError, TypeError)):
            evt.sequence = 99  # type: ignore[misc]


class TestPredictionRecord:
    def test_valid_prediction(self):
        pred = PredictionRecord(
            event_id="evt-0",
            sequence=0,
            timestamp=1.0,
            predicted_label=1,
            predicted_proba=0.8,
            features={"feature_0": 0.1},
        )
        assert pred.predicted_label == 1
        assert pred.warmup is False

    def test_invalid_label_raises(self):
        with pytest.raises(ValueError, match="predicted_label"):
            PredictionRecord(
                event_id="evt-0",
                sequence=0,
                timestamp=1.0,
                predicted_label=2,
                predicted_proba=0.9,
                features={"feature_0": 0.1},
            )

    def test_proba_out_of_range_raises(self):
        with pytest.raises(ValueError, match="predicted_proba"):
            PredictionRecord(
                event_id="evt-0",
                sequence=0,
                timestamp=1.0,
                predicted_label=1,
                predicted_proba=1.5,
                features={"feature_0": 0.1},
            )

    def test_frozen(self):
        pred = PredictionRecord(
            event_id="evt-0",
            sequence=0,
            timestamp=1.0,
            predicted_label=0,
            predicted_proba=0.3,
            features={"feature_0": 0.1},
        )
        with pytest.raises((AttributeError, TypeError)):
            pred.predicted_label = 1  # type: ignore[misc]


class TestLabelRecord:
    def test_valid(self):
        lr = LabelRecord(event_id="evt-0", true_label=1, delivery_sequence=5)
        assert lr.true_label == 1

    def test_invalid_label(self):
        with pytest.raises(ValueError, match="true_label"):
            LabelRecord(event_id="evt-0", true_label=2, delivery_sequence=0)

    def test_negative_delivery_sequence(self):
        with pytest.raises(ValueError, match="delivery_sequence"):
            LabelRecord(event_id="evt-0", true_label=0, delivery_sequence=-1)
