import React, { useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Database,
  Zap,
  Play,
  Pause,
  Plus,
  ArrowRight,
} from 'lucide-react';
import { api } from '../lib/api';
import { RunWebSocketClient } from '../lib/websocket';
import type { RunDetail, WebSocketSnapshotMessage, IncidentItem } from '../types';

interface SnapshotLogItem {
  seq: number;
  time: string;
  eventsProcessed: number;
  modelVersion: string;
  errorRateStr: string;
  state: string;
}

interface OverviewProps {
  activeRunId: string | null;
  onNavigateNew: () => void;
  onNavigateLive: (runId: string) => void;
  onNavigateIncidents: (runId?: string) => void;
  onNavigateActions: (runId?: string) => void;
}

export const Overview: React.FC<OverviewProps> = ({
  activeRunId,
  onNavigateNew,
  onNavigateLive,
  onNavigateIncidents,
  onNavigateActions,
}) => {
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [latestIncident, setLatestIncident] = useState<IncidentItem | null>(null);
  const [snapshotLogs, setSnapshotLogs] = useState<SnapshotLogItem[]>([]);
  const [errorTrajectory, setErrorTrajectory] = useState<{ seq: number; error: number }[]>([]);
  const [isControlling, setIsControlling] = useState(false);
  const [controlError, setControlError] = useState<string | null>(null);

  // Load run details from REST
  useEffect(() => {
    let isMounted = true;

    const loadData = async () => {
      try {
        let runIdToFetch = activeRunId;
        if (!runIdToFetch) {
          const runsRes = await api.getRuns(1, 1);
          if (runsRes.items.length > 0) {
            runIdToFetch = runsRes.items[0].run_id;
          }
        }

        if (runIdToFetch) {
          const detail = await api.getRunDetail(runIdToFetch);
          if (isMounted) {
            setRunDetail(detail);
            // Fetch latest incident
            const incRes = await api.getIncidents(runIdToFetch, 1, 1);
            if (incRes.items.length > 0) {
              setLatestIncident(incRes.items[0]);
            } else {
              setLatestIncident(null);
            }
          }
        }
      } catch (err) {
        console.error('Failed to load overview data:', err);
      }
    };

    loadData();

    // Connect WebSocket if runId is available
    let ws: RunWebSocketClient | null = null;
    if (activeRunId) {
      ws = new RunWebSocketClient({
        onMessage: (snapshot: WebSocketSnapshotMessage) => {
          if (!isMounted) return;
          setRunDetail((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              operational_state: snapshot.operational_state,
              candidate_state: snapshot.candidate_state || prev.candidate_state,
              events_processed: snapshot.events_processed,
              total_events: snapshot.total_events,
              progress_percent: snapshot.progress_percent,
              active_model_version: snapshot.active_model_version,
              monitoring_coverage: snapshot.monitoring_coverage,
              label_accounting: snapshot.label_accounting,
              metrics: snapshot.metrics || prev.metrics,
              monitoring_summary: snapshot.monitoring_summary || prev.monitoring_summary,
              candidate_summary: snapshot.candidate_summary || prev.candidate_summary,
              paired_summary: snapshot.paired_summary || prev.paired_summary,
            };
          });

          // Track actual metric error rate
          const activeErr = snapshot.metrics?.full_synthetic?.error_rate ?? snapshot.metrics?.monitor_channel?.error_rate;
          if (activeErr != null) {
            setErrorTrajectory((prev) => {
              const updated = [...prev, { seq: snapshot.events_processed, error: activeErr * 100 }];
              return updated.slice(-30);
            });
          }

          // Record snapshot activity log
          const newLog: SnapshotLogItem = {
            seq: snapshot.snapshot_sequence,
            time: new Date(snapshot.timestamp * 1000).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            eventsProcessed: snapshot.events_processed,
            modelVersion: snapshot.active_model_version,
            errorRateStr: activeErr != null ? `${(activeErr * 100).toFixed(1)}%` : 'N/A',
            state: snapshot.operational_state,
          };
          setSnapshotLogs((prev) => [newLog, ...prev].slice(0, 10));
        },
      });
      ws.connect(activeRunId);
    }

    return () => {
      isMounted = false;
      if (ws) ws.disconnect();
    };
  }, [activeRunId]);

  const handleControlAction = async (action: 'start' | 'pause' | 'resume' | 'stop') => {
    if (!runDetail) return;
    setIsControlling(true);
    setControlError(null);
    try {
      await api.controlRun(runDetail.run_id, action);
      const updated = await api.getRunDetail(runDetail.run_id);
      setRunDetail(updated);
    } catch (err: any) {
      setControlError(err?.message || `Failed to ${action} run`);
    } finally {
      setIsControlling(false);
    }
  };

  const isRunning = runDetail?.operational_state === 'RUNNING';
  const isPaused = runDetail?.operational_state === 'PAUSED';
  const isCreated = runDetail?.operational_state === 'CREATED';

  // Metrics
  const eventsCount = runDetail?.events_processed ?? 0;
  const fullSyntheticError = runDetail?.metrics?.full_synthetic;
  const monitorChannelError = runDetail?.metrics?.monitor_channel;
  
  let errorRateDisplay = 'Not available';
  let errorDenominatorDisplay = 'No evaluations recorded';
  let isErrorElevated = false;

  if (fullSyntheticError?.error_rate != null) {
    errorRateDisplay = `${(fullSyntheticError.error_rate * 100).toFixed(1)}%`;
    errorDenominatorDisplay = `Evaluated on ${fullSyntheticError.denominator} stream events`;
    isErrorElevated = fullSyntheticError.error_rate > 0.05;
  } else if (monitorChannelError?.error_rate != null) {
    errorRateDisplay = `${(monitorChannelError.error_rate * 100).toFixed(1)}%`;
    errorDenominatorDisplay = `Monitored channel (${monitorChannelError.sample_count}/${monitorChannelError.denominator} events)`;
    isErrorElevated = monitorChannelError.error_rate > 0.05;
  }

  const deliveredLabels = runDetail?.label_accounting?.total_unique_acquisitions ?? 0;
  const labelBudget = runDetail?.config?.labels?.label_budget ?? 0;
  const budgetDebits = runDetail?.label_accounting?.budget_debits ?? 0;
  const labelDelay = runDetail?.config?.labels?.label_delay ?? 0;
  const scenarioName = runDetail?.scenario ? `Equipment ${runDetail.scenario}` : 'Equipment Stream';
  const activeVersion = runDetail?.active_model_version || 'v1.0-frozen';
  const candidateState = runDetail?.candidate_state || 'NONE';

  const isInterrupted = runDetail?.operational_state === 'INTERRUPTED';
  const hasMonitoringEvidence = (runDetail?.events_processed ?? 0) > 0 && ((runDetail?.monitoring_summary?.alerts_count ?? 0) > 0 || runDetail?.metrics != null);
  const hasIncident = latestIncident != null || (runDetail?.monitoring_summary?.alerts_count ?? 0) > 0;
  const incidentId = latestIncident?.incident_id || (hasIncident ? 'Active Alert' : null);
  const pairedSession = runDetail?.paired_summary?.sessions?.[0];
  const activeCandidate = runDetail?.candidate_summary?.candidates?.[0];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Top Banner & Action Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div>
          <h1
            style={{
              fontSize: '1.75rem',
              fontWeight: 700,
              color: 'var(--text-primary)',
              letterSpacing: '-0.03em',
              lineHeight: 1.2,
            }}
          >
            Model reliability, live.
          </h1>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.625rem',
              marginTop: '0.25rem',
              fontSize: '0.8125rem',
              color: 'var(--text-secondary)',
            }}
          >
            <span style={{ fontWeight: 600 }}>{scenarioName}</span>
            <span style={{ color: 'var(--border-strong)' }}>•</span>
            <span style={{ fontFamily: 'var(--font-mono)' }}>{runDetail?.run_id || 'No active run'}</span>
            <span style={{ color: 'var(--border-strong)' }}>•</span>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.3125rem',
                color: isRunning ? 'var(--success-text)' : 'var(--text-muted)',
                fontWeight: 600,
              }}
            >
              <span
                style={{
                  width: '6px',
                  height: '6px',
                  borderRadius: 'var(--radius-full)',
                  backgroundColor: isRunning ? 'var(--success-solid)' : 'var(--border-strong)',
                }}
              />
              {runDetail?.operational_state || 'IDLE'}
            </span>
          </div>
        </div>

        {/* Action Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
          {runDetail && (
            <>
              {isCreated && (
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => handleControlAction('start')}
                  disabled={isControlling}
                >
                  <Play size={13} fill="currentColor" /> Start
                </button>
              )}
              {isRunning && (
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => handleControlAction('pause')}
                  disabled={isControlling}
                >
                  <Pause size={13} fill="currentColor" /> Pause
                </button>
              )}
              {isPaused && (
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => handleControlAction('resume')}
                  disabled={isControlling}
                >
                  <Play size={13} fill="currentColor" /> Resume
                </button>
              )}
            </>
          )}

          <button
            className="btn btn-primary btn-sm"
            onClick={onNavigateNew}
            style={{ fontWeight: 600 }}
          >
            <Plus size={14} /> New stream
          </button>
        </div>
      </div>

      {/* Actionable Interrupted Banner */}
      {runDetail?.operational_state === 'INTERRUPTED' && (
        <div
          className="card"
          style={{
            backgroundColor: 'var(--danger-bg)',
            borderColor: 'var(--danger-border)',
            color: 'var(--danger-text)',
            padding: '1rem 1.25rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '1rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <AlertTriangle size={20} color="var(--danger-solid)" />
            <div>
              <div style={{ fontWeight: 700, fontSize: '0.875rem' }}>Stream Run Interrupted</div>
              <div style={{ fontSize: '0.75rem', opacity: 0.9, marginTop: '0.125rem' }}>
                This run was stopped prior to completion (e.g. server process restart). Persisted events and state are retained in SQLite. Replay the same scenario and seed from the stream creator.
              </div>
            </div>
          </div>
          <button
            className="btn btn-primary btn-sm"
            onClick={onNavigateNew}
            style={{ fontWeight: 600 }}
          >
            Replay stream configuration <ArrowRight size={13} />
          </button>
        </div>
      )}

      {controlError && (
        <div style={{ padding: '0.75rem', backgroundColor: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', color: 'var(--danger-text)', fontSize: '0.8125rem' }}>
          {controlError}
        </div>
      )}

      {/* 4 Top KPI Cards */}
      <div className="kpi-grid">
        {/* 1. Events Processed */}
        <div className="kpi-card">
          <div className="kpi-card-header">
            <span className="kpi-card-label">Events processed</span>
            <Activity size={16} color="var(--cobalt-600)" />
          </div>
          <div className="kpi-card-value">{eventsCount.toLocaleString()}</div>
          <div className="kpi-card-subtitle">
            {runDetail?.config?.stream?.events_per_second ? `${runDetail.config.stream.events_per_second} events/s pacing` : 'Configured speed'}
          </div>
        </div>

        {/* 2. Prediction Error */}
        <div className="kpi-card">
          <div className="kpi-card-header">
            <span className="kpi-card-label">Prediction error</span>
            <AlertTriangle size={16} color={isErrorElevated ? 'var(--warning-solid)' : 'var(--cobalt-600)'} />
          </div>
          <div className="kpi-card-value" style={{ color: isErrorElevated ? 'var(--warning-text)' : 'var(--text-primary)' }}>
            {errorRateDisplay}
          </div>
          <div className="kpi-card-subtitle" style={{ color: isErrorElevated ? 'var(--warning-text)' : 'var(--text-muted)' }}>
            {errorDenominatorDisplay}
          </div>
        </div>

        {/* 3. Labels Received */}
        <div className="kpi-card">
          <div className="kpi-card-header">
            <span className="kpi-card-label">Labels acquired</span>
            <Database size={16} color="var(--cobalt-600)" />
          </div>
          <div className="kpi-card-value">
            {deliveredLabels.toLocaleString()} / {labelBudget ? labelBudget.toLocaleString() : '—'}
          </div>
          <div className="kpi-card-subtitle">
            Budget debits: {budgetDebits} · {labelDelay > 0 ? `${labelDelay} delay` : '0 delay'}
          </div>
        </div>

        {/* 4. Processing Latency */}
        <div className="kpi-card">
          <div className="kpi-card-header">
            <span className="kpi-card-label">Engine step latency</span>
            <Zap size={16} color="var(--cobalt-600)" />
          </div>
          <div className="kpi-card-value">37.0 µs</div>
          <div className="kpi-card-subtitle">In-memory engine benchmark step</div>
        </div>
      </div>

      {/* Middle Row: Prediction Error Chart & Incident Card */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.8fr) minmax(0, 1fr)', gap: '1.25rem' }}>
        {/* Left: Prediction Error Over Time Chart */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="card-header" style={{ marginBottom: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span className="card-title" style={{ fontSize: '0.875rem' }}>
                Prediction error over time
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', fontSize: '0.75rem' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', color: 'var(--cobalt-600)', fontWeight: 600 }}>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--cobalt-600)' }} />
                Active model ({activeVersion})
              </span>
              {candidateState !== 'NONE' && (
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', color: 'var(--teal-600)', fontWeight: 600 }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--teal-500)' }} />
                  Candidate ({activeCandidate?.target_version || 'v2.0'})
                </span>
              )}
            </div>
          </div>

          {/* SVG Line Chart from Actual Data */}
          <div style={{ flex: 1, minHeight: '220px', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {errorTrajectory.length > 1 ? (
              <svg viewBox="0 0 700 200" style={{ width: '100%', height: '100%', overflow: 'visible' }}>
                {[0, 10, 20, 30, 40].map((val) => {
                  const y = 170 - (val / 40) * 140;
                  return (
                    <g key={val}>
                      <line x1="40" y1={y} x2="680" y2={y} stroke="var(--border-subtle)" strokeDasharray="2 2" />
                      <text x="32" y={y + 4} textAnchor="end" fontSize="10" fill="var(--text-muted)" fontFamily="var(--font-mono)">
                        {val}%
                      </text>
                    </g>
                  );
                })}

                {/* Draw real polyline */}
                {(() => {
                  const minSeq = errorTrajectory[0].seq;
                  const maxSeq = Math.max(minSeq + 1, errorTrajectory[errorTrajectory.length - 1].seq);
                  const points = errorTrajectory.map((p) => {
                    const x = 50 + ((p.seq - minSeq) / (maxSeq - minSeq)) * 620;
                    const y = Math.max(20, Math.min(170, 170 - (p.error / 40) * 140));
                    return `${x},${y}`;
                  }).join(' ');
                  return (
                    <polyline
                      points={points}
                      fill="none"
                      stroke="var(--cobalt-600)"
                      strokeWidth="2.5"
                    />
                  );
                })()}

                <text x="50" y="190" fontSize="10" fill="var(--text-muted)">Seq #{errorTrajectory[0].seq}</text>
                <text x="670" y="190" fontSize="10" fill="var(--text-muted)" textAnchor="end">Seq #{errorTrajectory[errorTrajectory.length - 1].seq}</text>
              </svg>
            ) : (
              <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.8125rem' }}>
                {isRunning ? 'Receiving live stream metrics...' : 'No error history recorded yet for this stream'}
              </div>
            )}
          </div>
        </div>

        {/* Right: Incident Summary Card */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <div
                  style={{
                    width: '24px',
                    height: '24px',
                    borderRadius: 'var(--radius-xs)',
                    backgroundColor: isInterrupted || hasIncident ? 'var(--danger-bg)' : 'var(--bg-surface-subtle)',
                    color: isInterrupted || hasIncident ? 'var(--danger-text)' : 'var(--text-muted)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <AlertTriangle size={14} />
                </div>
                <div
                  style={{ cursor: hasIncident ? 'pointer' : 'default' }}
                  onClick={() => hasIncident && onNavigateIncidents(runDetail?.run_id)}
                  title="View incident details"
                >
                  <div style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                    {isInterrupted ? 'Stream Interrupted' : !hasMonitoringEvidence ? 'Unmonitored' : (incidentId || 'System Monitored')}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    {isInterrupted
                      ? 'Stream execution interrupted'
                      : !hasMonitoringEvidence
                      ? 'Awaiting stream monitoring data'
                      : hasIncident
                      ? 'Evidence of error change'
                      : 'No active alerts in stream'}
                  </div>
                </div>
              </div>
              <span
                className={`badge ${
                  isInterrupted
                    ? 'badge-danger'
                    : !hasMonitoringEvidence
                    ? 'badge-neutral'
                    : hasIncident
                    ? 'badge-danger'
                    : 'badge-success'
                }`}
              >
                {isInterrupted ? 'Interrupted' : !hasMonitoringEvidence ? 'Unmonitored' : hasIncident ? 'Alerted' : 'Nominal'}
              </span>
            </div>

            <div className="kv-list" style={{ marginTop: '1rem', borderTop: '1px solid var(--border-subtle)', paddingTop: '0.75rem' }}>
              <div className="kv-row">
                <span className="kv-key">Detected at</span>
                <span className="kv-val">{latestIncident?.event_sequence ? `Event #${latestIncident.event_sequence}` : '—'}</span>
              </div>
              <div className="kv-row">
                <span className="kv-key">Detection delay</span>
                <span className="kv-val">
                  {latestIncident?.event_sequence
                    ? `${latestIncident.event_sequence - (runDetail?.config?.stream?.drift_start_sequence ?? 1000)} events (onset)`
                    : '—'}
                </span>
              </div>
              <div className="kv-row">
                <span className="kv-key">Observed gain (paired)</span>
                <span className="kv-val" style={{ color: pairedSession?.gain ? 'var(--success-text)' : 'inherit' }}>
                  {pairedSession?.gain != null ? `+${(pairedSession.gain * 100).toFixed(1)} pp (b=${pairedSession.b}, c=${pairedSession.c})` : '—'}
                </span>
              </div>
              <div className="kv-row">
                <span className="kv-key">Active model ({activeVersion}) error</span>
                <span className="kv-val">{errorRateDisplay}</span>
              </div>
              <div className="kv-row">
                <span className="kv-key">Candidate lifecycle state</span>
                <span className="kv-val" style={{ color: candidateState === 'PROMOTED' ? 'var(--success-text)' : 'var(--text-primary)' }}>
                  {candidateState}
                </span>
              </div>
            </div>
          </div>

          <button
            className="btn btn-primary"
            style={{ width: '100%', marginTop: '1rem', fontWeight: 600 }}
            onClick={() => onNavigateActions(runDetail?.run_id)}
          >
            Review comparison <ArrowRight size={14} />
          </button>
        </div>
      </div>

      {/* Bottom Row: 3 Grid Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '1.25rem' }}>
        {/* 1. Model State & Decision Boundary */}
        <div className="card">
          <div className="card-header">
            <span className="card-title" style={{ fontSize: '0.875rem' }}>
              Decision boundary
            </span>
            <span className="badge badge-neutral" style={{ fontSize: '0.625rem' }}>Unavailable</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.625rem', fontSize: '0.75rem' }}>
            <div className="kv-row">
              <span className="kv-key">Active model</span>
              <span className="kv-val" style={{ fontWeight: 600, color: 'var(--cobalt-600)' }}>{activeVersion}</span>
            </div>
            <div className="kv-row">
              <span className="kv-key">Candidate version</span>
              <span className="kv-val" style={{ fontWeight: 600, color: 'var(--teal-600)' }}>
                {activeCandidate?.target_version || 'None'}
              </span>
            </div>
            <div className="kv-row">
              <span className="kv-key">Candidate state</span>
              <span className="kv-val">{candidateState}</span>
            </div>
            <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', borderTop: '1px solid var(--border-subtle)', paddingTop: '0.5rem', lineHeight: 1.4 }}>
              <strong>Notice:</strong> Decision boundary parameters (classifier weights and StandardScaler transformation parameters) are not exposed in the summary REST schema. Raw feature boundary plotting is unavailable.
            </div>
          </div>
        </div>

        {/* 2. Model Comparison */}
        <div className="card">
          <div className="card-header">
            <span className="card-title" style={{ fontSize: '0.875rem' }}>
              Model comparison
            </span>
            <span className="badge badge-neutral" style={{ fontSize: '0.625rem' }}>Paired Test</span>
          </div>

          <div className="kv-list" style={{ fontSize: '0.75rem' }}>
            <div className="kv-row">
              <span className="kv-key">Active model error</span>
              <span className="kv-val" style={{ fontWeight: 700 }}>{errorRateDisplay}</span>
            </div>
            <div className="kv-row">
              <span className="kv-key">Observed gain (paired)</span>
              <span className="kv-val" style={{ color: pairedSession?.gain ? 'var(--success-text)' : 'inherit', fontWeight: 600 }}>
                {pairedSession?.gain != null ? `+${(pairedSession.gain * 100).toFixed(1)} pp` : 'Awaiting evaluation'}
              </span>
            </div>
            <div className="kv-row">
              <span className="kv-key">Paired counts (b, c)</span>
              <span className="kv-val">
                {pairedSession ? `(${pairedSession.b}, ${pairedSession.c})` : '—'}
              </span>
            </div>
            <div className="kv-row">
              <span className="kv-key">Paired p-value</span>
              <span className="kv-val">
                {pairedSession?.p_value != null ? pairedSession.p_value.toExponential(2) : '—'}
              </span>
            </div>
            <div className="kv-row">
              <span className="kv-key">Promotion decision</span>
              <span className="kv-val" style={{ fontWeight: 600, color: pairedSession?.decision === 'PROMOTE' ? 'var(--success-text)' : 'var(--text-muted)' }}>
                {pairedSession?.decision || 'None'}
              </span>
            </div>
          </div>
        </div>

        {/* 3. Live Run Updates */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="card-header">
            <span className="card-title" style={{ fontSize: '0.875rem' }}>
              Live run updates
            </span>
            <button
              onClick={() => onNavigateLive(runDetail?.run_id || '')}
              style={{ background: 'none', border: 'none', color: 'var(--cobalt-600)', fontSize: '0.75rem', fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.25rem' }}
            >
              Live monitor →
            </button>
          </div>

          <div style={{ flex: 1, overflowX: 'auto' }}>
            <table className="table" style={{ fontSize: '0.75rem' }}>
              <thead>
                <tr>
                  <th style={{ padding: '0.375rem 0.5rem' }}>Seq</th>
                  <th style={{ padding: '0.375rem 0.5rem' }}>Time</th>
                  <th style={{ padding: '0.375rem 0.5rem' }}>Events</th>
                  <th style={{ padding: '0.375rem 0.5rem' }}>State</th>
                </tr>
              </thead>
              <tbody>
                {snapshotLogs.length > 0 ? (
                  snapshotLogs.slice(0, 5).map((log: SnapshotLogItem, idx: number) => (
                    <tr key={idx}>
                      <td style={{ fontFamily: 'var(--font-mono)', padding: '0.375rem 0.5rem' }}>#{log.seq}</td>
                      <td style={{ color: 'var(--text-muted)', padding: '0.375rem 0.5rem' }}>{log.time}</td>
                      <td style={{ padding: '0.375rem 0.5rem' }}>{log.eventsProcessed}</td>
                      <td style={{ padding: '0.375rem 0.5rem' }}>
                        <span className="badge badge-neutral" style={{ fontSize: '0.625rem' }}>
                          {log.state}
                        </span>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '1.5rem' }}>
                      {isRunning ? 'Listening for live stream snapshots...' : 'No snapshots recorded for this run'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
