import React, { useState, useEffect } from 'react';
import {
  ArrowRight,
  ArrowUpCircle,
  CheckCircle2,
  Lock,
  Info,
} from 'lucide-react';
import { api } from '../lib/api';
import type { RunDetail } from '../types';

interface ActionsProps {
  runId?: string | null;
}

export const Actions: React.FC<ActionsProps> = ({ runId }) => {
  const [reason, setReason] = useState('Lower error on fresh evaluation labels');
  const [exportReport, setExportReport] = useState(true);
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);

  useEffect(() => {
    let isMounted = true;
    const loadData = async () => {
      let targetRun = runId;
      if (!targetRun) {
        const runsRes = await api.getRuns(1, 1);
        if (runsRes.items.length > 0) {
          targetRun = runsRes.items[0].run_id;
        }
      }
      if (targetRun) {
        try {
          const detail = await api.getRunDetail(targetRun);
          if (isMounted) setRunDetail(detail);
        } catch (err) {
          console.error('Failed to load run detail for actions:', err);
        }
      }
    };
    loadData();
    return () => {
      isMounted = false;
    };
  }, [runId]);

  const activeVersion = runDetail?.active_model_version || 'v1.0';
  const activeCandidate = runDetail?.candidate_summary?.candidates?.[0];
  const candidateVersion = activeCandidate?.target_version || (runDetail?.candidate_state && runDetail.candidate_state !== 'IDLE' ? 'v2.0' : 'None');
  const candidateState = runDetail?.candidate_state || 'IDLE';
  const pairedSession = runDetail?.paired_summary?.sessions?.[0];
  const observedGain = pairedSession?.gain != null ? (pairedSession.gain * 100).toFixed(1) : null;
  const hasGain = observedGain != null;
  const b = pairedSession?.b ?? null;
  const c = pairedSession?.c ?? null;

  const isPromoted = candidateState === 'PROMOTED';
  const isEvaluating = candidateState === 'EVALUATING';
  const isTraining = candidateState === 'TRAINING';
  const hasCandidate = !!activeCandidate || isTraining || isEvaluating || isPromoted;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
            <h1 style={{ fontSize: '1.625rem', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
              Review model promotion
            </h1>
            <span className={`badge ${isPromoted ? 'badge-success' : isEvaluating ? 'badge-warning' : ''}`} style={!isPromoted && !isEvaluating ? { backgroundColor: 'var(--bg-surface-subtle)', color: 'var(--text-muted)', border: '1px solid var(--border-subtle)' } : {}}>
              {isPromoted ? 'Model Promoted' : isEvaluating ? 'Evaluating Candidate' : isTraining ? 'Training Candidate' : 'No Active Promotion'}
            </span>
          </div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginTop: '0.125rem' }}>
            Equipment State · <span style={{ fontFamily: 'var(--font-mono)' }}>{runDetail?.run_id || runId || 'stream'}</span> • Controlled synthetic stream
          </div>
        </div>
      </div>

      {/* Main 2-Column Body */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.6fr) minmax(0, 1fr)', gap: '1.25rem' }}>
        {/* Left Column: Recommendation & Checkpoints */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* Recommendation Banner */}
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', paddingBottom: '1rem', borderBottom: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
              <div
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '50%',
                  backgroundColor: isPromoted ? 'var(--teal-50)' : 'var(--bg-surface-subtle)',
                  color: isPromoted ? 'var(--teal-600)' : 'var(--text-muted)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <ArrowUpCircle size={22} />
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)' }}>
                  {isPromoted ? 'Automated action completed:' : isEvaluating ? 'Action in progress:' : 'Current state:'}
                </div>
                <div style={{ fontSize: '1.125rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  {isPromoted
                    ? `Promoted ${candidateVersion}`
                    : isEvaluating
                    ? `Evaluating candidate ${candidateVersion}`
                    : isTraining
                    ? `Training candidate ${candidateVersion}`
                    : `Baseline ${activeVersion} active`}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.125rem' }}>
                  {isPromoted
                    ? `Candidate ${candidateVersion} demonstrated statistically significant error reduction on fresh evaluation labels.`
                    : isEvaluating
                    ? `Candidate ${candidateVersion} is currently undergoing unbiased paired sequential evaluation.`
                    : isTraining
                    ? `Candidate ${candidateVersion} is collecting drift training quota labels.`
                    : `Serving predictions with frozen baseline ${activeVersion}. No candidate evaluation active.`}
                </div>
              </div>
            </div>

            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>Observed improvement</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: hasGain ? 'var(--teal-600)' : 'var(--text-muted)', lineHeight: 1.2 }}>
                {hasGain ? `+${observedGain} pp` : 'N/A'}
              </div>
              {b != null && c != null ? (
                <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>(b={b}, c={c})</div>
              ) : null}
            </div>
          </div>

          {/* Transition Box */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', alignItems: 'center', gap: '1rem' }}>
            <div style={{ border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)', padding: '0.75rem', backgroundColor: 'var(--bg-surface-subtle)' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>Active model ({activeVersion})</div>
              <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>Status: <strong>Serving predictions</strong></div>
              <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>State: Frozen baseline</div>
            </div>

            <ArrowRight size={16} color="var(--text-muted)" />

            <div style={{ border: '1px solid var(--cobalt-200)', borderRadius: 'var(--radius-sm)', padding: '0.75rem', backgroundColor: 'var(--cobalt-50)' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--cobalt-700)' }}>Candidate model ({candidateVersion})</div>
              <div style={{ fontSize: '0.6875rem', color: 'var(--cobalt-800)', marginTop: '0.25rem' }}>State: <strong>{candidateState}</strong></div>
              <div style={{ fontSize: '0.6875rem', color: 'var(--cobalt-700)' }}>
                {pairedSession ? `Evaluated: ${pairedSession.n ?? pairedSession.delivered_labels_count ?? 500} labels` : 'Evaluation: pending'}
              </div>
            </div>
          </div>

          {/* 4 Checkpoints */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.8125rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <CheckCircle2 size={16} color={hasCandidate ? 'var(--success-solid)' : 'var(--text-muted)'} />
                <span>Candidate training quota ({runDetail?.config?.adaptation?.target_training_labels ?? 200} labels)</span>
              </div>
              <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>
                {hasCandidate ? `${runDetail?.config?.adaptation?.target_training_labels ?? 200} labels` : 'Pending'}
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <CheckCircle2 size={16} color={pairedSession ? 'var(--success-solid)' : 'var(--text-muted)'} />
                <span>Fresh paired evaluation ({runDetail?.config?.adaptation?.evaluation_target_events ?? 500} random labels)</span>
              </div>
              <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>
                {pairedSession ? `${pairedSession.n ?? pairedSession.delivered_labels_count ?? 500} labels` : 'Pending'}
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <CheckCircle2 size={16} color={isPromoted ? 'var(--success-solid)' : 'var(--text-muted)'} />
                <span>Paired McNemar significance test</span>
              </div>
              <span style={{ fontWeight: 600, color: isPromoted ? 'var(--teal-600)' : 'var(--text-muted)' }}>
                {hasGain ? `+${observedGain} pp` : 'Pending'}
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <CheckCircle2 size={16} color="var(--success-solid)" />
                <span>Previous model version retained in snapshot store</span>
              </div>
              <span style={{ fontWeight: 600, color: 'var(--text-muted)' }}>Rollback retained</span>
            </div>
          </div>
        </div>

        {/* Right Column: Promotion Policy & Decision Review */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            Promotion policy & review
          </div>

          <div className="form-group">
            <label className="form-label">Operator / Auditor</label>
            <input type="text" className="form-input" value="Local Operator" readOnly />
          </div>

          <div className="form-group">
            <label className="form-label">Audit rationale</label>
            <textarea
              className="form-input"
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label className="form-label">Rollback target</label>
            <select className="form-select" defaultValue="v1.0" disabled>
              <option value="v1.0">{activeVersion} (Current baseline)</option>
            </select>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.75rem' }}>
            <input
              type="checkbox"
              id="exportReport"
              checked={exportReport}
              onChange={(e) => setExportReport(e.target.checked)}
            />
            <label htmlFor="exportReport">Include incident audit report in exports</label>
          </div>

          {/* Automated Policy Notice */}
          <div
            style={{
              padding: '0.75rem',
              backgroundColor: 'var(--cobalt-50)',
              border: '1px solid var(--cobalt-200)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.75rem',
              color: 'var(--cobalt-800)',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.375rem',
              marginTop: 'auto',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', fontWeight: 600 }}>
              <Lock size={13} />
              <span>Automated Engine Promotion Active</span>
            </div>
            <div style={{ fontSize: '0.6875rem', color: 'var(--cobalt-700)', lineHeight: 1.4 }}>
              Manual promotion override is disabled. DriftShield automatically promotes candidate models when paired McNemar evaluation confirms statistical error reduction.
            </div>
          </div>

          <div
            style={{
              padding: '0.625rem 0.75rem',
              backgroundColor: 'var(--warning-bg)',
              border: '1px solid var(--warning-border)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.6875rem',
              color: 'var(--warning-text)',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.375rem',
            }}
          >
            <Info size={13} style={{ flexShrink: 0, marginTop: '1px' }} />
            <span>
              <strong>Note:</strong> Future performance is bounded by stream drift rate. Live monitoring continues post-promotion.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
