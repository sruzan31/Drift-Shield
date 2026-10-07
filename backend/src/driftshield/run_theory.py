"""CLI runner for the DriftShield Theory Lab: T4 Rare-Region and T5 Finite-Domain Experiments."""

import argparse
from pathlib import Path
import sys

from driftshield.theory.finite_domain import (
    FiniteDomainConfig,
    FiniteDomainExperiment,
    ScenarioType,
)
from driftshield.theory.rare_region import (
    RareRegionConfig,
    RareRegionExperiment,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run DriftShield Theory Lab Experiments (T4 Rare-Region and T5 Finite-Domain)."
    )
    parser.add_argument(
        "--mode",
        choices=["rare-region", "finite-domain"],
        default="rare-region",
        help="Experiment mode: rare-region (T4) or finite-domain (T5) (default: rare-region)",
    )

    # --- T4 Rare-Region Arguments ---
    parser.add_argument(
        "--p",
        type=float,
        default=0.05,
        help="Disagreement mass / rare region size for T4 (default: 0.05)",
    )
    parser.add_argument(
        "--q",
        type=float,
        default=0.20,
        help="Independent random label query probability per event for T4 (default: 0.20)",
    )
    parser.add_argument(
        "-D",
        "--deadline",
        type=int,
        default=100,
        help="Observation deadline D in events for T4 (default: 100)",
    )
    parser.add_argument(
        "--delta",
        type=float,
        default=0.05,
        help="Target miss probability delta for T4 (default: 0.05)",
    )
    parser.add_argument(
        "-n",
        "--trials",
        type=int,
        default=10000,
        help="Number of independent trials for T4 (default: 10000)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Master random seed (default: 42)",
    )
    parser.add_argument(
        "--query-seed",
        type=int,
        default=None,
        help="Optional distinct seed for query RNG (default: seed + 1000000)",
    )
    parser.add_argument(
        "--no-change",
        action="store_true",
        help="Run no-change baseline (f0 only) to verify zero false alarms",
    )

    # --- T5 Finite-Domain Arguments ---
    parser.add_argument(
        "-N",
        "--n-domain",
        type=int,
        default=32,
        help="Finite domain size N for T5 (default: 32)",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        choices=["no-change", "single-last", "multiple"],
        default=None,
        help="Scenario for T5: no-change, single-last, or multiple (default: no-change)",
    )

    # --- Output ---
    parser.add_argument(
        "-o",
        "--output-dir",
        "--output-path",
        dest="output_dir",
        type=str,
        default=None,
        help="Output directory for CSV records and summary.json",
    )
    return parser.parse_args()


def run_rare_region(args: argparse.Namespace) -> int:
    output_dir_str = args.output_dir or "outputs/theory_rare_region"
    try:
        config = RareRegionConfig(
            p=args.p,
            q=args.q,
            deadline=args.deadline,
            delta=args.delta,
            trials=args.trials,
            seed=args.seed,
            query_seed=args.query_seed,
            no_change=args.no_change,
        )
    except Exception as e:
        print(f"Configuration Error: {e}", file=sys.stderr)
        return 1

    print("=================================================================")
    print(" DriftShield Theory Lab: T4 Rare-Region Detection Experiment")
    print("=================================================================")
    print(f"Parameters: p={config.p}, q={config.q}, D={config.deadline}, delta={config.delta}")
    print(f"Trials: {config.trials}, Seed: {config.seed}, Query Seed: {config.query_seed or (config.seed + 1_000_000)}")
    print(f"Mode: {'No-change baseline (f0 only)' if config.no_change else 'Post-drift regime (f1 with rare region)'}")
    print("-----------------------------------------------------------------")

    experiment = RareRegionExperiment(config)
    result = experiment.run()

    print("\n--- Theoretical Predictions ---")
    print(f"Theoretical Miss Probability (1 - q*p)^D      : {result.theoretical_miss_probability:.6f}")
    print(f"Theoretical Detection Probability              : {result.theoretical_detection_probability:.6f}")
    if result.min_deadline is not None:
        print(f"Minimum Deadline D* for delta={config.delta}        : {result.min_deadline}")
    if result.uncensored_expected_detection_time is not None:
        print(f"Uncensored Expected Detection Time 1/(q*p)     : {result.uncensored_expected_detection_time:.2f} events")
    if result.conditional_expected_detection_time is not None:
        print(f"Conditional Detection Mean E[T | T <= D]       : {result.conditional_expected_detection_time:.6f} events")
    print(f"Expected Observation Time E[min(T, D)]         : {result.expected_observation_time:.6f} events")
    print(f"Expected Acquired Labels                       : {result.expected_acquired_labels:.6f} labels")

    print("\n--- Empirical Results ---")
    print(f"Trials Conducted              : {result.trials_count}")
    print(f"Observed Detections           : {result.empirical_detection_count} ({result.empirical_detection_frequency:.4%})")
    print(f"Observed Misses               : {result.empirical_miss_count} ({result.empirical_miss_frequency:.4%})")
    print(f"95% Wilson Confidence Interval: [{result.ci_lower:.6f}, {result.ci_upper:.6f}]")
    if result.mean_detection_delay is not None:
        print(f"Mean Detection Delay (events) : {result.mean_detection_delay:.2f} (1-based stream event count)")
    print(f"Mean Observation Time (events): {result.mean_observation_time:.2f}")
    print(f"Mean Labels Acquired / Trial  : {result.mean_labels_acquired:.2f}")
    print(f"Total Labels Acquired         : {result.total_labels_acquired}")

    output_dir = Path(output_dir_str)
    csv_path, json_path = experiment.export(result, output_dir)
    print("\n--- Export Artifacts ---")
    print(f"Trial Records CSV : {csv_path}")
    print(f"Summary JSON      : {json_path}")
    print("=================================================================\n")
    return 0


def run_finite_domain(args: argparse.Namespace) -> int:
    scenario_val = args.scenario or "no-change"
    output_dir_str = args.output_dir or f"outputs/theory_finite_domain_{scenario_val}"
    try:
        config = FiniteDomainConfig(
            n_domain=args.n_domain,
            scenario=ScenarioType(scenario_val),
            seed=args.seed,
        )
    except Exception as e:
        print(f"Configuration Error: {e}", file=sys.stderr)
        return 1

    print("=================================================================")
    print(" DriftShield Theory Lab: T5 Finite-Domain Audit & Adaptation")
    print("=================================================================")
    print(f"Domain Size N: {config.n_domain}, Scenario: {config.scenario.value}, Seed: {config.seed}")
    print("-----------------------------------------------------------------")

    experiment = FiniteDomainExperiment(config)
    result = experiment.run()

    print("\n--- Audit Summary ---")
    print(f"Total Domain Size N              : {result.total_domain_size}")
    print(f"Queries Completed                : {result.queries_completed}/{result.total_domain_size}")
    print(f"Audit Status                     : {'COMPLETE' if result.is_complete else 'INCOMPLETE'}")
    print(f"Unique Label Cost                : {result.unique_label_cost}")
    print(f"Discovered Changes Count         : {result.total_discovered_changes}")
    print(f"Discovered Changed Indices       : {result.discovered_change_indices}")
    if result.first_change_discovery_step is not None:
        print(f"First Change Discovered At Step  : {result.first_change_discovery_step}")
    else:
        print("First Change Discovered At Step  : None (no changes detected)")

    print("\n--- Evaluator-Only Ground Truth Verification ---")
    print(f"True Changed Indices in Target   : {result.evaluator_true_changed_indices}")
    print(f"Total True Changes in Target     : {result.evaluator_total_true_changes}")
    print(f"All Domain Labels Match Target   : {result.evaluator_all_labels_correct}")

    output_dir = Path(output_dir_str)
    csv_path, json_path = experiment.export(result, output_dir)
    print("\n--- Export Artifacts ---")
    print(f"Audit Records CSV : {csv_path}")
    print(f"Summary JSON      : {json_path}")
    print("=================================================================\n")
    return 0


def main() -> int:
    args = parse_args()
    if args.mode == "finite-domain":
        return run_finite_domain(args)
    else:
        return run_rare_region(args)


if __name__ == "__main__":
    sys.exit(main())
