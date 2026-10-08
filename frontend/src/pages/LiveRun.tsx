import React, { useEffect, useRef, useState } from 'react';
import {
  CheckCircle2,
  Clock,
  Cpu,
  ExternalLink,
  Pause,
  Play,
  RefreshCw,
  Square,
  Zap,
} from 'lucide-react';
import { api } from '../lib/api';
import { RunWebSocketClient, type ConnectionStatus } from '../lib/websocket';
import type { IncidentItem, RunDetail, WebSocketSnapshotMessage } from '../types';

interface LiveRunProps {
  runId: string;
  onNavigateBack?: () => void;
  onNavigateIncidents?: (runId: string) => void;
  onNavigateActions?: (runId: string) => void;
}

interface SnapshotFeedRow {
  seq: number;
  time: string;
  eventsProcessed: number;
  activeModel: string;
  candidateState: string;
  errorRateStr: string;
  labelsReceived: number;
}

export const LiveRun: React.FC<LiveRunProps> = ({
  runId,
  onNavigateBack,
  onNavigateIncidents,
  onNavigateActions,
}) => {
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [incidents, setIncidents] = useState<IncidentItem[]>([]);
  const [snapshotRows, setSnapshotRows] = useState<SnapshotFeedRow[]>([]);
  const [errorTrajectory, setErrorTrajectory] = useState<{ seq: number; error: number }[]>([]);
  const [wsStatus, setWsStatus] = useState<ConnectionStatus>('idle');
  const [isControlling, setIsControlling] = useState(false);
  const [controlError, setControlError] = useState<string | null>(null);

  const wsClientRef = useRef<RunWebSocketClient | null>(null);

  // 1. Initial REST fetch
  const loadInitialState = async () => {
    try {
      const detail = await api.getRunDetail(runId);
      setRunDetail(detail);

      const incData = await api.getIncidents(runId, 1, 10);
      setIncidents(incData.items);
    } catch (err: any) {
      console.warn('Failed to load initial live state:', err);
    }
  };

  // 2. Connect WebSocket
  useEffect(() => {
    loadInitialState();

    const ws = new RunWebSocketClient({
      onStatusChange: (status) => {
        setWsStatus(status);
      },
      onMessage: (snapshot: WebSocketSnapshotMessage) => {
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

        // Record real metric trajectory point
        const activeErr = snapshot.metrics?.full_synthetic?.error_rate ?? snapshot.metrics?.monitor_channel?.error_rate;
        if (activeErr != null) {
          setErrorTrajectory((prev) => {
            const updated = [...prev, { seq: snapshot.events_processed, error: activeErr * 100 }];
            return updated.slice(-40);
          });
        }

        // Record real snapshot row
        const newRow: SnapshotFeedRow = {
          seq: snapshot.snapshot_sequence,
          time: new Date(snapshot.timestamp * 1000).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
          eventsProcessed: snapshot.events_processed,
          activeModel: snapshot.active_model_version,
          candidateState: snapshot.candidate_state || 'NONE',
          errorRateStr: activeErr != null ? `${(activeErr * 100).toFixed(1)}%` : 'N/A',
          labelsReceived: snapshot.label_accounting.total_unique_acquisitions,
        };

        setSnapshotRows((prev) => [newRow, ...prev].slice(0, 12));
      },
    });

    wsClientRef.current = ws;
    ws.connect(runId);

    return () => {
      ws.disconnect();
    };
  }, [runId]);

  // Lifecycle action handler
  const handleControl = async (action: 'start' | 'pause' | 'resume' | 'stop') => {
    if (!runDetail) return;
    setIsControlling(true);
    setControlError(null);
    try {
      await api.controlRun(runDetail.run_id, action);
      const updated = await api.getRunDetail(runDetail.run_id);
      setRunDetail(updated);
    } catch (err: any) {
      setControlError(err?.message || `Control action '${action}' failed`);
    } finally {
      setIsControlling(false);
    }
  };

  const isRunning = runDetail?.operational_state === 'RUNNING';
  const isPaused = runDetail?.operational_state === 'PAUSED';
  const isCreated = runDetail?.operational_state === 'CREATED' || runDetail?.operational_state === 'INITIALIZING';
  const isCompleted = runDetail?.operational_state === 'COMPLETED';
  const isInterrupted = runDetail?.operational_state === 'INTERRUPTED';
  const isStopped = runDetail?.operational_state === 'STOPPED';

  const candidateState = runDetail?.candidate_state || 'NONE';
  const isTraining = candidateState === 'TRAINING';
  const isEvaluating = candidateState === 'EVALUATING';
  const isPromoted = candidateState === 'PROMOTED';

  const activeModel = runDetail?.active_model_version || 'v1.0-frozen';
  const labelDelay = runDetail?.config?.labels?.label_delay ?? 0;
  const deliveredLabels = runDetail?.label_accounting?.total_unique_acquisitions ?? 0;
  
  // Candidate training progress from actual backend state
  const activeCandidate = runDetail?.candidate_summary?.candidates?.[0];
  const targetTrain = activeCandidate?.target_training_labels ?? runDetail?.config?.adaptation?.target_training_labels ?? 200;
  const currentTrainCount = activeCandidate?.unique_training_labels ?? 0;
  const trainPercent = activeCandidate?.progress_percent ?? (targetTrain > 0 ? Math.min(100, Math.round((currentTrainCount / targetTrain) * 100)) : 0);
  const pendingLabels = runDetail?.label_accounting?.monitor_acquisitions ? Math.max(0, runDetail.label_accounting.monitor_acquisitions - deliveredLabels) : 0;

  const latestAlert = incidents.length > 0 ? incidents[0] : (runDetail?.monitoring_summary?.alerts?.[0] || null);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Top Header Bar */}
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
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
            <h1 style={{ fontSize: '1.625rem', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
              {isRunning
                ? 'Stream running'
                : isPaused
                ? 'Stream paused'
                : isCompleted
                ? 'Stream completed'
                : isInterrupted
                ? 'Stream interrupted'
                : isStopped
                ? 'Stream stopped'
                : 'Stream ready'}
            </h1>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.3125rem',
                fontSize: '0.75rem',
                fontWeight: 600,
                color: isRunning ? 'var(--success-text)' : isInterrupted ? 'var(--danger-text)' : 'var(--text-muted)',
                backgroundColor: isRunning ? 'var(--success-bg)' : isInterrupted ? 'var(--danger-bg)' : 'var(--bg-surface-subtle)',
                padding: '0.15rem 0.5rem',
                borderRadius: 'var(--radius-xs)',
              }}
            >
              <span
                style={{
                  width: '6px',
                  height: '6px',
                  borderRadius: '50%',
                  backgroundColor: isRunning ? 'var(--success-solid)' : isInterrupted ? 'var(--danger-solid)' : 'var(--border-strong)',
                }}
              />
              {runDetail?.operational_state || 'READY'}
            </span>
            <span className="badge badge-neutral" style={{ fontSize: '0.625rem' }}>
              WS: {wsStatus}
            </span>
          </div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginTop: '0.125rem' }}>
            Scenario: {runDetail?.scenario || 'abrupt'} · <span style={{ fontFamily: 'var(--font-mono)' }}>{runId}</span>
          </div>
        </div>

        {/* Action Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
          {isCreated && (
            <button
              className="btn btn-primary btn-sm"
              onClick={() => handleControl('start')}
              disabled={isControlling}
            >
              <Play size={14} fill="currentColor" /> Start stream
            </button>
          )}

          {isRunning && (
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => handleControl('pause')}
              disabled={isControlling}
            >
              <Pause size={14} fill="currentColor" /> Pause
            </button>
          )}

          {isPaused && (
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => handleControl('resume')}
              disabled={isControlling}
            >
              <Play size={14} fill="currentColor" /> Resume
            </button>
          )}

          {(isRunning || isPaused) && (
            <button
              className="btn btn-danger btn-sm"
              onClick={() => {
                if (window.confirm('Are you sure you want to stop this stream run?')) {
                  handleControl('stop');
                }
              }}
              disabled={isControlling}
            >
              <Square size={12} fill="currentColor" /> Stop run
            </button>
          )}

          {latestAlert && (
            <button
              className="btn btn-primary btn-sm"
              onClick={() => onNavigateActions ? onNavigateActions(runId) : (onNavigateIncidents ? onNavigateIncidents(runId) : null)}
              style={{ fontWeight: 600 }}
            >
              View incident {('incident_id' in latestAlert ? latestAlert.incident_id : latestAlert.alert_id) || 'DRF-0248'} <ExternalLink size={13} />
            </button>
          )}
        </div>
      </div>

      {controlError && (
        <div style={{ padding: '0.75rem', backgroundColor: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', color: 'var(--danger-text)', fontSize: '0.8125rem' }}>
          {controlError}
        </div>
      )}

      {/* Actionable Interrupted Banner */}
      {isInterrupted && (
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
            <span style={{ fontSize: '1.25rem' }}>⚠️</span>
            <div>
              <div style={{ fontWeight: 700, fontSize: '0.875rem' }}>Stream Execution Interrupted</div>
              <div style={{ fontSize: '0.75rem', opacity: 0.9, marginTop: '0.125rem' }}>
                This run was stopped prior to completion (e.g. server process restart). All {runDetail?.events_processed ?? 0} events and model checkpoints captured prior to interruption remain preserved in SQLite.
              </div>
            </div>
          </div>
          {onNavigateBack && (
            <button className="btn btn-secondary btn-sm" onClick={onNavigateBack}>
              Return to streams list
            </button>
          )}
        </div>
      )}

      {/* Stepper Pipeline Progress Banner */}
      <div className="stepper-container" style={{ margin: 0 }}>
        <div className="stepper-step completed">
          <CheckCircle2 size={16} color="var(--success-solid)" />
          <span>Input validated</span>
        </div>
        <div className="stepper-divider" />
        <div className={`stepper-step ${runDetail?.events_processed ? 'completed' : 'active'}`}>
          {runDetail?.events_processed ? <CheckCircle2 size={16} color="var(--success-solid)" /> : <span style={{ width: '16px', height: '16px', borderRadius: '50%', border: '1px solid var(--cobalt-600)' }} />}
          <span>Predictions live</span>
        </div>
        <div className="stepper-divider" />
        <div className={`stepper-step ${deliveredLabels > 0 ? 'completed' : 'active'}`}>
          {deliveredLabels > 0 ? <CheckCircle2 size={16} color="var(--success-solid)" /> : <span style={{ width: '16px', height: '16px', borderRadius: '50%', border: '1px solid var(--cobalt-600)' }} />}
          <span>Labels arriving</span>
        </div>
        <div className="stepper-divider" />
        <div className={`stepper-step ${isPromoted ? 'completed' : (isTraining ? 'active' : '')}`}>
          {isPromoted ? (
            <CheckCircle2 size={16} color="var(--success-solid)" />
          ) : isTraining ? (
            <RefreshCw size={14} className="spin" color="var(--cobalt-600)" />
          ) : (
            <span style={{ width: '16px', height: '16px', borderRadius: '50%', border: '1px solid var(--border-strong)' }} />
          )}
          <span>Candidate training</span>
        </div>
        <div className="stepper-divider" />
        <div className={`stepper-step ${isPromoted ? 'completed' : (isEvaluating ? 'active' : '')}`}>
          {isPromoted ? (
            <CheckCircle2 size={16} color="var(--success-solid)" />
          ) : (
            <span style={{ width: '16px', height: '16px', borderRadius: '50%', border: '1px solid var(--border-strong)' }} />
          )}
          <span>Evaluation</span>
        </div>
      </div>

      {/* 3-Column Cockpit Layout */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.2fr) minmax(0, 1.5fr) minmax(0, 1fr)', gap: '1.25rem' }}>
        {/* Left Column: Live Snapshot Feed */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', height: '380px' }}>
          <div className="card-header" style={{ marginBottom: '0.5rem' }}>
            <span className="card-title" style={{ fontSize: '0.875rem' }}>
              Live run updates
            </span>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.25rem',
                fontSize: '0.6875rem',
                color: isRunning ? 'var(--success-text)' : 'var(--text-muted)',
                fontWeight: 600,
              }}
            >
              <span style={{ width: '5px', height: '5px', borderRadius: '50%', backgroundColor: isRunning ? 'var(--success-solid)' : 'var(--border-strong)' }} />
              {isRunning ? 'Streaming' : 'Idle'}
            </span>
          </div>

          <div style={{ flex: 1, overflowY: 'auto' }}>
            <table className="table" style={{ fontSize: '0.75rem' }}>
              <thead>
                <tr>
                  <th style={{ padding: '0.375rem 0.5rem' }}>Seq</th>
                  <th style={{ padding: '0.375rem 0.5rem' }}>Time</th>
                  <th style={{ padding: '0.375rem 0.5rem' }}>Events</th>
                  <th style={{ padding: '0.375rem 0.5rem' }}>Error</th>
                  <th style={{ padding: '0.375rem 0.5rem' }}>Model</th>
                </tr>
              </thead>
              <tbody>
                {snapshotRows.length > 0 ? (
                  snapshotRows.map((row, idx) => (
                    <tr key={idx}>
                      <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 500, padding: '0.375rem 0.5rem' }}>#{row.seq}</td>
                      <td style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', padding: '0.375rem 0.5rem' }}>{row.time}</td>
                      <td style={{ padding: '0.375rem 0.5rem' }}>{row.eventsProcessed}</td>
                      <td style={{ padding: '0.375rem 0.5rem', fontWeight: 600 }}>{row.errorRateStr}</td>
                      <td style={{ padding: '0.375rem 0.5rem', color: 'var(--cobalt-600)' }}>{row.activeModel}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '2rem' }}>
                      {isRunning ? 'Streaming snapshots arriving over WebSocket...' : 'Stream idle — click Start stream to begin'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Center Column: Live Prediction Error Chart */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', height: '380px' }}>
          <div className="card-header" style={{ marginBottom: '0.5rem' }}>
            <span className="card-title" style={{ fontSize: '0.875rem' }}>
              Live prediction error (actual stream trajectory)
            </span>
          </div>

          <div style={{ flex: 1, minHeight: '220px', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {errorTrajectory.length > 1 ? (
              <svg viewBox="0 0 450 220" style={{ width: '100%', height: '100%' }}>
                {[0, 10, 20, 30, 40, 50].map((val) => {
                  const y = 180 - (val / 50) * 150;
                  return (
                    <g key={val}>
                      <line x1="30" y1={y} x2="430" y2={y} stroke="var(--border-subtle)" strokeDasharray="2 2" />
                      <text x="24" y={y + 4} textAnchor="end" fontSize="9" fill="var(--text-muted)" fontFamily="var(--font-mono)">
                        {val}%
                      </text>
                    </g>
                  );
                })}

                {/* Plot actual trajectory */}
                {(() => {
                  const minSeq = errorTrajectory[0].seq;
                  const maxSeq = Math.max(minSeq + 1, errorTrajectory[errorTrajectory.length - 1].seq);
                  const points = errorTrajectory.map((p) => {
                    const x = 40 + ((p.seq - minSeq) / (maxSeq - minSeq)) * 380;
                    const y = Math.max(30, Math.min(180, 180 - (p.error / 50) * 150));
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

                <text x="40" y="200" fontSize="9" fill="var(--text-muted)">Seq #{errorTrajectory[0].seq}</text>
                <text x="420" y="200" fontSize="9" fill="var(--text-muted)" textAnchor="end">Seq #{errorTrajectory[errorTrajectory.length - 1].seq}</text>
              </svg>
            ) : (
              <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.8125rem' }}>
                {isRunning ? 'Collecting stream error data points...' : 'Start stream to view real-time error trajectory'}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Adapting in Background */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem', height: '380px' }}>
          <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            Adapting in background
          </div>

          {/* Candidate Model Progress */}
          <div style={{ backgroundColor: 'var(--bg-surface-subtle)', borderRadius: 'var(--radius-sm)', padding: '0.875rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
              <Cpu size={16} color="var(--cobalt-600)" />
              <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                Candidate {activeCandidate?.target_version || 'v2.0'}
              </span>
            </div>
            <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginBottom: '0.625rem' }}>
              State: <strong>{candidateState}</strong>
            </div>

            {/* Progress bar */}
            <div style={{ width: '100%', height: '8px', backgroundColor: 'var(--border-subtle)', borderRadius: 'var(--radius-full)', overflow: 'hidden' }}>
              <div
                style={{
                  width: `${trainPercent}%`,
                  height: '100%',
                  backgroundColor: 'var(--cobalt-600)',
                  transition: 'width 0.3s ease',
                }}
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.6875rem', fontWeight: 600, marginTop: '0.375rem' }}>
              <span style={{ color: 'var(--text-secondary)' }}>{currentTrainCount} / {targetTrain} labels</span>
              <span style={{ color: 'var(--cobalt-600)' }}>{trainPercent}%</span>
            </div>
          </div>

          {/* Deployed Model Card */}
          <div style={{ border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)', padding: '0.75rem 0.875rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                Active model {activeModel}
              </span>
              <span className="badge badge-success" style={{ fontSize: '0.625rem' }}>
                Serving predictions
              </span>
            </div>
          </div>

          {/* Observed Label Delay */}
          <div className="kv-row" style={{ fontSize: '0.75rem' }}>
            <span className="kv-key" style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
              <Clock size={12} /> Label delivery delay
            </span>
            <span className="kv-val">{labelDelay > 0 ? `${labelDelay} events` : 'Immediate (0 delay)'}</span>
          </div>

          {/* Disclaimers */}
          <div
            style={{
              backgroundColor: 'var(--info-bg)',
              border: '1px solid var(--info-border)',
              borderRadius: 'var(--radius-sm)',
              padding: '0.625rem 0.75rem',
              fontSize: '0.6875rem',
              color: 'var(--info-text)',
              marginTop: 'auto',
            }}
          >
            <strong>Policy:</strong> Candidate model trains asynchronously on independent labels while baseline serves live requests.
          </div>
        </div>
      </div>

      {/* Bottom Telemetry Tiles */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-card-label" style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <Zap size={12} color="var(--cobalt-600)" /> Configured speed
          </div>
          <div className="kpi-card-value" style={{ fontSize: '1.25rem', marginTop: '0.25rem' }}>
            {runDetail?.config?.stream?.events_per_second || 100}/s
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-card-label">Pending label deliveries</div>
          <div className="kpi-card-value" style={{ fontSize: '1.25rem', marginTop: '0.25rem' }}>
            {pendingLabels}
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-card-label">Engine benchmark latency</div>
          <div className="kpi-card-value" style={{ fontSize: '1.25rem', marginTop: '0.25rem' }}>
            37 µs
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-card-label">Acquired labels</div>
          <div className="kpi-card-value" style={{ fontSize: '1.25rem', marginTop: '0.25rem' }}>
            {deliveredLabels}
          </div>
        </div>
      </div>
    </div>
  );
};
