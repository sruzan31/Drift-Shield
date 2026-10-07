import React from 'react';
import { BarChart2, AlertCircle } from 'lucide-react';
import type { ClassificationMetric } from '../types';

interface MetricsCardProps {
  metrics?: Record<string, ClassificationMetric> | null;
  isComplete: boolean;
}

export const MetricsCard: React.FC<MetricsCardProps> = ({ metrics, isComplete }) => {
  const fullSynth = metrics?.full_synthetic;
  const randMon = metrics?.random_monitoring;

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">
          <BarChart2 size={16} color="var(--cobalt-600)" />
          Classification Metrics & Evaluation Windows
        </span>
        <span className="badge badge-neutral" style={{ fontSize: '0.6875rem' }}>
          Exact Denominators
        </span>
      </div>

      {!isComplete || !metrics ? (
        <div
          style={{
            padding: '1.5rem 1rem',
            textAlign: 'center',
            backgroundColor: 'var(--bg-surface-subtle)',
            borderRadius: 'var(--radius-sm)',
            border: '1px dashed var(--border-subtle)',
          }}
        >
          <AlertCircle size={20} color="var(--text-muted)" style={{ margin: '0 auto 0.5rem auto' }} />
          <div style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>
            Evaluation Windows Pending
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            Final classification error metrics are calculated and recorded to SQLite upon run completion or explicit stop.
          </div>
        </div>
      ) : (
        <div className="grid-2">
          {/* Full Synthetic Ground Truth Reference */}
          <div
            style={{
              padding: '1rem',
              backgroundColor: 'var(--bg-surface-subtle)',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
              <span style={{ fontWeight: 600, fontSize: '0.875rem', color: 'var(--text-primary)' }}>
                Full Synthetic Reference
              </span>
              <span className="badge badge-info" style={{ fontSize: '0.6875rem' }}>
                Evaluator Truth
              </span>
            </div>

            {fullSynth && fullSynth.error_rate !== null ? (
              <>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--cobalt-700)', marginBottom: '0.5rem' }}>
                  {(fullSynth.error_rate * 100).toFixed(2)}%
                  <span style={{ fontSize: '0.75rem', fontWeight: 400, color: 'var(--text-muted)', marginLeft: '0.5rem' }}>
                    Cumulative Error
                  </span>
                </div>

                <div className="kv-list">
                  <div className="kv-row">
                    <span className="kv-key">Sample Count:</span>
                    <span className="kv-val">{fullSynth.sample_count}</span>
                  </div>
                  <div className="kv-row">
                    <span className="kv-key">Correct Predictions:</span>
                    <span className="kv-val" style={{ color: 'var(--success-text)' }}>{fullSynth.correct_count}</span>
                  </div>
                  <div className="kv-row">
                    <span className="kv-key">Incorrect Predictions:</span>
                    <span className="kv-val" style={{ color: 'var(--danger-text)' }}>{fullSynth.incorrect_count}</span>
                  </div>
                  <div className="kv-row">
                    <span className="kv-key">Population Denominator:</span>
                    <span className="kv-val">{fullSynth.denominator}</span>
                  </div>
                </div>
              </>
            ) : (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.8125rem' }}>Unavailable</div>
            )}
          </div>

          {/* Random Monitoring Sample Estimate */}
          <div
            style={{
              padding: '1rem',
              backgroundColor: 'var(--bg-surface-subtle)',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
              <span style={{ fontWeight: 600, fontSize: '0.875rem', color: 'var(--text-primary)' }}>
                Random Monitoring Channel
              </span>
              <span className="badge badge-success" style={{ fontSize: '0.6875rem' }}>
                Sample Estimate (q)
              </span>
            </div>

            {randMon && randMon.error_rate !== null ? (
              <>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
                  {(randMon.error_rate * 100).toFixed(2)}%
                  <span style={{ fontSize: '0.75rem', fontWeight: 400, color: 'var(--text-muted)', marginLeft: '0.5rem' }}>
                    Observed Loss Mean
                  </span>
                </div>

                <div className="kv-list">
                  <div className="kv-row">
                    <span className="kv-key">Acquired Monitoring Labels:</span>
                    <span className="kv-val">{randMon.sample_count}</span>
                  </div>
                  <div className="kv-row">
                    <span className="kv-key">Correct:</span>
                    <span className="kv-val" style={{ color: 'var(--success-text)' }}>{randMon.correct_count}</span>
                  </div>
                  <div className="kv-row">
                    <span className="kv-key">Incorrect (ADWIN updates):</span>
                    <span className="kv-val" style={{ color: 'var(--danger-text)' }}>{randMon.incorrect_count}</span>
                  </div>
                  <div className="kv-row">
                    <span className="kv-key">Sample Denominator:</span>
                    <span className="kv-val">{randMon.denominator}</span>
                  </div>
                </div>
              </>
            ) : (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.8125rem' }}>Unavailable</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
