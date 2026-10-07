"""Unit and integration tests for T5 Finite-Domain Exact Adaptation Experiment."""

import json
from pathlib import Path
import pytest

from driftshield.theory.finite_domain import (
    AuditQueryRecord,
    FiniteDomainAuditor,
    FiniteDomainConfig,
    FiniteDomainExperiment,
    FiniteDomainResult,
    MembershipOracle,
    ScenarioType,
)


class TestMembershipOracle:
    def test_oracle_queries_and_changes(self) -> None:
        oracle = MembershipOracle(n_domain=5, changed_indices={2, 4}, f0_val=0)
        assert oracle.query(0) == 0
        assert oracle.query(1) == 0
        assert oracle.query(2) == 1
        assert oracle.query(3) == 0
        assert oracle.query(4) == 1
        assert oracle.queries_count == 5
        assert oracle.unique_queries_count == 5

    def test_invalid_input_raises(self) -> None:
        oracle = MembershipOracle(n_domain=5, changed_indices=set())
        with pytest.raises(ValueError, match="out of domain"):
            oracle.query(5)
        with pytest.raises(ValueError, match="out of domain"):
            oracle.query(-1)


class TestFiniteDomainAuditor:
    def test_unqueried_inputs_unresolved(self) -> None:
        auditor = FiniteDomainAuditor(n_domain=4, f0=lambda x: 0)
        assert not auditor.is_complete
        assert auditor.queries_completed == 0

        # Unqueried input returns None
        assert auditor.predict(0) is None
        assert auditor.predict(1) is None

        # predict_strict raises RuntimeError when incomplete
        with pytest.raises(RuntimeError, match="Audit incomplete"):
            auditor.predict_strict(0)

    def test_audit_completion_exact_n_queries(self) -> None:
        auditor = FiniteDomainAuditor(n_domain=3, f0=lambda x: 0)
        # Step 1
        is_dis, is_comp = auditor.record_query(input_id=0, label=0)
        assert not is_dis and not is_comp and not auditor.is_complete
        assert auditor.predict(0) == 0
        assert auditor.predict(1) is None

        # Step 2
        is_dis, is_comp = auditor.record_query(input_id=1, label=1)
        assert is_dis and not is_comp and not auditor.is_complete
        assert auditor.predict(1) == 1

        # Step 3
        is_dis, is_comp = auditor.record_query(input_id=2, label=0)
        assert not is_dis and is_comp and auditor.is_complete
        assert auditor.queries_completed == 3

        # Full lookup table verified
        assert auditor.predict_strict(0) == 0
        assert auditor.predict_strict(1) == 1
        assert auditor.predict_strict(2) == 0
        assert auditor.discovered_changes == [1]

    def test_duplicate_query_raises(self) -> None:
        auditor = FiniteDomainAuditor(n_domain=3)
        auditor.record_query(input_id=0, label=0)
        with pytest.raises(ValueError, match="Duplicate query"):
            auditor.record_query(input_id=0, label=0)

    def test_invalid_label_or_domain_raises(self) -> None:
        auditor = FiniteDomainAuditor(n_domain=3)
        with pytest.raises(ValueError, match="out of domain"):
            auditor.record_query(input_id=5, label=0)
        with pytest.raises(ValueError, match="Label must be 0 or 1"):
            auditor.record_query(input_id=1, label=2)


class TestFiniteDomainExperiment:
    def test_scenario_no_change(self) -> None:
        config = FiniteDomainConfig(n_domain=32, scenario=ScenarioType.NO_CHANGE)
        exp = FiniteDomainExperiment(config)
        res = exp.run()

        assert res.total_domain_size == 32
        assert res.queries_completed == 32
        assert res.is_complete
        assert res.unique_label_cost == 32
        assert res.total_discovered_changes == 0
        assert res.discovered_change_indices == []
        assert res.evaluator_total_true_changes == 0
        assert res.evaluator_all_labels_correct
        assert res.first_change_discovery_step is None

    def test_scenario_single_last_not_discovered_early(self) -> None:
        # N=32, change only on index queried last (index 31)
        config = FiniteDomainConfig(n_domain=32, scenario=ScenarioType.SINGLE_LAST)
        exp = FiniteDomainExperiment(config)
        res = exp.run()

        assert res.total_domain_size == 32
        assert res.queries_completed == 32
        assert res.is_complete
        assert res.total_discovered_changes == 1
        assert res.discovered_change_indices == [31]
        assert res.first_change_discovery_step == 32  # Exactly on the 32nd query

        # Verify steps 1..31 showed no disagreement
        for r in res.records[:31]:
            assert not r.disagreement_detected
            assert r.cumulative_changes_discovered == 0
            assert not r.is_audit_complete

        # Step 32 discovered the change and completed the audit
        last_rec = res.records[31]
        assert last_rec.disagreement_detected
        assert last_rec.cumulative_changes_discovered == 1
        assert last_rec.is_audit_complete
        assert res.evaluator_all_labels_correct

    def test_scenario_multiple_changes(self) -> None:
        config = FiniteDomainConfig(n_domain=32, scenario=ScenarioType.MULTIPLE, seed=42)
        exp = FiniteDomainExperiment(config)
        res = exp.run()

        assert res.total_domain_size == 32
        assert res.queries_completed == 32
        assert res.is_complete
        assert res.total_discovered_changes > 1
        assert res.discovered_change_indices == res.evaluator_true_changed_indices
        assert res.evaluator_all_labels_correct

    def test_export_consistency(self, tmp_path: Path) -> None:
        config = FiniteDomainConfig(n_domain=32, scenario=ScenarioType.MULTIPLE, seed=42)
        exp = FiniteDomainExperiment(config)
        res = exp.run()

        csv_path, json_path = exp.export(res, tmp_path)
        assert csv_path.exists()
        assert json_path.exists()

        with open(json_path, "r", encoding="utf-8") as f:
            summary = json.load(f)

        assert summary["parameters"]["n_domain"] == 32
        assert summary["audit_summary"]["queries_completed"] == 32
        assert summary["audit_summary"]["is_complete"] is True
        assert summary["evaluator_verification"]["evaluator_all_labels_correct"] is True

        with open(csv_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 33  # header + 32 queries
