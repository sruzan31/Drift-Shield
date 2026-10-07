"""
Tests for driftshield.evaluator

Key properties verified:
1. Warm-up predictions are excluded from reported metrics.
2. Future labels cannot affect earlier predictions.
3. Reported error rate matches a direct re-calculation from saved predictions.
4. Labels join the correct original predictions (by event_id).
5. Duplicate prediction registration raises.
6. compute_error_rate_from_records == compute_metrics error_rate.
"""

import math
import pytest

from driftshield.config import LabelConfig, StreamConfig
from driftshield.contracts import AcquiredLabel, PredictionRecord
from driftshield.evaluator import Evaluator
from driftshield.simulator import Simulator


def make_simulator(n_events=100, seed=42):
    return Simulator(StreamConfig(n_events=n_events, seed=seed))


def make_pred(evt, proba=0.5, warmup=False):
    return PredictionRecord(
        event_id=evt.event_id,
        sequence=evt.sequence,
        timestamp=evt.timestamp,
        predicted_label=int(proba >= 0.5),
        predicted_proba=proba,
        features=dict(evt.features),
        warmup=warmup,
    )


def make_acquired(sim, event_id, source="monitor"):
    true_label = sim.get_hidden_label(event_id)
    return AcquiredLabel(
        event_id=event_id,
        true_label=true_label,
        delivery_sequence=0,
        source=source,
    )


class TestWarmupExclusion:
    def test_warmup_excluded_from_metrics(self):
        warmup_size = 10
        sim = make_simulator(n_events=50)
        evaluator = Evaluator(sim, warmup_size=warmup_size)

        for evt in sim.events:
            is_warmup = evt.sequence < warmup_size
            pred = make_pred(evt, warmup=is_warmup)
            evaluator.record_prediction(pred)
            if not is_warmup:
                acq = make_acquired(sim, evt.event_id)
                evaluator.deliver_label(acq)

        metrics = evaluator.compute_metrics()
        assert metrics.warmup_predictions == warmup_size
        assert metrics.total_predictions == 50 - warmup_size
        # All post-warmup predictions should be scored
        assert metrics.scored_predictions == 50 - warmup_size

    def test_warmup_labels_do_not_affect_postWarmup_metrics(self):
        """Warmup labels must not affect monitor/selective channel metrics or warmup counts."""
        warmup_size = 5
        sim = make_simulator(n_events=20)
        evaluator = Evaluator(sim, warmup_size=warmup_size)

        for evt in sim.events:
            is_warmup = evt.sequence < warmup_size
            pred = make_pred(evt, warmup=is_warmup)
            evaluator.record_prediction(pred)
            # Only deliver warmup labels (no post-warmup labels)
            if is_warmup:
                acq = make_acquired(sim, evt.event_id, source="warmup")
                evaluator.deliver_label(acq)

        metrics = evaluator.compute_metrics()
        assert metrics.warmup_predictions == warmup_size
        assert metrics.scored_predictions == 20 - warmup_size
        assert metrics.monitor_channel.total == 0
        assert metrics.monitor_channel.error_rate is None
        assert metrics.selective_channel.total == 0
        assert metrics.selective_channel.error_rate is None


class TestFutureLabelIsolation:
    def test_future_labels_cannot_change_past_predictions(self):
        """
        Predictions are locked in at record time.  Delivering a label later
        must not mutate the prediction.
        """
        sim = make_simulator(n_events=20)
        warmup_size = 5
        evaluator = Evaluator(sim, warmup_size=warmup_size)

        # Record all predictions
        preds = {}
        for evt in sim.events:
            is_warmup = evt.sequence < warmup_size
            pred = make_pred(evt, proba=0.3, warmup=is_warmup)
            preds[evt.event_id] = pred
            evaluator.record_prediction(pred)

        # Deliver labels AFTER all predictions are recorded
        for evt in sim.events:
            if evt.sequence >= warmup_size:
                acq = make_acquired(sim, evt.event_id)
                evaluator.deliver_label(acq)

        # Verify original predictions are unchanged
        for evt in sim.events:
            original_pred = preds[evt.event_id]
            assert original_pred.predicted_proba == 0.3
            assert original_pred.predicted_label == 0


class TestErrorRateConsistency:
    def test_error_rate_matches_direct_calculation(self):
        """
        The evaluator's reported error_rate must equal a direct re-calculation
        from saved scored predictions.
        """
        warmup_size = 10
        sim = make_simulator(n_events=100)
        evaluator = Evaluator(sim, warmup_size=warmup_size)

        for evt in sim.events:
            is_warmup = evt.sequence < warmup_size
            pred = make_pred(evt, warmup=is_warmup)
            evaluator.record_prediction(pred)
            if not is_warmup:
                acq = make_acquired(sim, evt.event_id)
                evaluator.deliver_label(acq)

        metrics = evaluator.compute_metrics()
        direct_error = evaluator.compute_error_rate_from_records()

        assert not math.isnan(metrics.error_rate)
        assert abs(metrics.error_rate - direct_error) < 1e-9, (
            f"Error rate mismatch: metrics={metrics.error_rate}, direct={direct_error}"
        )

    def test_perfect_predictions_zero_error(self):
        """If all predictions match true labels, error_rate should be 0."""
        sim = make_simulator(n_events=50)
        warmup_size = 5
        evaluator = Evaluator(sim, warmup_size=warmup_size)

        for evt in sim.events:
            is_warmup = evt.sequence < warmup_size
            true_label = sim.get_hidden_label(evt.event_id)
            pred = PredictionRecord(
                event_id=evt.event_id,
                sequence=evt.sequence,
                timestamp=evt.timestamp,
                predicted_label=true_label,
                predicted_proba=float(true_label),
                features=dict(evt.features),
                warmup=is_warmup,
            )
            evaluator.record_prediction(pred)
            if not is_warmup:
                acq = make_acquired(sim, evt.event_id)
                evaluator.deliver_label(acq)

        metrics = evaluator.compute_metrics()
        assert metrics.error_rate == pytest.approx(0.0)

    def test_all_wrong_predictions_full_error(self):
        """If all predictions are wrong, error_rate should be 1.0."""
        sim = make_simulator(n_events=50)
        warmup_size = 5
        evaluator = Evaluator(sim, warmup_size=warmup_size)

        for evt in sim.events:
            is_warmup = evt.sequence < warmup_size
            true_label = sim.get_hidden_label(evt.event_id)
            wrong_label = 1 - true_label
            pred = PredictionRecord(
                event_id=evt.event_id,
                sequence=evt.sequence,
                timestamp=evt.timestamp,
                predicted_label=wrong_label,
                predicted_proba=float(wrong_label),
                features=dict(evt.features),
                warmup=is_warmup,
            )
            evaluator.record_prediction(pred)
            if not is_warmup:
                acq = make_acquired(sim, evt.event_id)
                evaluator.deliver_label(acq)

        metrics = evaluator.compute_metrics()
        assert metrics.error_rate == pytest.approx(1.0)


class TestLabelJoining:
    def test_labels_join_correct_predictions(self):
        sim = make_simulator(n_events=30)
        warmup_size = 5
        evaluator = Evaluator(sim, warmup_size=warmup_size)

        for evt in sim.events:
            is_warmup = evt.sequence < warmup_size
            pred = make_pred(evt, warmup=is_warmup)
            evaluator.record_prediction(pred)

        # Deliver labels in REVERSE order to test ordering independence
        post_warmup = [e for e in sim.events if e.sequence >= warmup_size]
        for evt in reversed(post_warmup):
            acq = make_acquired(sim, evt.event_id)
            evaluator.deliver_label(acq)

        metrics = evaluator.compute_metrics()
        assert metrics.scored_predictions == len(post_warmup)
        assert not math.isnan(metrics.error_rate)


class TestDuplicatePrediction:
    def test_duplicate_prediction_raises(self):
        sim = make_simulator(n_events=10)
        evaluator = Evaluator(sim, warmup_size=2)
        evt = sim.events[5]
        pred = make_pred(evt)
        evaluator.record_prediction(pred)
        with pytest.raises(ValueError, match="Duplicate"):
            evaluator.record_prediction(pred)


class TestEmptyChannelMetrics:
    def test_empty_channel_metrics_return_null(self):
        sim = make_simulator(n_events=30)
        evaluator = Evaluator(sim, warmup_size=10)
        for evt in sim.events:
            is_warmup = evt.sequence < 10
            pred = make_pred(evt, warmup=is_warmup)
            evaluator.record_prediction(pred)

        metrics = evaluator.compute_metrics()
        # No monitor or selective labels were delivered
        assert metrics.monitor_channel.total == 0
        assert metrics.monitor_channel.error_rate is None
        assert metrics.monitor_channel.accuracy is None
        assert metrics.selective_channel.total == 0
        assert metrics.selective_channel.error_rate is None
        assert metrics.selective_channel.accuracy is None

        # Verify JSON serialization represents None as null
        data = metrics.to_dict()
        assert data["monitor_channel"]["error_rate"] is None
        assert data["selective_channel"]["error_rate"] is None


class TestPostDriftSyntheticEvaluation:
    def test_full_synthetic_post_drift_breakdown(self):
        stream_cfg = StreamConfig(
            scenario="abrupt",
            n_events=100,
            drift_start_sequence=50,
            seed=42,
        )
        sim = Simulator(stream_cfg)
        warmup_size = 20
        evaluator = Evaluator(sim, warmup_size=warmup_size, drift_sequence=50)

        for evt in sim.events:
            is_warmup = evt.sequence < warmup_size
            true_label = sim.get_hidden_label(evt.event_id)
            # Before seq 50: correct prediction. After seq 50: wrong prediction.
            pred_label = true_label if evt.sequence < 50 else 1 - true_label
            pred = PredictionRecord(
                event_id=evt.event_id,
                sequence=evt.sequence,
                timestamp=evt.timestamp,
                predicted_label=pred_label,
                predicted_proba=float(pred_label),
                features=dict(evt.features),
                warmup=is_warmup,
            )
            evaluator.record_prediction(pred)

        metrics = evaluator.compute_metrics()
        assert metrics.full_synthetic.total == 80
        assert metrics.pre_drift is not None
        assert metrics.pre_drift.total == 30  # seq 20..49
        assert metrics.pre_drift.error_rate == pytest.approx(0.0)

        assert metrics.post_drift is not None
        assert metrics.post_drift.total == 50  # seq 50..99
        assert metrics.post_drift.error_rate == pytest.approx(1.0)

