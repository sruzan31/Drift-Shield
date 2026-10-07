import React, { useState } from 'react';
import {
  Clock,
  Download,
  Play,
  Sliders,
} from 'lucide-react';
import { api } from '../../lib/api';
import type { CreateRareRegionRequest, RareRegionResults, TheoryExperimentDetail } from '../../types';

interface RareRegionTabProps {
  experiment: TheoryExperimentDetail | null;
  isRunning: boolean;
  onLaunchExperiment: (payload: CreateRareRegionRequest) => void;
}

export const RareRegionTab: React.FC<RareRegionTabProps> = ({
  experiment,
  isRunning,
  onLaunchExperiment,
}) => {
  const [p, setP] = useState<number>(0.05);
  const [q, setQ] = useState<number>(0.20);
  const [deadline, setDeadline] = useState<number>(100);
  const [delta, setDelta] = useState<number>(0.05);
  const [trials, setTrials] = useState<number>(10000);
  const [seed, setSeed] = useState<number>(42);
  const [noChange, setNoChange] = useState<boolean>(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onLaunchExperiment({
      mode: 'rare-region',
      p,
      q,
      deadline,
      delta,
      trials,
      seed,
      no_change: noChange,
    });
  };

  const results = experiment?.results as RareRegionResults | undefined;
  const isCompleted = experiment?.status === 'COMPLETED' && !!results;

  // Generate SVG curve points for theoretical miss probability vs deadline
  const renderTheoreticalChart = () => {
    if (!results) return null;

    const qVal = results.parameters.q;
    const pVal = results.parameters.p;
    const dVal = results.parameters.deadline;
    const r = qVal * pVal;

    const maxD = Math.max(dVal * 2, 20);
    const width = 600;
    const height = 180;
    const padding = { top: 20, right: 30, bottom: 30, left: 50 };

    const plotW = width - padding.left - padding.right;
    const plotH = height - padding.top - padding.bottom;

    // Build theoretical curve path
    const points: [number, number][] = [];
    const steps = 60;
    for (let i = 0; i <= steps; i++) {
      const curD = (i / steps) * maxD;
      const missProb = r <= 0 ? 1 : Math.exp(curD * Math.log1p(-r));
      const x = padding.left + (curD / maxD) * plotW;
      const y = padding.top + (1 - missProb) * plotH;
      points.push([x, y]);
    }

    const pathD = points.map((pt, i) => `${i === 0 ? 'M' : 'L'} ${pt[0].toFixed(1)} ${pt[1].toFixed(1)}`).join(' ');

    // Empirical point location
    const empD = dVal;
    const empMiss = results.empirical.miss_frequency;
    const empX = padding.left + (empD / maxD) * plotW;
    const empY = padding.top + (1 - empMiss) * plotH;

    // Minimum deadline line
    const minD = results.theoretical.min_deadline_for_delta;
    const minDX = minD !== null && minD <= maxD ? padding.left + (minD / maxD) * plotW : null;

    return (
      <div style={{ marginTop: '1rem' }}>
        <div style={{ fontSize: '0.8125rem', fontWeight: 600, marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>
          Theoretical Miss Probability Curve $(1 - qp)^D$ vs Empirical Trial Observation
        </div>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          style={{
            width: '100%',
            height: 'auto',
            backgroundColor: 'var(--bg-surface-subtle)',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          {/* Grid lines */}
          <line x1={padding.left} y1={padding.top} x2={width - padding.right} y2={padding.top} stroke="var(--border-subtle)" strokeDasharray="3 3" />
          <line x1={padding.left} y1={padding.top + plotH / 2} x2={width - padding.right} y2={padding.top + plotH / 2} stroke="var(--border-subtle)" strokeDasharray="3 3" />
          <line x1={padding.left} y1={padding.top + plotH} x2={width - padding.right} y2={padding.top + plotH} stroke="var(--border-subtle)" />

          {/* Y Axis Labels */}
          <text x={padding.left - 8} y={padding.top + 4} fill="var(--text-muted)" fontSize="10" textAnchor="end">1.0</text>
          <text x={padding.left - 8} y={padding.top + plotH / 2 + 4} fill="var(--text-muted)" fontSize="10" textAnchor="end">0.5</text>
          <text x={padding.left - 8} y={padding.top + plotH + 4} fill="var(--text-muted)" fontSize="10" textAnchor="end">0.0</text>

          {/* X Axis Labels */}
          <text x={padding.left} y={height - 8} fill="var(--text-muted)" fontSize="10" textAnchor="start">D=0</text>
          <text x={padding.left + plotW / 2} y={height - 8} fill="var(--text-muted)" fontSize="10" textAnchor="middle">D={Math.round(maxD / 2)}</text>
          <text x={width - padding.right} y={height - 8} fill="var(--text-muted)" fontSize="10" textAnchor="end">D={Math.round(maxD)}</text>

          {/* Min Deadline Vertical Marker */}
          {minDX !== null && (
            <>
              <line x1={minDX} y1={padding.top} x2={minDX} y2={padding.top + plotH} stroke="var(--amber-500)" strokeDasharray="4 3" strokeWidth="1.5" />
              <text x={minDX + 4} y={padding.top + 14} fill="var(--amber-600)" fontSize="9" fontWeight="600">D*={minD}</text>
            </>
          )}

          {/* Theoretical Curve */}
          <path d={pathD} fill="none" stroke="var(--cobalt-600)" strokeWidth="2" />

          {/* Empirical Observation Point */}
          <circle cx={empX} cy={empY} r="5" fill="var(--danger-500)" stroke="white" strokeWidth="1.5" />
        </svg>

        <div style={{ display: 'flex', gap: '1.5rem', justifyContent: 'center', marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
            <span style={{ width: '12px', height: '2px', backgroundColor: 'var(--cobalt-600)', display: 'inline-block' }} />
            <span>Theoretical (1-qp)^D</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--danger-500)', display: 'inline-block' }} />
            <span>Empirical P_miss ({results.empirical.miss_frequency.toFixed(4)})</span>
          </div>
          {minD !== null && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
              <span style={{ width: '12px', height: '2px', borderTop: '2px dashed var(--amber-500)', display: 'inline-block' }} />
              <span>Min Deadline D*(delta={results.parameters.delta})</span>
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Parameter Controls Form */}
      <form onSubmit={handleSubmit} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
          <div style={{ fontWeight: 600, fontSize: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Sliders size={16} color="var(--cobalt-600)" />
            T4 Rare-Region Experiment Parameters
          </div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
            Effective discovery rate r = q · p = {(q * p).toFixed(4)}
          </div>
        </div>

        <div className="grid-3">
          <div className="form-group">
            <label className="form-label">Disagreement Mass (p)</label>
            <input
              type="number"
              className="form-input"
              value={p}
              min={0.001}
              max={1.0}
              step="any"
              onChange={(e) => setP(parseFloat(e.target.value) || 0.05)}
              required
            />
            <span className="form-help">Fraction of feature space where concept differs</span>
          </div>

          <div className="form-group">
            <label className="form-label">Query Probability (q)</label>
            <input
              type="number"
              className="form-input"
              value={q}
              min={0.001}
              max={1.0}
              step="any"
              onChange={(e) => setQ(parseFloat(e.target.value) || 0.20)}
              required
            />
            <span className="form-help">Independent random labeling query rate</span>
          </div>

          <div className="form-group">
            <label className="form-label">Observation Deadline (D)</label>
            <input
              type="number"
              className="form-input"
              value={deadline}
              min={1}
              max={10000}
              step="any"
              onChange={(e) => setDeadline(parseInt(e.target.value, 10) || 100)}
              required
            />
            <span className="form-help">Stream event budget to catch disagreement</span>
          </div>
        </div>

        <div className="grid-3">
          <div className="form-group">
            <label className="form-label">Target Miss Delta (δ)</label>
            <input
              type="number"
              className="form-input"
              value={delta}
              min={0.001}
              max={0.999}
              step="any"
              onChange={(e) => setDelta(parseFloat(e.target.value) || 0.05)}
              required
            />
            <span className="form-help">Desired error ceiling for minimum deadline D*</span>
          </div>

          <div className="form-group">
            <label className="form-label">Independent Trials (n)</label>
            <input
              type="number"
              className="form-input"
              value={trials}
              min={10}
              max={100000}
              step="any"
              onChange={(e) => setTrials(parseInt(e.target.value, 10) || 10000)}
              required
            />
            <span className="form-help">Number of independent empirical runs</span>
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
            <span className="form-help">Deterministic seed for exact replay</span>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--border-subtle)', paddingTop: '1rem', flexWrap: 'wrap', gap: '1rem' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.875rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={noChange}
              onChange={(e) => setNoChange(e.target.checked)}
            />
            <span><strong>No-Change Baseline:</strong> Run with f1(x) = f0(x) to verify zero false alarms</span>
          </label>

          <button
            type="submit"
            className="btn btn-primary"
            disabled={isRunning}
          >
            <Play size={14} />
            {isRunning ? 'Running Mathematical Trials...' : 'Run T4 Rare-Region Experiment'}
          </button>
        </div>
      </form>

      {/* Results Presentation */}
      {isCompleted && results && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* Top Metric Cards */}
          <div className="grid-3">
            {/* Miss Probability */}
            <div className="card" style={{ padding: '1.25rem' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Miss Probability at $D={results.parameters.deadline}$
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.75rem', marginTop: '0.5rem' }}>
                <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  {(results.empirical.miss_frequency * 100).toFixed(2)}%
                </div>
                <div style={{ fontSize: '0.8125rem', color: 'var(--cobalt-600)' }}>
                  Theory: {(results.theoretical.miss_probability * 100).toFixed(2)}%
                </div>
              </div>
              <div style={{ marginTop: '0.75rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                95% Wilson CI: <strong>[{(results.empirical.confidence_interval_95[0] * 100).toFixed(2)}%, {(results.empirical.confidence_interval_95[1] * 100).toFixed(2)}%]</strong> across {results.empirical.trials_count.toLocaleString()} trials.
              </div>
            </div>

            {/* Minimum Deadline D* */}
            <div className="card" style={{ padding: '1.25rem' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Min Deadline for $\delta={results.parameters.delta}$
              </div>
              <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--amber-600)', marginTop: '0.5rem' }}>
                {results.theoretical.min_deadline_for_delta !== null
                  ? `${results.theoretical.min_deadline_for_delta} events`
                  : 'Undefined (qp=0)'}
              </div>
              <div style={{ marginTop: '0.75rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                Formula: ceil(ln(1/delta) / -ln(1-qp)). Guarantees P_miss &le; {results.parameters.delta}.
              </div>
            </div>

            {/* Labels Acquired */}
            <div className="card" style={{ padding: '1.25rem' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Mean Labels Acquired
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.75rem', marginTop: '0.5rem' }}>
                <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--success-600)' }}>
                  {results.empirical.mean_labels_acquired.toFixed(2)}
                </div>
                <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                  Theory: {results.theoretical.expected_acquired_labels.toFixed(2)}
                </div>
              </div>
              <div style={{ marginTop: '0.75rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                Total labels across all trials: {results.empirical.total_labels_acquired.toLocaleString()}
              </div>
            </div>
          </div>

          {/* Expected Times Distinction Card */}
          <div className="card" style={{ padding: '1.25rem' }}>
            <div style={{ fontWeight: 600, fontSize: '0.9375rem', marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Clock size={16} color="var(--cobalt-600)" />
              Detection Time Statistics: Uncensored vs Conditional Expectations
            </div>
            <div className="grid-3" style={{ fontSize: '0.8125rem' }}>
              <div style={{ backgroundColor: 'var(--bg-surface-subtle)', padding: '0.875rem', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Uncensored $E[T] = 1/(qp)$</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--cobalt-600)', margin: '0.25rem 0' }}>
                  {results.theoretical.uncensored_expected_detection_time !== null
                    ? `${results.theoretical.uncensored_expected_detection_time.toFixed(1)} events`
                    : 'N/A'}
                </div>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                  Expected arrival of first queried disagreement without deadline truncation.
                </div>
              </div>

              <div style={{ backgroundColor: 'var(--bg-surface-subtle)', padding: '0.875rem', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Conditional $E[T \mid T \le D]$</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--cobalt-600)', margin: '0.25rem 0' }}>
                  {results.theoretical.conditional_expected_detection_time !== null
                    ? `${results.theoretical.conditional_expected_detection_time.toFixed(1)} events`
                    : 'N/A'}
                </div>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                  Theoretical average detection time given detection occurs before deadline $D$.
                </div>
              </div>

              <div style={{ backgroundColor: 'var(--bg-surface-subtle)', padding: '0.875rem', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Empirical Mean Detection Delay</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--success-600)', margin: '0.25rem 0' }}>
                  {results.empirical.mean_detection_delay !== null
                    ? `${results.empirical.mean_detection_delay.toFixed(1)} events`
                    : 'No detections'}
                </div>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                  Average 1-based stream event count upon alert across detected trials.
                </div>
              </div>
            </div>
          </div>

          {/* Theoretical Curve Visualization */}
          <div className="card" style={{ padding: '1.25rem' }}>
            {renderTheoreticalChart()}
          </div>

          {/* Export Action Bar */}
          <div className="card" style={{ padding: '1rem 1.25rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
            <div style={{ fontSize: '0.875rem' }}>
              <strong>Durable Artifacts:</strong> Results and trial records persisted under <code>{experiment.artifacts_dir}</code>
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
                download={`${experiment.experiment_id}_trials.csv`}
                className="btn btn-secondary btn-sm"
              >
                <Download size={14} /> Export Trials CSV
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
