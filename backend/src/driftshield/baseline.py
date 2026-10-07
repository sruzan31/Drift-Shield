"""
driftshield.baseline
====================
Logistic-regression baseline classifier for DriftShield Phase 1.

Architecture
------------
* **Preprocessor**: ``StandardScaler`` fitted on warm-up features and then
  frozen.  All subsequent predictions use the same scaling parameters.
* **Classifier**: River ``LogisticRegression`` (SGD) trained on warm-up
  labels.  After warm-up the model is *frozen* — no further updates occur.
  Phase 1 does NOT implement online adaptation; that is a future phase.

Phase 1 limitation
------------------
Because the model is frozen after warm-up, it will experience performance
degradation when concept drift occurs (abrupt scenario).  This is expected
and correct behaviour: the evaluator will measure that degradation.  Do not
interpret a high post-drift error rate as a bug.

Usage
-----
::

    baseline = BaselineClassifier(config.labels)
    for event in warmup_events:
        pred = baseline.predict(event)   # warm-up prediction
        baseline.learn(event_id, label)  # train on warm-up label
    baseline.freeze()

    for event in production_events:
        pred = baseline.predict(event)   # frozen: no further learning
"""

from __future__ import annotations

import copy
from typing import Dict, List, Optional, Tuple

import numpy as np
from river import linear_model, optim, preprocessing

from .config import LabelConfig
from .contracts import PredictionRecord, StreamEvent


class BaselineClassifier:
    """
    Logistic-regression baseline: fit on warm-up, frozen thereafter.

    Parameters
    ----------
    config : LabelConfig
        Used to determine the warm-up window.

    Notes
    -----
    * Preprocessing is fitted incrementally on warm-up data and then frozen.
    * The River ``LogisticRegression`` is trained incrementally on warm-up
      labels and then frozen.
    * ``predict()`` works correctly whether or not the model is frozen.
    * Calling ``learn()`` after ``freeze()`` raises ``RuntimeError``.
    """

    def __init__(self, config: LabelConfig) -> None:
        self._cfg = config
        self._frozen: bool = False
        self._warmup_complete: bool = False

        # Accumulated warm-up data for scaler fitting
        self._warmup_features: List[Dict[str, float]] = []
        self._warmup_labels: List[Tuple[str, int]] = []   # (event_id, label)

        # River scaler — fitted on warm-up, then frozen
        self._scaler = preprocessing.StandardScaler()
        self._scaler_fitted: bool = False

        # River logistic regression (SGD)
        self._lr = linear_model.LogisticRegression(
            optimizer=optim.SGD(lr=0.01),
            l2=1e-4,
            intercept_lr=0.01,
        )
        self.model_version: str = "v1.0-frozen"

        # Buffer for pending warm-up labels (may arrive with delay)
        self._pending_warmup: Dict[str, int] = {}  # event_id -> label
        # Store warm-up features for deferred training
        self._warmup_feature_store: Dict[str, Dict[str, float]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_frozen(self) -> bool:
        """``True`` after ``freeze()`` has been called."""
        return self._frozen

    @property
    def weights(self) -> Dict[str, float]:
        """Dictionary of current model weights."""
        return dict(self._lr.weights)

    @property
    def scaler(self) -> preprocessing.StandardScaler:
        """The fitted preprocessing scaler."""
        return self._scaler

    @property
    def warmup_size(self) -> int:
        """Configured warm-up size."""
        return self._cfg.warmup_size

    def promote_candidate(self, candidate_lr_model: Any, new_model_version: str) -> None:
        """
        Atomically switch the active classifier SGD model to the promoted candidate.

        The preprocessor scaler remains unchanged and frozen.
        """
        self._lr = copy.deepcopy(candidate_lr_model)
        self.model_version = new_model_version

    def predict(self, event: StreamEvent) -> PredictionRecord:
        """
        Predict the label for *event*.

        If the scaler has not been fitted yet (early warm-up), raw features
        are used directly.  This is acceptable because warm-up predictions
        are excluded from reported metrics.

        The prediction is made BEFORE any label for this event is revealed.

        Parameters
        ----------
        event : StreamEvent

        Returns
        -------
        PredictionRecord
        """
        x = event.features

        if self._scaler_fitted:
            x_scaled = self._scaler.transform_one(x)
        else:
            x_scaled = x  # unscaled during very early warm-up

        proba = self._lr.predict_proba_one(x_scaled)
        p1 = proba.get(1, 0.5) if proba else 0.5
        label = int(p1 >= 0.5)

        is_warmup = event.sequence < self._cfg.warmup_size

        return PredictionRecord(
            event_id=event.event_id,
            sequence=event.sequence,
            timestamp=event.timestamp,
            predicted_label=label,
            predicted_proba=float(p1),
            features=dict(event.features),
            warmup=is_warmup,
            model_version=self.model_version,
        )

    def learn(self, event_id: str, true_label: int) -> None:
        """
        Train on one labelled example.

        Parameters
        ----------
        event_id : str
        true_label : int

        Raises
        ------
        RuntimeError
            If called after ``freeze()``.
        """
        if self._frozen:
            raise RuntimeError(
                "BaselineClassifier is frozen; learn() must not be called "
                "after freeze().  Phase 1 does not implement online adaptation."
            )
        # Retrieve features for this event
        features = self._warmup_feature_store.get(event_id)
        if features is None:
            # Store pending label to apply when features arrive
            self._pending_warmup[event_id] = true_label
            return

        self._train_one(features, true_label)

    def register_warmup_features(self, event: StreamEvent) -> None:
        """
        Register warm-up event features for deferred training.

        Must be called for every warm-up event so that ``learn()`` can
        retrieve them later (in case labels arrive with delay).
        """
        self._warmup_feature_store[event.event_id] = dict(event.features)
        # Update scaler incrementally (fitting continues during warm-up)
        if not self._frozen:
            self._scaler.learn_one(event.features)
            self._scaler_fitted = True
        # Apply any pending label
        if event.event_id in self._pending_warmup:
            label = self._pending_warmup.pop(event.event_id)
            self._train_one(event.features, label)

    def freeze(self) -> None:
        """
        Freeze the preprocessor and classifier.

        After this call:
        * ``learn()`` raises ``RuntimeError``.
        * ``predict()`` uses the frozen scaler parameters.

        This must be called after all warm-up labels have been processed.
        """
        if self._frozen:
            return  # idempotent
        self._frozen = True
        self._warmup_complete = True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _train_one(self, features: Dict[str, float], true_label: int) -> None:
        """One SGD update on one example."""
        if self._scaler_fitted:
            x_scaled = self._scaler.transform_one(features)
        else:
            x_scaled = features
        self._lr.learn_one(x_scaled, true_label)
