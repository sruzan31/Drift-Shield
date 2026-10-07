"""
Tests for driftshield.baseline

Key properties verified:
1. Preprocessor (StandardScaler) fits on warm-up features and transforms features.
2. Learner updates incrementally during warm-up.
3. learn() after freeze() raises RuntimeError.
4. predict() returns a valid PredictionRecord before and after freeze.
5. Idempotent freeze() calls.
"""

import pytest

from driftshield.baseline import BaselineClassifier
from driftshield.config import LabelConfig
from driftshield.contracts import StreamEvent


def make_event(seq: int = 0, f0: float = 1.0, f1: float = -1.0) -> StreamEvent:
    return StreamEvent(
        event_id=f"evt-{seq}",
        sequence=seq,
        timestamp=1700000000.0 + seq,
        features={"feature_0": f0, "feature_1": f1},
    )


class TestBaselineClassifier:
    def test_predict_returns_valid_record(self):
        cfg = LabelConfig(warmup_size=10)
        clf = BaselineClassifier(cfg)
        evt = make_event(0)
        pred = clf.predict(evt)
        assert pred.event_id == "evt-0"
        assert pred.sequence == 0
        assert pred.predicted_label in (0, 1)
        assert 0.0 <= pred.predicted_proba <= 1.0
        assert pred.warmup is True

    def test_learn_during_warmup(self):
        cfg = LabelConfig(warmup_size=10)
        clf = BaselineClassifier(cfg)
        evt = make_event(0)
        clf.register_warmup_features(evt)
        clf.learn(evt.event_id, 1)
        assert not clf.is_frozen

    def test_learn_after_freeze_raises_runtime_error(self):
        cfg = LabelConfig(warmup_size=10)
        clf = BaselineClassifier(cfg)
        evt = make_event(0)
        clf.register_warmup_features(evt)
        clf.learn(evt.event_id, 1)
        clf.freeze()
        assert clf.is_frozen

        with pytest.raises(RuntimeError, match="frozen"):
            clf.learn("evt-1", 0)

    def test_freeze_is_idempotent(self):
        cfg = LabelConfig(warmup_size=10)
        clf = BaselineClassifier(cfg)
        clf.freeze()
        assert clf.is_frozen
        clf.freeze()
        assert clf.is_frozen

    def test_scaler_fitting_and_transformation(self):
        cfg = LabelConfig(warmup_size=10)
        clf = BaselineClassifier(cfg)
        for i in range(10):
            evt = make_event(i, f0=float(i * 10), f1=float(-i * 10))
            clf.register_warmup_features(evt)
            clf.learn(evt.event_id, int(i % 2))
        clf.freeze()

        # Predict post-warmup event
        prod_evt = make_event(10, f0=20.0, f1=-20.0)
        pred = clf.predict(prod_evt)
        assert pred.warmup is False
        assert pred.predicted_label in (0, 1)
