"""Theory Lab: Tight Finite-Domain Exact Adaptation Experiment (T5).

Implements the finite-domain exact adaptation experiment from Section 3 (T5)
and Section 21 (P4/T5) of the DriftShield specification:
- Known finite domain of N distinct inputs X = {0, 1, ..., N-1}.
- Known old binary rule f0(x) (default: f0(x) = 0 for all x).
- Fixed new binary rule f1(x) accessible only through a noiseless membership-label oracle.
- Audit queries every domain input once, storing each authorized answer in a lookup table.
- Exactly N queries suffice and are necessary in the worst case for exact full-domain adaptation.
- Before audit completion, unqueried inputs are unresolved; zero-risk predictions are not advertised.
- Evaluator / Learner isolation: oracle ground truth is hidden from the learner until queried.
"""

from __future__ import annotations

import csv
from enum import Enum
import json
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ScenarioType(str, Enum):
    NO_CHANGE = "no-change"
    SINGLE_LAST = "single-last"
    MULTIPLE = "multiple"
    CUSTOM = "custom"


class FiniteDomainConfig(BaseModel):
    """Configuration for T5 finite-domain exact adaptation experiment."""
    model_config = ConfigDict(frozen=True)

    n_domain: int = Field(
        default=32,
        ge=1,
        description="Finite domain size N (distinct inputs)",
    )
    scenario: ScenarioType = Field(
        default=ScenarioType.NO_CHANGE,
        description="Drift scenario: no-change, single-last, multiple, or custom",
    )
    changed_indices: Optional[List[int]] = Field(
        default=None,
        description="Explicit indices where f1(x) != f0(x). If None, determined by scenario.",
    )
    query_order: Optional[List[int]] = Field(
        default=None,
        description="Explicit permutation of domain indices to query. If None, default 0..N-1 or seeded shuffle.",
    )
    seed: int = Field(
        default=42,
        description="Random seed for randomized query order or scenario generation",
    )

    @field_validator("n_domain")
    @classmethod
    def validate_n_domain(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"Domain size N must be at least 1, got {v}")
        return v


class AuditQueryRecord(BaseModel):
    """Record of an individual membership query during audit."""
    model_config = ConfigDict(frozen=True)

    query_sequence: int  # 1-based query step
    input_id: int
    queried_label: int
    old_rule_label: int
    disagreement_detected: bool
    audit_progress: float
    is_audit_complete: bool
    cumulative_changes_discovered: int


class FiniteDomainResult(BaseModel):
    """Consolidated summary and records of the finite-domain experiment."""
    model_config = ConfigDict(frozen=True)

    config: FiniteDomainConfig
    total_domain_size: int
    queries_completed: int
    is_complete: bool
    unique_label_cost: int
    discovered_change_indices: List[int]
    total_discovered_changes: int

    # Evaluator-only ground truth validation
    evaluator_true_changed_indices: List[int]
    evaluator_total_true_changes: int
    evaluator_all_labels_correct: bool
    first_change_discovery_step: Optional[int] = None

    records: List[AuditQueryRecord] = Field(default_factory=list)


# =====================================================================
# Isolated Membership Oracle (Evaluator-Only)
# =====================================================================

class MembershipOracle:
    """Evaluator-only membership label oracle.

    Holds the true target rule f1: X -> {0, 1} and responds noiselessly
    to point queries.
    """

    def __init__(self, n_domain: int, changed_indices: Set[int], f0_val: int = 0) -> None:
        self.n_domain = n_domain
        self.changed_indices = set(changed_indices)
        self.f0_val = f0_val
        self._queries_count = 0
        self._queried_inputs: Set[int] = set()

    def query(self, input_id: int) -> int:
        """Query the label for input_id."""
        if not (0 <= input_id < self.n_domain):
            raise ValueError(f"input_id {input_id} out of domain [0, {self.n_domain - 1}]")

        self._queries_count += 1
        self._queried_inputs.add(input_id)

        # f1(x) differs from f0(x) on changed_indices
        if input_id in self.changed_indices:
            return 1 - self.f0_val
        return self.f0_val

    @property
    def queries_count(self) -> int:
        return self._queries_count

    @property
    def unique_queries_count(self) -> int:
        return len(self._queried_inputs)


# =====================================================================
# Learner: Finite Domain Auditor & Lookup Predictor
# =====================================================================

class FiniteDomainAuditor:
    """Learner that audits a finite domain of N inputs via membership queries.

    Maintains an acquired lookup table.
    Unqueried inputs remain unresolved before audit completion.
    """

    def __init__(self, n_domain: int, f0: Optional[Callable[[int], int]] = None) -> None:
        if n_domain < 1:
            raise ValueError(f"Domain size must be >= 1, got {n_domain}")
        self.n_domain = n_domain
        self.f0 = f0 if f0 is not None else (lambda x: 0)
        self._lookup_table: Dict[int, int] = {}
        self._discovered_changes: List[int] = []

    @property
    def is_complete(self) -> bool:
        """Audit is complete if and only if all N distinct domain inputs are queried."""
        return len(self._lookup_table) == self.n_domain

    @property
    def queries_completed(self) -> int:
        return len(self._lookup_table)

    @property
    def discovered_changes(self) -> List[int]:
        return list(self._discovered_changes)

    @property
    def lookup_table(self) -> Dict[int, int]:
        return dict(self._lookup_table)

    def record_query(self, input_id: int, label: int) -> Tuple[bool, bool]:
        """Record an authorized query response.

        Returns (is_disagreement, is_complete).
        """
        if not (0 <= input_id < self.n_domain):
            raise ValueError(f"input_id {input_id} out of domain [0, {self.n_domain - 1}]")
        if label not in (0, 1):
            raise ValueError(f"Label must be 0 or 1, got {label}")
        if input_id in self._lookup_table:
            raise ValueError(f"Duplicate query for input_id {input_id}")

        self._lookup_table[input_id] = label
        old_val = self.f0(input_id)
        is_disagreement = (label != old_val)
        if is_disagreement:
            self._discovered_changes.append(input_id)

        return is_disagreement, self.is_complete

    def predict(self, input_id: int) -> Optional[int]:
        """Predict label for input_id.

        Returns:
        - Exact label if input_id was queried in lookup table.
        - None (unresolved) if input_id has not been queried.
        """
        if not (0 <= input_id < self.n_domain):
            raise ValueError(f"input_id {input_id} out of domain [0, {self.n_domain - 1}]")
        return self._lookup_table.get(input_id, None)

    def predict_strict(self, input_id: int) -> int:
        """Strict prediction requiring completed audit.

        Raises RuntimeError if audit is incomplete.
        """
        if not self.is_complete:
            raise RuntimeError(
                f"Audit incomplete ({len(self._lookup_table)}/{self.n_domain} inputs queried). "
                "Exact zero-risk predictions are only available after complete audit."
            )
        return self._lookup_table[input_id]


# =====================================================================
# Experiment Runner
# =====================================================================

class FiniteDomainExperiment:
    """Executes the T5 Finite-Domain Audit and Exact Adaptation Experiment."""

    def __init__(self, config: FiniteDomainConfig) -> None:
        self.config = config

    def _resolve_changed_indices(self) -> Set[int]:
        """Resolve true changed indices based on scenario configuration."""
        N = self.config.n_domain
        if self.config.changed_indices is not None:
            for idx in self.config.changed_indices:
                if not (0 <= idx < N):
                    raise ValueError(f"changed_index {idx} out of domain [0, {N - 1}]")
            return set(self.config.changed_indices)

        if self.config.scenario == ScenarioType.NO_CHANGE:
            return set()
        elif self.config.scenario == ScenarioType.SINGLE_LAST:
            # Change is on the element that is queried last
            query_order = self._resolve_query_order()
            last_input = query_order[-1]
            return {last_input}
        elif self.config.scenario == ScenarioType.MULTIPLE:
            # Deterministic subset of changed indices (e.g. ~25% of domain)
            rng = np.random.default_rng(self.config.seed)
            k = max(2, N // 4)
            chosen = rng.choice(N, size=k, replace=False)
            return set(int(x) for x in chosen)
        elif self.config.scenario == ScenarioType.CUSTOM:
            return set()
        else:
            raise ValueError(f"Unknown scenario {self.config.scenario}")

    def _resolve_query_order(self) -> List[int]:
        """Resolve the sequence of domain queries."""
        N = self.config.n_domain
        if self.config.query_order is not None:
            if len(self.config.query_order) != N or set(self.config.query_order) != set(range(N)):
                raise ValueError(f"query_order must be a permutation of 0..{N - 1}")
            return list(self.config.query_order)

        # Standard canonical order 0..N-1
        return list(range(N))

    def run(self) -> FiniteDomainResult:
        """Run the complete N-query audit and evaluate exact adaptation."""
        N = self.config.n_domain
        query_order = self._resolve_query_order()
        true_changes = self._resolve_changed_indices()

        # Instantiate evaluator-only oracle and learner
        oracle = MembershipOracle(n_domain=N, changed_indices=true_changes, f0_val=0)
        auditor = FiniteDomainAuditor(n_domain=N, f0=lambda x: 0)

        records: List[AuditQueryRecord] = []
        first_change_step: Optional[int] = None

        for step_1based, input_id in enumerate(query_order, start=1):
            # 1. Oracle reveals noiseless label for queried input
            label = oracle.query(input_id)
            old_label = auditor.f0(input_id)

            # 2. Auditor updates lookup table
            is_disagreement, is_complete = auditor.record_query(input_id, label)

            if is_disagreement and first_change_step is None:
                first_change_step = step_1based

            record = AuditQueryRecord(
                query_sequence=step_1based,
                input_id=input_id,
                queried_label=label,
                old_rule_label=old_label,
                disagreement_detected=is_disagreement,
                audit_progress=step_1based / N,
                is_audit_complete=is_complete,
                cumulative_changes_discovered=len(auditor.discovered_changes),
            )
            records.append(record)

        # Evaluator-only verification of complete lookup table vs true target rule
        all_correct = True
        for x in range(N):
            pred = auditor.predict(x)
            true_label = 1 if (x in true_changes) else 0
            if pred != true_label:
                all_correct = False
                break

        return FiniteDomainResult(
            config=self.config,
            total_domain_size=N,
            queries_completed=auditor.queries_completed,
            is_complete=auditor.is_complete,
            unique_label_cost=oracle.unique_queries_count,
            discovered_change_indices=sorted(auditor.discovered_changes),
            total_discovered_changes=len(auditor.discovered_changes),
            evaluator_true_changed_indices=sorted(list(true_changes)),
            evaluator_total_true_changes=len(true_changes),
            evaluator_all_labels_correct=all_correct,
            first_change_discovery_step=first_change_step,
            records=records,
        )

    def export(self, result: FiniteDomainResult, output_dir: Path) -> Tuple[Path, Path]:
        """Export audit_records.csv and summary.json."""
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / "audit_records.csv"
        json_path = output_dir / "summary.json"

        # 1. CSV
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "query_sequence",
                "input_id",
                "queried_label",
                "old_rule_label",
                "disagreement_detected",
                "audit_progress",
                "is_audit_complete",
                "cumulative_changes_discovered",
            ])
            for r in result.records:
                writer.writerow([
                    r.query_sequence,
                    r.input_id,
                    r.queried_label,
                    r.old_rule_label,
                    r.disagreement_detected,
                    f"{r.audit_progress:.4f}",
                    r.is_audit_complete,
                    r.cumulative_changes_discovered,
                ])

        # 2. JSON
        summary_dict = {
            "parameters": {
                "n_domain": result.config.n_domain,
                "scenario": result.config.scenario.value,
                "seed": result.config.seed,
            },
            "audit_summary": {
                "total_domain_size": result.total_domain_size,
                "queries_completed": result.queries_completed,
                "is_complete": result.is_complete,
                "unique_label_cost": result.unique_label_cost,
                "discovered_change_indices": result.discovered_change_indices,
                "total_discovered_changes": result.total_discovered_changes,
                "first_change_discovery_step": result.first_change_discovery_step,
            },
            "evaluator_verification": {
                "evaluator_true_changed_indices": result.evaluator_true_changed_indices,
                "evaluator_total_true_changes": result.evaluator_total_true_changes,
                "evaluator_all_labels_correct": result.evaluator_all_labels_correct,
            },
        }

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary_dict, f, indent=2)

        return csv_path, json_path
