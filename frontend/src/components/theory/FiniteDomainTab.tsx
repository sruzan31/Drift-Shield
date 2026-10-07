import React, { useEffect, useState } from 'react';
import {
  CheckCircle2,
  Download,
  FastForward,
  Pause,
  Play,
  RotateCcw,
  Sliders,
  StepForward,
  Terminal,
} from 'lucide-react';
import { api } from '../../lib/api';
import type { CreateFiniteDomainRequest, FiniteDomainResults, TheoryExperimentDetail } from '../../types';

interface FiniteDomainTabProps {
  experiment: TheoryExperimentDetail | null;
  isRunning: boolean;
  onLaunchExperiment: (payload: CreateFiniteDomainRequest) => void;
}

export const FiniteDomainTab: React.FC<FiniteDomainTabProps> = ({
  experiment,
  isRunning,
  onLaunchExperiment,
}) => {
  const [nDomain, setNDomain] = useState<number>(32);
  const [scenario, setScenario] = useState<'no-change' | 'single-last' | 'multiple'>('single-last');
  const [seed, setSeed] = useState<number>(42);

  // Playback state
  const [playbackStep, setPlaybackStep] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);

  const results = experiment?.results as FiniteDomainResults | undefined;
  const isCompleted = experiment?.status === 'COMPLETED' && !!results;

  // Auto-reset playback step when results change
  useEffect(() => {
    if (results?.records) {
      setPlaybackStep(results.records.length);
      setIsPlaying(false);
    }
  }, [results]);

  // Playback timer loop
  useEffect(() => {
    if (!isPlaying || !results?.records) return;

    const interval = setInterval(() => {
      setPlaybackStep((prev) => {
        if (prev >= results.records.length) {
          setIsPlaying(false);
          return prev;
        }
        return prev + 1;
      });
    }, 200);

    return () => clearInterval(interval);
  }, [isPlaying, results]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onLaunchExperiment({
      mode: 'finite-domain',
      n_domain: nDomain,
      scenario,
      seed,
    });
  };

  const currentRecords = results?.records.slice(0, playbackStep) || [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Configuration Form */}
      <form onSubmit={handleSubmit} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
          <div style={{ fontWeight: 600, fontSize: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Sliders size={16} color="var(--cobalt-600)" />
            T5 Finite-Domain Exact Adaptation Parameters
          </div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
            Look-up table adaptation under noiseless membership queries
          </div>
        </div>

        <div className="grid-3">
          <div className="form-group">
            <label className="form-label">Domain Size (N)</label>
            <input
              type="number"
              className="form-input"
              value={nDomain}
              min={2}
              max={256}
              step="any"
              onChange={(e) => setNDomain(parseInt(e.target.value, 10) || 32)}
              required
            />
            <span className="form-help">Distinct inputs X = &#123;0, 1, ..., N-1&#125;</span>
          </div>

          <div className="form-group">
            <label className="form-label">Concept Drift Scenario</label>
            <select
              className="form-select"
              value={scenario}
              onChange={(e) => setScenario(e.target.value as any)}
            >
              <option value="single-last">Single-Last Drift (Only index N-1 changed)</option>
              <option value="multiple">Multiple Dispersed Changes</option>
              <option value="no-change">No-Change Baseline (f1 = f0)</option>
            </select>
            <span className="form-help">Target rule f1(x) difference pattern</span>
          </div>

          <div className="form-group">
            <label className="form-label">RNG Seed</label>
            <input
              type="number"
              className="form-input"
              value={seed}
              step="any"
              onChange={(e) => setSeed(parseInt(e.target.value, 10) || 42)}
              required
            />
            <span className="form-help">Deterministic query permutation seed</span>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', borderTop: '1px solid var(--border-subtle)', paddingTop: '1rem' }}>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={isRunning}
          >
            <Play size={14} />
            {isRunning ? 'Executing Oracle Audit...' : 'Run T5 Finite-Domain Audit'}
          </button>
        </div>
      </form>

      {/* Results Presentation */}
      {isCompleted && results && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* Top Metrics Cards */}
          <div className="grid-3">
            <div className="card" style={{ padding: '1.25rem' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Audit Queries Completed
              </div>
              <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--cobalt-600)', marginTop: '0.5rem' }}>
                {results.queries_completed} / {results.total_domain_size}
              </div>
              <div style={{ marginTop: '0.75rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                Unique Label Cost: <strong>{results.unique_label_cost} labels</strong> (exactly N).
              </div>
            </div>

            <div className="card" style={{ padding: '1.25rem' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Audit Status & Discovered Drift
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.5rem' }}>
                <CheckCircle2 size={20} color="var(--success-600)" />
                <span style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  {results.is_complete ? 'Audit Complete' : 'Incomplete'}
                </span>
              </div>
              <div style={{ marginTop: '0.75rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                Discovered Changes: <strong>{results.total_discovered_changes} inputs</strong> ({results.discovered_change_indices.join(', ') || 'None'})
              </div>
            </div>

            <div className="card" style={{ padding: '1.25rem' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Evaluator Post-Audit Verification
              </div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--success-600)', marginTop: '0.5rem' }}>
                {results.evaluator_all_labels_correct ? '100% Exact Accuracy' : 'Incomplete / Error'}
              </div>
              <div style={{ marginTop: '0.75rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                All domain labels verified after the complete audit (under fixed-target, noiseless-oracle assumptions).
              </div>
            </div>
          </div>

          {/* Interactive Recorded Playback Animation */}
          <div className="card" style={{ padding: '1.25rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1rem' }}>
              <div>
                <div style={{ fontWeight: 600, fontSize: '0.9375rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Terminal size={16} color="var(--cobalt-600)" />
                  Audit Step Animation (Recorded Playback)
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  Step-by-step visual playback of verified membership query records. Unqueried inputs remain unresolved.
                </div>
              </div>

              {/* Playback Controls */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => {
                    setIsPlaying(false);
                    setPlaybackStep(0);
                  }}
                  title="Reset Playback"
                >
                  <RotateCcw size={13} />
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => setIsPlaying(!isPlaying)}
                >
                  {isPlaying ? <Pause size={13} /> : <Play size={13} />} {isPlaying ? 'Pause' : 'Play'}
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => {
                    setIsPlaying(false);
                    setPlaybackStep((prev) => Math.min(results.records.length, prev + 1));
                  }}
                  disabled={playbackStep >= results.records.length}
                >
                  <StepForward size={13} /> Step
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => {
                    setIsPlaying(false);
                    setPlaybackStep(results.records.length);
                  }}
                  disabled={playbackStep >= results.records.length}
                >
                  <FastForward size={13} /> End
                </button>
              </div>
            </div>

            {/* Playback Progress Bar */}
            <div style={{ marginBottom: '1.25rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', marginBottom: '0.25rem', color: 'var(--text-secondary)' }}>
                <span>Step {playbackStep} of {results.records.length} queries</span>
                <span>{((playbackStep / results.records.length) * 100).toFixed(1)}% complete</span>
              </div>
              <div className="progress-bar-bg">
                <div
                  className="progress-bar-fill"
                  style={{ width: `${(playbackStep / results.records.length) * 100}%` }}
                />
              </div>
            </div>

            {/* Domain Grid Cell Visualizer */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Finite Domain Cells (N = {results.total_domain_size})
              </div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(36px, 1fr))',
                  gap: '6px',
                  maxHeight: '220px',
                  overflowY: 'auto',
                  padding: '0.5rem',
                  backgroundColor: 'var(--bg-surface-subtle)',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                {Array.from({ length: results.total_domain_size }).map((_, idx) => {
                  const queryRec = currentRecords.find((r) => r.input_id === idx);
                  const isQueried = !!queryRec;
                  const isChange = queryRec?.disagreement_detected;

                  let bgColor = 'var(--bg-surface)';
                  let textColor = 'var(--text-muted)';
                  let borderColor = 'var(--border-subtle)';

                  if (isQueried) {
                    if (isChange) {
                      bgColor = 'var(--amber-100)';
                      textColor = 'var(--amber-800)';
                      borderColor = 'var(--amber-400)';
                    } else {
                      bgColor = 'var(--success-50)';
                      textColor = 'var(--success-700)';
                      borderColor = 'var(--success-300)';
                    }
                  }

                  return (
                    <div
                      key={idx}
                      style={{
                        height: '36px',
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        backgroundColor: bgColor,
                        color: textColor,
                        border: `1px solid ${borderColor}`,
                        borderRadius: 'var(--radius-sm)',
                        fontSize: '0.6875rem',
                        fontWeight: 600,
                        transition: 'all 0.15s ease',
                      }}
                      title={
                        isQueried
                          ? `Input ${idx}: Queried label=${queryRec.queried_label} (Baseline=${queryRec.old_rule_label})`
                          : `Input ${idx}: Unqueried (Unresolved)`
                      }
                    >
                      <span>x_{idx}</span>
                      <span style={{ fontSize: '0.625rem', opacity: isQueried ? 1 : 0.4 }}>
                        {isQueried ? (isChange ? 'Δ' : '✓') : '?'}
                      </span>
                    </div>
                  );
                })}
              </div>

              <div style={{ display: 'flex', gap: '1.25rem', marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                  <span style={{ width: '10px', height: '10px', backgroundColor: 'var(--success-50)', border: '1px solid var(--success-300)', display: 'inline-block' }} />
                  <span>Queried Agreement (f1 = f0)</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                  <span style={{ width: '10px', height: '10px', backgroundColor: 'var(--amber-100)', border: '1px solid var(--amber-400)', display: 'inline-block' }} />
                  <span>Queried Disagreement (f1 != f0)</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                  <span style={{ width: '10px', height: '10px', backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', display: 'inline-block' }} />
                  <span>Unqueried (Unresolved)</span>
                </div>
              </div>
            </div>
          </div>

          {/* Audit Records Table */}
          <div className="card" style={{ padding: '1.25rem' }}>
            <div style={{ fontWeight: 600, fontSize: '0.9375rem', marginBottom: '0.75rem' }}>
              Membership Query Audit Log ({results.records.length} Records)
            </div>
            <div className="table-container" style={{ maxHeight: '280px', overflowY: 'auto' }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Seq #</th>
                    <th>Input ID</th>
                    <th>Queried Label f1(x)</th>
                    <th>Baseline Label f0(x)</th>
                    <th>Disagreement</th>
                    <th>Cumulative Drift Count</th>
                  </tr>
                </thead>
                <tbody>
                  {results.records.map((r) => (
                    <tr key={r.query_sequence}>
                      <td><strong>#{r.query_sequence}</strong></td>
                      <td><code>x_{r.input_id}</code></td>
                      <td>
                        <span className={`badge ${r.queried_label === 1 ? 'badge-amber' : 'badge-green'}`}>
                          y = {r.queried_label}
                        </span>
                      </td>
                      <td><code>f0 = {r.old_rule_label}</code></td>
                      <td>
                        {r.disagreement_detected ? (
                          <span className="badge badge-red">Concept Shift</span>
                        ) : (
                          <span className="badge badge-green">Match</span>
                        )}
                      </td>
                      <td>{r.cumulative_changes_discovered}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Export Actions */}
          <div className="card" style={{ padding: '1rem 1.25rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
            <div style={{ fontSize: '0.875rem' }}>
              <strong>Durable Artifacts:</strong> Audit records saved to <code>{experiment.artifacts_dir}</code>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <a
                href={api.getTheoryExportUrl(experiment.experiment_id, 'json')}
                download={`${experiment.experiment_id}_summary.json`}
                className="btn btn-secondary btn-sm"
              >
                <Download size={14} /> Export Summary JSON
              </a>
              <a
                href={api.getTheoryExportUrl(experiment.experiment_id, 'csv')}
                download={`${experiment.experiment_id}_audit_records.csv`}
                className="btn btn-secondary btn-sm"
              >
                <Download size={14} /> Export Audit CSV
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
