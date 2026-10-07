"""driftshield.run_baseline
========================
CLI entry point for DriftShield baseline execution, monitoring, candidate training,
paired evaluation/promotion, and SQLite persistence.

Runs two scenarios:
* ``stationary``: no drift.
* ``abrupt``: linear boundary change at the configured sequence.

For each scenario the runner:
1. Instantiates the reusable `DriftShieldEngine` with durable SQLite persistence.
2. Initializes warm-up, preprocessor fitting, and simulator event streaming.
3. Processes all stream events serially through the engine pipeline.
4. Handles alerts, candidate training, paired comparisons, and atomic promotions.
5. Finalizes run state, persists metric windows, and exports CSV/JSON/DB artifacts.

Usage
-----
::

    python -m driftshield.run_baseline [--output-dir PATH] [--delay N]

"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import sys
import time
from typing import List

import numpy as np
import pydantic
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "driftshield"

from .config import AdaptationConfig, DriftShieldConfig, LabelConfig, MonitoringConfig, StreamConfig
from .contracts import CandidateState, EvaluationDecision
from .engine import DriftShieldEngine, get_execution_environment
from .simulator import Simulator


def run_scenario(
    scenario: str,
    cfg: DriftShieldConfig,
    output_dir: str,
) -> dict:
    """
    Run one scenario end-to-end via DriftShieldEngine and return the metrics dict.

    Parameters
    ----------
    scenario : str
        "stationary" or "abrupt"
    cfg : DriftShieldConfig
    output_dir : str
    """
    print(f"\n{'='*65}")
    print(f"  DriftShield Phase 5A — Scenario: {scenario.upper()}")
    print(f"  [SYNTHETIC DATA — not real-world measurements]")
    print(f"{'='*65}")

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Override the scenario in stream config
    stream_cfg = StreamConfig(
        scenario=scenario,
        n_events=cfg.stream.n_events,
        seed=cfg.stream.seed,
        noise_std=cfg.stream.noise_std,
        drift_start_sequence=cfg.stream.drift_start_sequence,
    )

    run_cfg = DriftShieldConfig(
        stream=stream_cfg,
        labels=cfg.labels,
        monitoring=cfg.monitoring,
        adaptation=cfg.adaptation,
        output_dir=output_dir,
    )

    # Build simulator (full truth hidden inside)
    sim = Simulator(stream_cfg, label_delay=cfg.labels.label_delay)
    print(
        f"  Generated {len(sim.events)} events "
        f"(warmup={cfg.labels.warmup_size}, "
        f"label_delay={cfg.labels.label_delay})"
    )
    if sim.drift_sequence is not None:
        print(f"  Drift onset configured at sequence {sim.drift_sequence}")

    # Build reusable engine
    run_id = f"run-{scenario}-{cfg.stream.seed}"
    engine = DriftShieldEngine(
        config=run_cfg,
        run_id=run_id,
        environment=get_execution_environment(),
    )
    engine.initialize(simulator=sim)

    # Track logging state
    budget_exhausted_logged = False
    last_logged_candidate_id = None

    # ----------------------------------------------------------------
    # Stream loop
    # ----------------------------------------------------------------
    for event in sim.iter_events():
        # Log drift onset
        if sim.drift_sequence is not None and event.sequence == sim.drift_sequence:
            print(f"  [DRIFT ONSET] Stream reached sequence {event.sequence} — decision boundary changed")

        # Process through reusable engine
        res = engine.process_event(event)

        # Log alerts
        for alert in res.alerts_triggered:
            print(
                f"  [ALERT] Evidence of error change at arrival seq {alert.arrival_sequence} "
                f"(event seq {alert.event_sequence}, delay={alert.detection_delay_from_event}). "
                f"ADWIN est={alert.adwin_estimation:.4f}, width={alert.adwin_width}"
            )

        # Log candidate initiation
        if engine.candidate_manager.active_candidate is not None:
            ac = engine.candidate_manager.active_candidate
            if ac.candidate_id != last_logged_candidate_id and ac.state == CandidateState.TRAINING:
                last_logged_candidate_id = ac.candidate_id
                print(
                    f"  [CANDIDATE INITIATED] Started Candidate '{ac.candidate_id}' at sequence {ac.creation_sequence} "
                    f"(epoch={ac.epoch}, target={ac.target_training_labels} unique labels)"
                )
            elif (
                ac.state == CandidateState.READY_FOR_EVALUATION
                and ac.freeze_sequence == event.sequence
            ):
                print(
                    f"  [CANDIDATE COMPLETE] Candidate '{ac.candidate_id}' reached target {ac.unique_training_labels} labels. "
                    f"Frozen at sequence {ac.freeze_sequence}. State: READY_FOR_EVALUATION."
                )

        # Log promotions
        for p_ver in res.promotions_triggered:
            sess = engine.paired_evaluator.completed_sessions[-1]
            print(
                f"  [MODEL PROMOTION] Candidate '{sess.candidate_id}' PROMOTED! "
                f"Switching active model to '{p_ver}' "
                f"(gain={sess.gain:.4f}, p-value={sess.p_value:.4e}, b={sess.b}, c={sess.c}, n={sess.n})."
            )

        # Check for initial freeze transition
        if engine.freeze_sequence == event.sequence:
            print(
                f"  [TRANSITION] Warm-up complete ({cfg.labels.warmup_size} events, delay={cfg.labels.label_delay}). "
                f"Initial model frozen at sequence {engine.freeze_sequence}. Evaluation starts at sequence {engine.evaluation_start_sequence}."
            )

        # Check budget exhaustion
        if (
            not res.is_warmup
            and not budget_exhausted_logged
            and engine.acquirer is not None
            and engine.acquirer.budget_remaining == 0
        ):
            print(
                f"  [BUDGET EXHAUSTED] Label budget fully used at sequence {event.sequence} "
                f"({engine.acquirer.budget_used}/{cfg.labels.label_budget})"
            )
            budget_exhausted_logged = True

    # ----------------------------------------------------------------
    # Finalize engine & Export
    # ----------------------------------------------------------------
    summary = engine.finalize()
    exported_paths = engine.export_artifacts(out_path)

    metrics = summary.metrics or {}
    print(f"\n  --- Overall Model Evaluation (Post-Initialization Events) ---")
    print(f"    Active Model Version    : {summary.active_model_version}")
    print(f"    Evaluation Start Seq    : {summary.evaluation_start_sequence}")
    print(f"    Total Events Processed  : {summary.total_events}")
    if "full_synthetic" in metrics:
        fs = metrics["full_synthetic"]
        print(f"    Evaluated Predictions   : {fs['total']}")
        print(f"    Correct Predictions     : {fs['correct']}")
        if fs['error_rate'] is not None:
            print(f"    Total Error Rate        : {fs['error_rate']:.4f} ({fs['error_rate']*100:.1f}%)")
    if "pre_drift" in metrics and metrics["pre_drift"]:
        pd = metrics["pre_drift"]
        err = f"{pd['error_rate']:.4f}" if pd['error_rate'] is not None else "N/A"
        print(f"    Pre-drift Error Rate    : {err} ({pd['correct']}/{pd['total']})")
    if "post_drift" in metrics and metrics["post_drift"]:
        pd = metrics["post_drift"]
        err = f"{pd['error_rate']:.4f}" if pd['error_rate'] is not None else "N/A"
        print(f"    Post-drift Error Rate   : {err} ({pd['correct']}/{pd['total']})")

    print(f"\n  --- Monitoring Channel & ADWIN Detector ---")
    mon = summary.monitoring_summary
    if "monitor_channel" in metrics:
        mc = metrics["monitor_channel"]
        m_err = f"{mc['error_rate']:.4f}" if mc['error_rate'] is not None else "N/A"
        print(f"    Monitor Labels Scored   : {mc['total']}")
        print(f"    Monitor Error Rate      : {m_err}")
    print(f"    Monitoring Coverage     : {mon.get('monitoring_coverage', 0.0):.2%}")
    print(f"    ADWIN Estimation        : {mon.get('current_adwin_estimation', 0.0):.4f}")
    print(f"    ADWIN Window Width      : {mon.get('current_adwin_width', 0)}")
    print(f"    Emitted Alerts Count    : {mon.get('alerts_count', 0)}")

    if "monitoring_evaluation" in metrics and metrics["monitoring_evaluation"]:
        me = metrics["monitoring_evaluation"]
        print(f"\n  --- Independent Alarm Evaluation (Against Synthetic Ground Truth) ---")
        print(f"    False Alarms (Pre-Drift): {me['false_alarms']}")
        print(f"    Missed Detection        : {me['missed_detection']}")
        if me.get('first_alert_event_sequence') is not None:
            print(f"    First Alert Event Seq   : {me['first_alert_event_sequence']}")
            print(f"    First Alert Arrival Seq : {me['first_alert_arrival_sequence']}")
        if me.get('detection_delay_events') is not None:
            print(f"    Detection Delay (Events): {me['detection_delay_events']} stream events from drift onset")
        if me.get('detection_delay_labeled_observations') is not None:
            print(f"    Detection Delay (Labels): {me['detection_delay_labeled_observations']} post-drift monitor observations")

    print(f"\n  --- Adaptation & Candidate Training (Phase 4A) ---")
    cand_summary = summary.candidate_summary
    print(f"    Candidates Spawned      : {cand_summary.get('total_candidates_spawned', 0)}")
    print(f"    Ignored Alerts Count    : {cand_summary.get('ignored_alerts_count', 0)}")
    for c in cand_summary.get("candidates", []):
        print(
            f"    Candidate '{c['candidate_id']}'  : state={c['state']}  "
            f"training_labels={c['unique_training_labels']}/{c['target_training_labels']}  "
            f"epoch={c['epoch']}  freeze_seq={c['freeze_sequence']}"
        )

    print(f"\n  --- Fresh Paired Evaluation & Promotion (Phase 4B) ---")
    paired_summary = summary.paired_summary
    print(f"    Evaluations Started     : {paired_summary.get('total_evaluations_started', 0)}")
    print(f"    Completed Comparisons   : {paired_summary.get('completed_comparisons_count', 0)}/{paired_summary.get('max_comparisons_cap', 5)}")
    for s in paired_summary.get("sessions", []):
        gain_str = f"{s['gain']:.4f}" if s['gain'] is not None else "N/A"
        p_str = f"{s['p_value']:.4e}" if s['p_value'] is not None else "N/A"
        print(
            f"    Session '{s['eval_id']}' ({s['candidate_id']}) : decision={s['decision']}  "
            f"events={s['delivered_labels_count']}/{s['target_events_n']}  "
            f"gain={gain_str}  p-value={p_str}  (b={s['b']}, c={s['c']}, n={s['n']})"
        )

    print(f"\n  --- Saved Artifacts & SQLite Persistence (Phase 5A) ---")
    print(f"    SQLite Database Path    : {engine.storage.db_path}")
    print(f"    Model Artifacts Dir     : {engine.storage.models_dir}")
    for name, pth in exported_paths.items():
        print(f"    {name:22s} : {pth}")

    return metrics


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="DriftShield Phase 5A — reusable engine and SQLite persistence runner."
    )
    parser.add_argument(
        "--scenario",
        choices=["stationary", "abrupt", "both"],
        default="both",
        help="Scenario to run: 'stationary', 'abrupt', or 'both' (default: 'both').",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="Directory for CSV/JSON outputs and SQLite DB (default: outputs).",
    )
    parser.add_argument(
        "--n-events",
        type=int,
        default=2000,
        help="Total events per scenario (default: 2000).",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=200,
        help="Warm-up window size (default: 200).",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=300,
        help="Post-warmup label budget (default: 300).",
    )
    parser.add_argument(
        "--delay",
        "--label-delay",
        dest="delay",
        type=int,
        default=0,
        help="Label delivery delay in steps (default: 0).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Stream seed (default: 42).",
    )
    parser.add_argument(
        "--adwin-delta",
        type=float,
        default=0.002,
        help="ADWIN delta confidence parameter (default: 0.002).",
    )
    parser.add_argument(
        "--target-labels",
        type=int,
        default=200,
        help="Target number of unique labels to train candidate (default: 200).",
    )
    parser.add_argument(
        "--target-eval-events",
        type=int,
        default=500,
        help="Target number of fresh random-monitoring evaluation events (default: 500).",
    )
    parser.add_argument(
        "--drift-start",
        type=int,
        default=None,
        help="Optional sequence for abrupt drift start (default: n_events // 2).",
    )
    args = parser.parse_args(argv)

    drift_start = args.drift_start if args.drift_start is not None else args.n_events // 2

    cfg = DriftShieldConfig(
        stream=StreamConfig(
            n_events=args.n_events,
            seed=args.seed,
            drift_start_sequence=drift_start,
        ),
        labels=LabelConfig(
            warmup_size=args.warmup,
            label_budget=args.budget,
            label_delay=args.delay,
        ),
        monitoring=MonitoringConfig(
            adwin_delta=args.adwin_delta,
        ),
        adaptation=AdaptationConfig(
            target_training_labels=args.target_labels,
            evaluation_target_events=args.target_eval_events,
        ),
        output_dir=args.output_dir,
    )

    scenarios = ["stationary", "abrupt"] if args.scenario == "both" else [args.scenario]
    all_metrics = {}
    for scenario in scenarios:
        m = run_scenario(scenario, cfg, args.output_dir)
        all_metrics[scenario] = m

    # Summary
    print("\n" + "="*65)
    print("  SUMMARY — PHASE 5A REUSABLE ENGINE & PERSISTENCE")
    print("="*65)
    for sc, m in all_metrics.items():
        err_str = f"{m['error_rate']:.4f}" if m.get('error_rate') is not None else "N/A"
        mon_eval = m.get("monitoring_evaluation", {})
        alerts_count = mon_eval.get("total_alerts", 0)
        delay_str = str(mon_eval.get("detection_delay_events", "N/A"))
        print(
            f"  {sc:12s}  error_rate={err_str}  "
            f"alerts={alerts_count}  "
            f"detection_delay={delay_str} events"
        )
    print("\nPhase 5A complete. Engine orchestration and SQLite persistence active.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
