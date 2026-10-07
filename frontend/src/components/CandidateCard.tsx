import React from 'react';
import { Cpu } from 'lucide-react';
import type { CandidateSummary, PairedSummary } from '../types';
import { StatusBadge } from './StatusBadge';

interface CandidateCardProps {
  candidateState?: string | null;
  candidateSummary?: CandidateSummary | null;
  pairedSummary?: PairedSummary | null;
  activeModelVersion: string;
}

export const CandidateCard: React.FC<CandidateCardProps> = ({
  candidateState,
  candidateSummary,
  pairedSummary,
  activeModelVersion,
}) => {
  const currentCand = candidateSummary?.candidates?.[candidateSummary.candidates.length - 1];
  const currentSession = pairedSummary?.sessions?.[pairedSummary.sessions.length - 1];

  const candStateNorm = (candidateState || currentCand?.state || 'NONE').toUpperCase();

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">
          <Cpu size={16} color="var(--cobalt-600)" />
          Candidate Adaptation & Statistical Evaluation
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Active Model:</span>
          <span className="badge badge-info">{activeModelVersion}</span>
        </div>
      </div>

      <div className="grid-2">
        {/* Candidate Training Progress */}
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
              Candidate Model Lifecycle
            </span>
            <StatusBadge status={candStateNorm} />
          </div>

          {currentCand ? (
            <>
              <div style={{ marginBottom: '0.75rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8125rem', marginBottom: '0.25rem' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Post-Epoch Training Labels:</span>
                  <span style={{ fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                    {currentCand.unique_training_labels} / {currentCand.target_training_labels} ({currentCand.progress_percent}%)
                  </span>
                </div>
                <div
                  style={{
                    width: '100%',
                    height: '6px',
                    backgroundColor: 'var(--border-subtle)',
                    borderRadius: '3px',
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      width: `${Math.min(100, currentCand.progress_percent)}%`,
                      height: '100%',
                      backgroundColor:
                        candStateNorm === 'INCOMPLETE'
                          ? 'var(--warning-solid)'
                          : 'var(--cobalt-600)',
                      transition: 'width 0.3s ease',
                    }}
                  />
                </div>
              </div>

              <div className="kv-list">
                <div className="kv-row">
                  <span className="kv-key">Candidate Identifier:</span>
                  <span className="kv-val">{currentCand.candidate_id}</span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">Adaptation Epoch (Alert Seq):</span>
                  <span className="kv-val">{currentCand.epoch ?? 'N/A'}</span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">Training Freeze Sequence:</span>
                  <span className="kv-val">{currentCand.freeze_sequence ?? 'In Progress'}</span>
                </div>
              </div>
            </>
          ) : (
            <div style={{ padding: '1rem 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.8125rem' }}>
              No active candidate spawned. (ADWIN monitoring running on active model).
            </div>
          )}
        </div>

        {/* Paired Statistical Evaluation */}
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
              Paired Statistical Comparison
            </span>
            <span className="badge badge-neutral" style={{ fontSize: '0.6875rem' }}>
              McNemar Paired Test
            </span>
          </div>

          {currentSession ? (
            <>
              <div style={{ marginBottom: '0.75rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8125rem', marginBottom: '0.25rem' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Evaluation Window Scored:</span>
                  <span style={{ fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                    {currentSession.delivered_labels_count} / {currentSession.target_events_count} ({currentSession.progress_percent}%)
                  </span>
                </div>
                <div
                  style={{
                    width: '100%',
                    height: '6px',
                    backgroundColor: 'var(--border-subtle)',
                    borderRadius: '3px',
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      width: `${Math.min(100, currentSession.progress_percent)}%`,
                      height: '100%',
                      backgroundColor:
                        currentSession.decision === 'PROMOTED'
                          ? 'var(--success-solid)'
                          : currentSession.decision === 'REJECTED'
                          ? 'var(--danger-solid)'
                          : 'var(--cobalt-600)',
                      transition: 'width 0.3s ease',
                    }}
                  />
                </div>
              </div>

              <div className="kv-list">
                <div className="kv-row">
                  <span className="kv-key">Statistical Decision:</span>
                  <span className="kv-val">
                    <StatusBadge status={currentSession.decision} />
                  </span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">Observed Gain (b - c) / n:</span>
                  <span className="kv-val">
                    {currentSession.gain !== null && currentSession.gain !== undefined
                      ? `${(currentSession.gain * 100).toFixed(2)}%`
                      : 'Pending'}
                  </span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">One-Sided Exact p-value:</span>
                  <span className="kv-val">
                    {currentSession.p_value !== null && currentSession.p_value !== undefined
                      ? currentSession.p_value < 0.0001
                        ? currentSession.p_value.toExponential(3)
                        : currentSession.p_value.toFixed(4)
                      : 'Pending'}
                  </span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">Disagreements (b: active wrong / c: cand wrong):</span>
                  <span className="kv-val">b={currentSession.b}, c={currentSession.c}, n={currentSession.n}</span>
                </div>
              </div>
            </>
          ) : (
            <div style={{ padding: '1rem 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.8125rem' }}>
              Paired evaluation session inactive. (Begins when candidate completes training).
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
