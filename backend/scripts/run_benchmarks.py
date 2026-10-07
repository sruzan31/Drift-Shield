"""
DriftShield Phase 7B Benchmark and Performance Measurement Suite
================================================================
Generates reproducible benchmarks, measures prediction latencies,
throughput, WebSocket timing boundaries, and concurrent Theory Lab isolation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import time
from typing import Any, Dict, List

import numpy as np

from driftshield.config import (
    AdaptationConfig,
    DriftShieldConfig,
    LabelConfig,
    MonitoringConfig,
    StreamConfig,
)
from driftshield.contracts import CandidateState
from driftshield.engine import DriftShieldEngine
from driftshield.simulator import Simulator
from driftshield.storage import SQLiteStorage
from driftshield.theory.rare_region import RareRegionExperiment
from driftshield.theory.finite_domain import FiniteDomainAuditor


ROOT_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUTS_DIR = ROOT_DIR / "outputs" / "phase7b_benchmarks"


def get_system_specs() -> Dict[str, Any]:
    return {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
    }


def run_streaming_benchmark(
    name: str,
    config: DriftShieldConfig,
    target_dir: Path,
) -> Dict[str, Any]:
    print(f"\n--- Running Benchmark: {name} ---")
    target_dir.mkdir(parents=True, exist_ok=True)
    db_path = target_dir / f"{name}.db"
    art_path = target_dir / "artifacts"
    if db_path.exists():
        db_path.unlink()

    # Save run config
    config_file = target_dir / "config.json"
    with open(config_file, "w") as f:
        f.write(config.model_dump_json(indent=2))

    storage = SQLiteStorage(db_path=db_path, artifacts_dir=art_path)
    sim = Simulator(config.stream, label_delay=config.labels.label_delay)
    engine = DriftShieldEngine(config=config, storage=storage)

    # Latency tracking
    pure_prediction_latencies_us: List[float] = []
    step_latencies_us: List[float] = []

    engine.initialize(simulator=sim)

    t_start = time.perf_counter()
    for event in sim.iter_events():
        # 1. Pure model inference timing
        tp0 = time.perf_counter()
        _ = engine.baseline.predict(event)
        tp1 = time.perf_counter()
        pure_prediction_latencies_us.append((tp1 - tp0) * 1_000_000.0)

        # 2. Full engine step timing
        t0 = time.perf_counter()
        snapshot = engine.process_event(event)
        t1 = time.perf_counter()
        step_latencies_us.append((t1 - t0) * 1_000_000.0)

    t_end = time.perf_counter()
    summary = engine.finalize()

    elapsed_s = t_end - t_start
    events_count = config.stream.n_events
    throughput_eps = events_count / elapsed_s if elapsed_s > 0 else 0.0

    # Collect metrics
    stats = engine.acquirer.get_channel_stats()
    metrics = engine.evaluator.compute_metrics(
        label_acquisition=stats,
        alerts=engine.monitor.alerts,
    )

    p_lat = np.array(step_latencies_us)
    pred_lat = np.array(pure_prediction_latencies_us)

    timing_metrics = {
        "events_count": events_count,
        "elapsed_seconds": elapsed_s,
        "observed_throughput_eps": throughput_eps,
        "pure_prediction_latency_us": {
            "mean": float(np.mean(pred_lat)),
            "p50": float(np.percentile(pred_lat, 50)),
            "p95": float(np.percentile(pred_lat, 95)),
            "p99": float(np.percentile(pred_lat, 99)),
        },
        "engine_step_duration_us": {
            "mean": float(np.mean(p_lat)),
            "p50": float(np.percentile(p_lat, 50)),
            "p95": float(np.percentile(p_lat, 95)),
            "p99": float(np.percentile(p_lat, 99)),
        },
        "timing_boundaries_documented": {
            "pure_prediction": "Time for active_model.predict_proba(features) alone.",
            "engine_step": "In-memory event prediction, label delivery joining, ADWIN update, candidate SGD step, and snapshot assembly.",
            "excluded_from_step": "REST HTTP serialization, TCP transit, network lag, and browser React DOM rendering.",
        },
    }

    from dataclasses import asdict

    results = {
        "benchmark_name": name,
        "scenario": config.stream.scenario,
        "seed": config.stream.seed,
        "system_specs": get_system_specs(),
        "timing_metrics": timing_metrics,
        "run_summary": asdict(summary),
        "evaluator_metrics": metrics.to_dict(),
    }

    results_file = target_dir / "results.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)

    # Export predictions CSV
    preds_csv = target_dir / "predictions.csv"
    preds = engine.evaluator.get_all_predictions()
    if preds:
        import csv
        with open(preds_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(preds[0].keys()))
            writer.writeheader()
            writer.writerows(preds)

    print(
        f"Completed {name}: observed throughput = {throughput_eps:.1f} eps, "
        f"predict p50 = {timing_metrics['pure_prediction_latency_us']['p50']:.1f} us, "
        f"step p50 = {timing_metrics['engine_step_duration_us']['p50']:.1f} us"
    )
    return results


from driftshield.theory.rare_region import RareRegionConfig, RareRegionExperiment
from driftshield.theory.finite_domain import FiniteDomainConfig, FiniteDomainExperiment, ScenarioType


def run_t4_experiment(target_dir: Path) -> Dict[str, Any]:
    print("\n--- Running Theory T4 Rare-Region Experiment ---")
    target_dir.mkdir(parents=True, exist_ok=True)
    cfg = RareRegionConfig(
        p=0.05,
        q=0.20,
        deadline=100,
        delta=0.05,
        trials=10000,
        seed=42,
    )
    exp = RareRegionExperiment(config=cfg)
    t0 = time.perf_counter()
    result = exp.run()
    t1 = time.perf_counter()

    summary = result.model_dump()
    results = {
        "experiment": "T4_Rare_Region",
        "parameters": cfg.model_dump(),
        "execution_time_seconds": t1 - t0,
        "summary": summary,
    }
    with open(target_dir / "results.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"Completed T4: empirical_det={summary['empirical_detection_frequency']:.4f}, theoretical_det={summary['theoretical_detection_probability']:.4f}, time={t1-t0:.2f}s")
    return results


def run_t5_experiment(target_dir: Path) -> Dict[str, Any]:
    print("\n--- Running Theory T5 Finite-Domain Audit ---")
    target_dir.mkdir(parents=True, exist_ok=True)
    cfg = FiniteDomainConfig(
        n_domain=32,
        scenario=ScenarioType.SINGLE_LAST,
        seed=42,
    )
    exp = FiniteDomainExperiment(config=cfg)
    t0 = time.perf_counter()
    result = exp.run()
    t1 = time.perf_counter()

    summary = result.model_dump()
    results = {
        "experiment": "T5_Finite_Domain",
        "parameters": cfg.model_dump(),
        "execution_time_seconds": t1 - t0,
        "summary": summary,
    }
    with open(target_dir / "results.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"Completed T5: is_complete={summary['is_complete']}, queries={summary['queries_completed']}, all_correct={summary['evaluator_all_labels_correct']}, time={t1-t0:.4f}s")
    return results


def run_concurrent_workload_benchmark(target_dir: Path) -> Dict[str, Any]:
    print("\n--- Running Concurrent Workload Benchmark (Streaming + Theory Lab CPU Load) ---")
    target_dir.mkdir(parents=True, exist_ok=True)
    import concurrent.futures
    from dataclasses import asdict

    cfg = DriftShieldConfig(
        stream=StreamConfig(scenario="abrupt", n_events=5000, drift_start_sequence=1000, seed=42),
        labels=LabelConfig(warmup_size=200, label_budget=1000, monitor_rate=0.15, label_delay=0),
        adaptation=AdaptationConfig(
            target_training_labels=200,
            evaluation_target_events=500,
            min_gain_threshold=0.02,
        ),
        output_dir=str(target_dir),
    )
    db_path = target_dir / "concurrent_run.db"
    art_path = target_dir / "artifacts"
    if db_path.exists():
        db_path.unlink()

    # Save run config
    with open(target_dir / "config.json", "w") as f:
        f.write(cfg.model_dump_json(indent=2))

    storage = SQLiteStorage(db_path=db_path, artifacts_dir=art_path)
    sim = Simulator(cfg.stream)
    engine = DriftShieldEngine(config=cfg, storage=storage)
    engine.initialize(simulator=sim)

    pure_prediction_latencies_us: List[float] = []
    step_latencies_us: List[float] = []

    # Spawn Theory Lab heavy experiment in thread pool
    t_start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        t4_future = executor.submit(
            lambda: RareRegionExperiment(
                RareRegionConfig(p=0.02, q=0.10, deadline=100, delta=0.05, trials=20000, seed=123)
            ).run()
        )

        for event in sim.iter_events():
            tp0 = time.perf_counter()
            _ = engine.baseline.predict(event)
            tp1 = time.perf_counter()
            pure_prediction_latencies_us.append((tp1 - tp0) * 1_000_000.0)

            t0 = time.perf_counter()
            engine.process_event(event)
            t1 = time.perf_counter()
            step_latencies_us.append((t1 - t0) * 1_000_000.0)

        summary = engine.finalize()
        t4_res = t4_future.result()

    t_end = time.perf_counter()
    elapsed = t_end - t_start
    throughput = 5000 / elapsed if elapsed > 0 else 0.0

    stats = engine.acquirer.get_channel_stats()
    metrics = engine.evaluator.compute_metrics(
        label_acquisition=stats,
        alerts=engine.monitor.alerts,
    )

    p_lat = np.array(step_latencies_us)
    pred_lat = np.array(pure_prediction_latencies_us)

    timing_metrics = {
        "events_count": 5000,
        "elapsed_seconds": elapsed,
        "observed_throughput_eps": throughput,
        "pure_prediction_latency_us": {
            "mean": float(np.mean(pred_lat)),
            "p50": float(np.percentile(pred_lat, 50)),
            "p95": float(np.percentile(pred_lat, 95)),
            "p99": float(np.percentile(pred_lat, 99)),
        },
        "engine_step_duration_us": {
            "mean": float(np.mean(p_lat)),
            "p50": float(np.percentile(p_lat, 50)),
            "p95": float(np.percentile(p_lat, 95)),
            "p99": float(np.percentile(p_lat, 99)),
        },
        "timing_boundaries_documented": {
            "pure_prediction": "Time for active_model.predict_proba(features) alone.",
            "engine_step": "In-memory event prediction, label delivery joining, ADWIN update, candidate SGD step, and snapshot assembly.",
            "excluded_from_step": "REST HTTP serialization, TCP transit, network lag, and browser React DOM rendering.",
        },
    }

    # Regression check on promotion timeline
    for cand in summary.candidate_summary.get("candidates", []):
        freeze_seq = cand.get("freeze_sequence")
        if freeze_seq is not None:
            assert freeze_seq <= 5000, f"Freeze sequence {freeze_seq} > 5000"
        for t in cand.get("state_transitions", []):
            if t.get("to_state") == "PROMOTED":
                assert t.get("sequence", 0) <= 5000, f"Promotion sequence {t.get('sequence')} > total events 5000"

    results = {
        "benchmark_name": "concurrent_workload",
        "concurrent_streaming_events": 5000,
        "theory_trials_executed": 20000,
        "theory_completed": bool(t4_res),
        "scenario": cfg.stream.scenario,
        "seed": cfg.stream.seed,
        "system_specs": get_system_specs(),
        "timing_metrics": timing_metrics,
        "run_summary": asdict(summary),
        "evaluator_metrics": metrics.to_dict(),
    }

    with open(target_dir / "results.json", "w") as f:
        json.dump(results, f, indent=2)

    with open(target_dir / "concurrent_results.json", "w") as f:
        json.dump(
            {
                "concurrent_streaming_events": 5000,
                "theory_trials_executed": 20000,
                "elapsed_seconds": elapsed,
                "achieved_streaming_throughput_eps": throughput,
                "streaming_completed_state": summary.state,
                "theory_completed": bool(t4_res),
            },
            f,
            indent=2,
        )

    preds_csv = target_dir / "predictions.csv"
    preds = engine.evaluator.get_all_predictions()
    if preds:
        import csv
        with open(preds_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(preds[0].keys()))
            writer.writeheader()
            writer.writerows(preds)

    print(
        f"Completed Concurrent Benchmark: streaming throughput = {throughput:.1f} eps during 20,000 trial Theory load, "
        f"step p50 = {timing_metrics['engine_step_duration_us']['p50']:.1f} us"
    )
    return results


def main() -> None:
    print(f"Starting Phase 7B Comprehensive Benchmark Suite on {platform.machine()} ({platform.system()})")
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Stationary Monitoring
    cfg_stationary = DriftShieldConfig(
        stream=StreamConfig(scenario="stationary", n_events=2000, seed=42),
        labels=LabelConfig(warmup_size=200, label_budget=300, monitor_rate=0.10, label_delay=0),
        monitoring=MonitoringConfig(adwin_delta=0.002),
        output_dir=str(OUTPUTS_DIR / "1_stationary"),
    )
    run_streaming_benchmark("stationary_monitoring", cfg_stationary, OUTPUTS_DIR / "1_stationary")

    # 2. Abrupt Drift with Candidate Evaluation and Promotion
    cfg_abrupt = DriftShieldConfig(
        stream=StreamConfig(scenario="abrupt", n_events=10000, drift_start_sequence=1000, seed=42),
        labels=LabelConfig(warmup_size=200, label_budget=1500, monitor_rate=0.15, label_delay=0),
        monitoring=MonitoringConfig(adwin_delta=0.002),
        adaptation=AdaptationConfig(
            target_training_labels=200,
            evaluation_target_events=500,
            min_gain_threshold=0.02,
        ),
        output_dir=str(OUTPUTS_DIR / "2_abrupt_promotion"),
    )
    run_streaming_benchmark("abrupt_promotion", cfg_abrupt, OUTPUTS_DIR / "2_abrupt_promotion")

    # 3. Delayed-Label Adaptation (delay = 10)
    cfg_delayed = DriftShieldConfig(
        stream=StreamConfig(scenario="abrupt", n_events=10000, drift_start_sequence=1000, seed=42),
        labels=LabelConfig(warmup_size=200, label_budget=1500, monitor_rate=0.15, label_delay=10),
        monitoring=MonitoringConfig(adwin_delta=0.002),
        adaptation=AdaptationConfig(
            target_training_labels=200,
            evaluation_target_events=500,
            min_gain_threshold=0.02,
        ),
        output_dir=str(OUTPUTS_DIR / "3_delayed_adaptation"),
    )
    run_streaming_benchmark("delayed_adaptation", cfg_delayed, OUTPUTS_DIR / "3_delayed_adaptation")

    # 4. Challenging Scenario: Rare Region Stealth Drift (p = 0.03)
    cfg_challenging = DriftShieldConfig(
        stream=StreamConfig(
            scenario="rare_region",
            rare_region_p=0.03,
            n_events=10000,
            drift_start_sequence=1000,
            seed=42,
        ),
        labels=LabelConfig(warmup_size=200, label_budget=1500, monitor_rate=0.10, label_delay=0),
        monitoring=MonitoringConfig(adwin_delta=0.002),
        adaptation=AdaptationConfig(
            target_training_labels=200,
            evaluation_target_events=500,
            min_gain_threshold=0.02,
        ),
        output_dir=str(OUTPUTS_DIR / "4_challenging_rare_region"),
    )
    run_streaming_benchmark("challenging_rare_region", cfg_challenging, OUTPUTS_DIR / "4_challenging_rare_region")

    # 5. Theory T4 Rare-Region
    run_t4_experiment(OUTPUTS_DIR / "5_theory_t4_rare_region")

    # 6. Theory T5 Finite-Domain Audit
    run_t5_experiment(OUTPUTS_DIR / "6_theory_t5_finite_domain")

    # 7. Concurrent Workload Benchmark
    run_concurrent_workload_benchmark(OUTPUTS_DIR / "7_concurrent_workload")

    print("\n=======================================================")
    print(f"All Phase 7B benchmarks successfully executed and saved to:")
    print(f"{OUTPUTS_DIR}")
    print("=======================================================\n")


if __name__ == "__main__":
    main()
