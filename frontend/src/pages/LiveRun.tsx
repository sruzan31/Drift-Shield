import React, { useEffect, useRef, useState } from 'react';
import {
  Activity,
  AlertCircle,
  RefreshCw,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { api } from '../lib/api';
import { RunWebSocketClient } from '../lib/websocket';
import type { ConnectionStatus } from '../lib/websocket';
import type { IncidentItem, RunDetail, WebSocketSnapshotMessage } from '../types';
import { AccountingCard } from '../components/AccountingCard';
import { CandidateCard } from '../components/CandidateCard';
import { CumulativeChart } from '../components/CumulativeChart';
import type { ChartPoint } from '../components/CumulativeChart';
import { ControlBar } from '../components/ControlBar';
import { IncidentsTable } from '../components/IncidentsTable';
import { MetricsCard } from '../components/MetricsCard';
import { StatusBadge } from '../components/StatusBadge';

interface LiveRunProps {
  runId: string;
  onNavigateBack: () => void;
}

export const LiveRun: React.FC<LiveRunProps> = ({ runId, onNavigateBack }) => {
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [incidents, setIncidents] = useState<IncidentItem[]>([]);
  const [incidentsTotal, setIncidentsTotal] = useState(0);
  const [incidentsPage, setIncidentsPage] = useState(1);
  const [incidentsLoading, setIncidentsLoading] = useState(false);

  const [wsStatus, setWsStatus] = useState<ConnectionStatus>('idle');
  const [wsDetail, setWsDetail] = useState<string>('');
  const [chartPoints, setChartPoints] = useState<ChartPoint[]>([]);

  const [isLoading, setIsLoading] = useState(true);
  const [isControlling, setIsControlling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsClientRef = useRef<RunWebSocketClient | null>(null);
  const lastAlertsCountRef = useRef<number>(0);

  // 1. Fetch initial REST state
  const loadInitialState = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const detail = await api.getRunDetail(runId);
      setRunDetail(detail);

      // If run already has metrics, initialize chart point
      if (detail.metrics?.full_synthetic?.error_rate !== null && detail.metrics?.full_synthetic?.error_rate !== undefined) {
        setChartPoints([
          {
            sequence: 1,
            eventsProcessed: detail.events_processed,
            errorRate: detail.metrics.full_synthetic.error_rate,
            timestamp: Date.now(),
          },
        ]);
      }
    } catch (err: any) {
      setError(err?.message || `Failed to load run detail for '${runId}'`);
    } finally {
      setIsLoading(false);
    }
  };

  // 2. Fetch incidents from SQLite
  const loadIncidents = async (page = 1) => {
    setIncidentsLoading(true);
    try {
      const incData = await api.getIncidents(runId, page, 10);
      setIncidents(incData.items);
      setIncidentsTotal(incData.total);
      setIncidentsPage(page);
      lastAlertsCountRef.current = incData.total;
    } catch (err) {
      console.error('[LiveRun] Failed to load incidents:', err);
    } finally {
      setIncidentsLoading(false);
    }
  };

  // 3. Connect WebSocket on mount or runId change
  useEffect(() => {
    loadInitialState();
    loadIncidents(1);
    setChartPoints([]);

    const ws = new RunWebSocketClient({
      onMessage: (snapshot: WebSocketSnapshotMessage) => {
        // Update live run detail from snapshot
        setRunDetail((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            operational_state: snapshot.operational_state,
            state: snapshot.operational_state,
            candidate_state: snapshot.candidate_state || prev.candidate_state,
            events_processed: snapshot.events_processed,
            total_events: snapshot.total_events,
            progress_percent: snapshot.progress_percent,
            active_model_version: snapshot.active_model_version,
            monitoring_coverage: snapshot.monitoring_coverage,
            label_accounting: snapshot.label_accounting,
            metrics: snapshot.metrics !== undefined ? snapshot.metrics : prev.metrics,
            monitoring_summary: snapshot.monitoring_summary || prev.monitoring_summary,
            candidate_summary: snapshot.candidate_summary || prev.candidate_summary,
            paired_summary: snapshot.paired_summary || prev.paired_summary,
          };
        });

        // Record chart points if valid loss observation exists
        const errRate =
          snapshot.metrics?.full_synthetic?.error_rate ??
          snapshot.metrics?.random_monitoring?.error_rate;

        if (errRate !== null && errRate !== undefined) {
          setChartPoints((prev) => {
            const last = prev[prev.length - 1];
            if (!last || last.eventsProcessed !== snapshot.events_processed) {
              return [
                ...prev,
                {
                  sequence: snapshot.snapshot_sequence,
                  eventsProcessed: snapshot.events_processed,
                  errorRate: errRate,
                  timestamp: snapshot.timestamp,
                },
              ];
            }
            return prev;
          });
        }

        // Check if new incidents occurred; reload persisted incidents if count changed
        const newAlertsCount = snapshot.monitoring_summary?.alerts_count ?? 0;
        if (newAlertsCount !== lastAlertsCountRef.current) {
          loadIncidents(incidentsPage);
        }
      },
      onStatusChange: (status, detail) => {
        setWsStatus(status);
        setWsDetail(detail || '');
      },
    });

    ws.connect(runId);
    wsClientRef.current = ws;

    return () => {
      ws.disconnect();
    };
  }, [runId]);

  // 4. Handle lifecycle controls
  const handleControl = async (action: 'start' | 'pause' | 'resume' | 'stop') => {
    setIsControlling(true);
    setError(null);
    try {
      const res = await api.controlRun(runId, action);
      setRunDetail((prev) => (prev ? { ...prev, operational_state: res.current_state, state: res.current_state } : prev));
      // Refresh persisted incidents on stop
      if (action === 'stop') {
        setTimeout(() => loadIncidents(1), 500);
      }
    } catch (err: any) {
      setError(err?.message || `Control action '${action}' failed.`);
    } finally {
      setIsControlling(false);
    }
  };

  if (isLoading && !runDetail) {
    return (
      <div style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-muted)' }}>
        <Activity size={32} className="spin" style={{ margin: '0 auto 1rem auto', color: 'var(--cobalt-600)' }} />
        <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Loading Run '{runId}'...</div>
        <div style={{ fontSize: '0.8125rem', marginTop: '0.25rem' }}>Fetching SQLite metadata and opening WebSocket stream.</div>
      </div>
    );
  }

  if (error && !runDetail) {
    return (
      <div className="card" style={{ maxWidth: '600px', margin: '2rem auto', textAlign: 'center' }}>
        <AlertCircle size={32} color="var(--danger-solid)" style={{ margin: '0 auto 1rem auto' }} />
        <div style={{ fontWeight: 700, fontSize: '1.125rem', color: 'var(--danger-text)' }}>Failed to Load Run</div>
        <p style={{ color: 'var(--text-secondary)', margin: '0.5rem 0 1.5rem 0', fontSize: '0.875rem' }}>{error}</p>
        <button className="btn btn-secondary" onClick={onNavigateBack}>
          Return to Run History
        </button>
      </div>
    );
  }

  if (!runDetail) return null;

  const isTerminal = ['COMPLETED', 'STOPPED', 'INTERRUPTED'].includes(
    (runDetail.operational_state || '').toUpperCase()
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Top Breadcrumb & Metadata Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem', flexWrap: 'wrap' }}>
            <h1 style={{ fontSize: '1.375rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
              {runDetail.run_id}
            </h1>
            <StatusBadge status={runDetail.operational_state} />
            <span className="badge badge-neutral">{runDetail.scenario}</span>
            <span className="badge badge-neutral" style={{ fontFamily: 'var(--font-mono)' }}>
              Seed: {runDetail.seed}
            </span>
            {runDetail.parent_run_id && (
              <span className="badge badge-info" title="Deterministic replay lineage">
                Parent: {runDetail.parent_run_id}
              </span>
            )}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            Created: {new Date(runDetail.created_at * 1000).toLocaleString()} • Schema {runDetail.schema_version}
          </div>
        </div>

        {/* WebSocket Connection State Pill */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.375rem',
              padding: '0.25rem 0.625rem',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.75rem',
              fontWeight: 500,
              backgroundColor:
                wsStatus === 'connected'
                  ? 'var(--success-bg)'
                  : wsStatus === 'reconnecting'
                  ? 'var(--warning-bg)'
                  : 'var(--danger-bg)',
              color:
                wsStatus === 'connected'
                  ? 'var(--success-text)'
                  : wsStatus === 'reconnecting'
                  ? 'var(--warning-text)'
                  : 'var(--danger-text)',
              border: `1px solid ${
                wsStatus === 'connected'
                  ? 'var(--success-border)'
                  : wsStatus === 'reconnecting'
                  ? 'var(--warning-border)'
                  : 'var(--danger-border)'
              }`,
            }}
          >
            {wsStatus === 'connected' ? <Wifi size={12} /> : <WifiOff size={12} />}
            <span>
              {wsStatus === 'connected'
                ? 'Live WebSocket (500ms)'
                : wsStatus === 'reconnecting'
                ? wsDetail || 'Reconnecting...'
                : isTerminal
                ? 'Persisted Run (History Loaded)'
                : wsDetail || 'Disconnected'}
            </span>
          </div>

          <button
            className="btn btn-secondary btn-sm"
            onClick={loadInitialState}
            title="Refresh state from REST API"
          >
            <RefreshCw size={12} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div
          style={{
            padding: '0.75rem 1rem',
            backgroundColor: 'var(--danger-bg)',
            color: 'var(--danger-text)',
            border: '1px solid var(--danger-border)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.8125rem',
          }}
        >
          {error}
        </div>
      )}

      {/* Control Bar */}
      <ControlBar
        operationalState={runDetail.operational_state}
        onControl={handleControl}
        isLoading={isControlling}
      />

      {/* Progress & Model Version Strip */}
      <div className="card" style={{ padding: '1rem 1.25rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem', flexWrap: 'wrap', gap: '0.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              Stream Ingestion Progress
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
              {runDetail.events_processed} / {runDetail.total_events} events ({runDetail.progress_percent.toFixed(1)}%)
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '0.8125rem' }}>
            <span style={{ color: 'var(--text-muted)' }}>Deployed Model Version:</span>
            <span className="badge badge-info" style={{ fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
              {runDetail.active_model_version}
            </span>
          </div>
        </div>

        <div
          style={{
            width: '100%',
            height: '8px',
            backgroundColor: 'var(--border-subtle)',
            borderRadius: '4px',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: `${Math.min(100, runDetail.progress_percent)}%`,
              height: '100%',
              backgroundColor: isTerminal ? 'var(--success-solid)' : 'var(--cobalt-600)',
              transition: 'width 0.3s ease',
            }}
          />
        </div>
      </div>

      {/* 2-Column Dashboard Layout */}
      <div className="grid-2">
        {/* Candidate & Statistical Evaluation */}
        <CandidateCard
          candidateState={runDetail.candidate_state}
          candidateSummary={runDetail.candidate_summary}
          pairedSummary={runDetail.paired_summary}
          activeModelVersion={runDetail.active_model_version}
        />

        {/* Label Accounting & Budget */}
        <AccountingCard
          accounting={runDetail.label_accounting}
          monitoringCoverage={runDetail.monitoring_coverage}
          labelBudget={runDetail.config?.labels?.label_budget ?? 300}
        />
      </div>

      {/* Cumulative Error Trajectory Chart */}
      <CumulativeChart
        points={chartPoints}
        totalEvents={runDetail.total_events}
      />

      {/* Evaluated Metric Windows Card */}
      <MetricsCard
        metrics={runDetail.metrics}
        isComplete={isTerminal}
      />

      {/* Incidents and Alerts Evidence Table */}
      <IncidentsTable
        incidents={incidents}
        totalIncidents={incidentsTotal}
        page={incidentsPage}
        pageSize={10}
        onPageChange={loadIncidents}
        isLoading={incidentsLoading}
      />
    </div>
  );
};
