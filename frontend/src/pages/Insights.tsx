import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  Clock,
  HelpCircle,
  TrendingUp,
  Zap,
} from 'lucide-react';
import { api } from '../lib/api';
import type { RunDetail } from '../types';

interface InsightsProps {
  runId?: string | null;
  onNavigateActions?: (runId?: string) => void;
}

export const Insights: React.FC<InsightsProps> = ({ runId, onNavigateActions }) => {
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);

  useEffect(() => {
    let isMounted = true;
    const loadRun = async () => {
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
          console.error('Failed to load insights run detail:', err);
        }
      }
    };
    loadRun();
    return () => {
      isMounted = false;
    };
  }, [runId]);

  const fullSynthetic = runDetail?.metrics?.full_synthetic;
  const monitorChannel = runDetail?.metrics?.monitor_channel;
  const currentError = fullSynthetic?.error_rate ?? monitorChannel?.error_rate ?? null;
  const errorRateStr = currentError != null ? `${(currentError * 100).toFixed(1)}%` : 'Not available';
  const isErrorElevated = currentError != null && currentError > 0.05;

  const coveragePercent = typeof runDetail?.monitoring_coverage === 'number'
    ? (runDetail.monitoring_coverage * 100).toFixed(0)
    : (runDetail?.config?.monitoring?.random_rate != null
      ? (runDetail.config.monitoring.random_rate * 100).toFixed(0)
      : 'N/A');

  const labelDelay = runDetail?.config?.labels?.label_delay ?? 0;
  const pairedSession = runDetail?.paired_summary?.sessions?.[0];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.625rem', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
            Prediction risk & stream health
          </h1>
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginTop: '0.125rem' }}>
            Scenario: {runDetail?.scenario || 'abrupt'} · <span style={{ fontFamily: 'var(--font-mono)' }}>{runDetail?.run_id || runId || 'stream'}</span> • Controlled synthetic stream
          </div>
        </div>
      </div>

      {/* 4 KPI Cards */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-card-header">
            <span className="kpi-card-label">Observed error</span>
            <AlertTriangle size={15} color={isErrorElevated ? 'var(--warning-solid)' : (currentError != null ? 'var(--cobalt-600)' : 'var(--text-muted)')} />
          </div>
          <div className="kpi-card-value" style={{ color: isErrorElevated ? 'var(--warning-text)' : 'var(--text-primary)' }}>
            {errorRateStr}
          </div>
          {currentError != null ? (
            <span className={`badge ${isErrorElevated ? 'badge-warning' : 'badge-success'}`} style={{ marginTop: '0.25rem' }}>
              {isErrorElevated ? 'Elevated error' : 'Nominal'}
            </span>
          ) : (
            <span className="badge" style={{ marginTop: '0.25rem', backgroundColor: 'var(--bg-surface-subtle)', color: 'var(--text-muted)', border: '1px solid var(--border-subtle)' }}>
              No data
            </span>
          )}
        </div>

        <div className="kpi-card">
          <div className="kpi-card-header">
            <span className="kpi-card-label">Monitoring coverage</span>
            <Zap size={15} color="var(--cobalt-600)" />
          </div>
          <div className="kpi-card-value">{coveragePercent}{coveragePercent !== 'N/A' ? '%' : ''}</div>
          <div className="kpi-card-subtitle">Random sample rate</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-card-header">
            <span className="kpi-card-label">Budget debits</span>
            <Clock size={15} color="var(--cobalt-600)" />
          </div>
          <div className="kpi-card-value">{runDetail?.label_accounting?.budget_debits ?? 0}</div>
          <div className="kpi-card-subtitle">Post-warmup acquisitions</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-card-header">
            <span className="kpi-card-label">Label delay</span>
            <Clock size={15} color="var(--cobalt-600)" />
          </div>
          <div className="kpi-card-value">{labelDelay > 0 ? `${labelDelay} events` : '0 events'}</div>
          <div className="kpi-card-subtitle">{labelDelay > 0 ? `${labelDelay} events delay` : 'Immediate delivery'}</div>
        </div>
      </div>

      {/* 2x2 Grid Layout */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '1.25rem' }}>
        {/* Top Left: Stream Performance Breakdown */}
        <div className="card">
          <div className="card-header">
            <span className="card-title" style={{ fontSize: '0.875rem' }}>
              Stream Error & Channel Breakdown
            </span>
            <HelpCircle size={14} color="var(--text-muted)" />
          </div>
          <div className="kv-list" style={{ fontSize: '0.8125rem' }}>
            <div className="kv-row">
              <span className="kv-key">Full synthetic channel</span>
              <span className="kv-val">
                {fullSynthetic?.error_rate != null ? `${(fullSynthetic.error_rate * 100).toFixed(1)}% (${fullSynthetic.denominator} events)` : 'N/A'}
              </span>
            </div>
            <div className="kv-row">
              <span className="kv-key">Monitoring sample channel</span>
              <span className="kv-val">
                {monitorChannel?.error_rate != null ? `${(monitorChannel.error_rate * 100).toFixed(1)}% (${monitorChannel.sample_count}/${monitorChannel.denominator})` : 'N/A'}
              </span>
            </div>
            <div className="kv-row">
              <span className="kv-key">Warm-up acquisitions</span>
              <span className="kv-val">{runDetail?.label_accounting?.warmup_acquisitions ?? 0}</span>
            </div>
            <div className="kv-row">
              <span className="kv-key">Unique labels acquired</span>
              <span className="kv-val">{runDetail?.label_accounting?.total_unique_acquisitions ?? 0}</span>
            </div>
          </div>
        </div>

        {/* Top Right: Model Margin Interpretation */}
        <div className="card">
          <div className="card-header">
            <span className="card-title" style={{ fontSize: '0.875rem' }}>
              Model Decision Boundaries & Scores
            </span>
          </div>
          <div className="kv-list" style={{ fontSize: '0.8125rem' }}>
            <div className="kv-row">
              <span className="kv-key">Active model version</span>
              <span className="kv-val" style={{ fontWeight: 600, color: 'var(--cobalt-600)' }}>
                {runDetail?.active_model_version || 'v1.0-frozen'}
              </span>
            </div>
            <div className="kv-row">
              <span className="kv-key">Candidate state</span>
              <span className="kv-val">{runDetail?.candidate_state || 'NONE'}</span>
            </div>
            <div className="kv-row">
              <span className="kv-key">Paired McNemar test</span>
              <span className="kv-val" style={{ color: pairedSession?.gain ? 'var(--success-text)' : 'inherit' }}>
                {pairedSession?.gain != null ? `+${(pairedSession.gain * 100).toFixed(1)} pp (b=${pairedSession.b}, c=${pairedSession.c})` : 'Awaiting evaluation'}
              </span>
            </div>
          </div>
          <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', borderTop: '1px solid var(--border-subtle)', paddingTop: '0.5rem', marginTop: '0.5rem' }}>
            Note: Margin is a geometric decision score |w^T x + b|, not calibrated posterior probability.
          </div>
        </div>

        {/* Bottom Left: Configuration Settings */}
        <div className="card">
          <div className="card-header">
            <span className="card-title" style={{ fontSize: '0.875rem' }}>
              Engine Adaptation Policy
            </span>
          </div>
          <div className="kv-list" style={{ fontSize: '0.8125rem' }}>
            <div className="kv-row">
              <span className="kv-key">ADWIN delta</span>
              <span className="kv-val">{runDetail?.config?.monitoring?.adwin_delta || 0.002}</span>
            </div>
            <div className="kv-row">
              <span className="kv-key">Candidate training quota</span>
              <span className="kv-val">{runDetail?.config?.adaptation?.target_training_labels || 200} labels</span>
            </div>
            <div className="kv-row">
              <span className="kv-key">Evaluation quota</span>
              <span className="kv-val">{runDetail?.config?.adaptation?.evaluation_target_events || 500} labels</span>
            </div>
          </div>
        </div>

        {/* Bottom Right: Insights & Next Steps */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <span className="card-title" style={{ fontSize: '0.875rem' }}>
            Insights & next steps
          </span>

          {currentError == null ? (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', padding: '0.5rem', backgroundColor: 'var(--bg-surface-subtle)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)', fontSize: '0.75rem' }}>
              <HelpCircle size={15} color="var(--text-muted)" style={{ flexShrink: 0, marginTop: '2px' }} />
              <div>
                <strong>Awaiting evaluation telemetry</strong>
                <div style={{ color: 'var(--text-secondary)' }}>No observed error rate recorded yet for this stream.</div>
              </div>
            </div>
          ) : isErrorElevated ? (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', padding: '0.5rem', backgroundColor: 'var(--warning-bg)', border: '1px solid var(--warning-border)', borderRadius: 'var(--radius-sm)', fontSize: '0.75rem' }}>
              <AlertTriangle size={15} color="var(--warning-solid)" style={{ flexShrink: 0, marginTop: '2px' }} />
              <div>
                <strong>Elevated error detected</strong>
                <div style={{ color: 'var(--text-secondary)' }}>Statistical drift detected on monitored sensor stream.</div>
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', padding: '0.5rem', backgroundColor: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: 'var(--radius-sm)', fontSize: '0.75rem' }}>
              <TrendingUp size={15} color="var(--success-solid)" style={{ flexShrink: 0, marginTop: '2px' }} />
              <div>
                <strong>Stream nominal</strong>
                <div style={{ color: 'var(--text-secondary)' }}>Active model prediction error within nominal threshold.</div>
              </div>
            </div>
          )}

          <button
            className="btn btn-primary"
            style={{ marginTop: 'auto', fontWeight: 600 }}
            onClick={() => onNavigateActions && onNavigateActions(runDetail?.run_id || runId || undefined)}
          >
            Review model actions <ArrowRight size={14} />
          </button>
        </div>
      </div>
    </div>
  );
};
