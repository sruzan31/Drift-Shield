import React, { useEffect, useState } from 'react';
import {
  Database,
  TrendingUp,
  Download,
  Search,
  CheckCircle2,
  Calendar,
  Layers,
  Activity,
  FileText,
} from 'lucide-react';
import { api } from '../lib/api';
import type { PaginatedResponse, RunSummary, RunDetail, IncidentItem } from '../types';

interface ReportsProps {
  onSelectRun: (runId: string) => void;
  onNavigateNew: () => void;
}

export const Reports: React.FC<ReportsProps> = ({ onSelectRun }) => {
  const [runsData, setRunsData] = useState<PaginatedResponse<RunSummary> | null>(null);
  const [selectedRunDetail, setSelectedRunDetail] = useState<RunDetail | null>(null);
  const [selectedIncident, setSelectedIncident] = useState<IncidentItem | null>(null);
  const [scenarioFilter, setScenarioFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadRuns = async () => {
      setError(null);
      try {
        const data = await api.getRuns(1, 20);
        setRunsData(data);
        if (data.items.length > 0) {
          const firstRun = data.items[0];
          const detail = await api.getRunDetail(firstRun.run_id);
          setSelectedRunDetail(detail);

          const incRes = await api.getIncidents(firstRun.run_id, 1, 1);
          if (incRes.items.length > 0) {
            setSelectedIncident(incRes.items[0]);
          }
        }
      } catch (err: any) {
        setError(err?.message || 'Failed to load reports ledger');
      }
    };
    loadRuns();
  }, []);

  const handleSelectRunRow = async (runId: string) => {
    try {
      const detail = await api.getRunDetail(runId);
      setSelectedRunDetail(detail);
      const incRes = await api.getIncidents(runId, 1, 1);
      if (incRes.items.length > 0) {
        setSelectedIncident(incRes.items[0]);
      } else {
        setSelectedIncident(null);
      }
    } catch (err) {
      console.error('Failed to load run detail:', err);
    }
  };

  const handleDownloadReport = (format: 'csv' | 'json') => {
    if (!selectedRunDetail) return;
    const data = {
      run_id: selectedRunDetail.run_id,
      scenario: selectedRunDetail.scenario,
      events_processed: selectedRunDetail.events_processed,
      total_events: selectedRunDetail.total_events,
      state: selectedRunDetail.state,
      operational_state: selectedRunDetail.operational_state,
      active_model_version: selectedRunDetail.active_model_version,
      metrics: selectedRunDetail.metrics,
      monitoring_summary: selectedRunDetail.monitoring_summary,
      candidate_summary: selectedRunDetail.candidate_summary,
      paired_summary: selectedRunDetail.paired_summary,
      label_accounting: selectedRunDetail.label_accounting,
      incident: selectedIncident,
    };

    let content = '';
    let mimeType = '';
    let filename = `driftshield_summary_${selectedRunDetail.run_id}.${format}`;

    const activeCandidate = selectedRunDetail.candidate_summary?.candidates?.[0];
    const pairedSession = selectedRunDetail.paired_summary?.sessions?.[0];
    const activeErr = selectedRunDetail.metrics?.full_synthetic?.error_rate ?? selectedRunDetail.metrics?.monitor_channel?.error_rate ?? selectedRunDetail.metrics?.random_monitoring?.error_rate ?? 0;

    if (format === 'json') {
      content = JSON.stringify(data, null, 2);
      mimeType = 'application/json';
    } else {
      // CSV format
      const rows = [
        ['Field', 'Value'],
        ['Run ID', selectedRunDetail.run_id],
        ['Scenario', selectedRunDetail.scenario],
        ['Events Processed', selectedRunDetail.events_processed.toString()],
        ['Total Events', selectedRunDetail.total_events.toString()],
        ['State', selectedRunDetail.state],
        ['Active Model', selectedRunDetail.active_model_version || 'v1.0-frozen'],
        ['Active Error Rate', (activeErr * 100).toFixed(2) + '%'],
        ['Candidate Version', activeCandidate?.target_version || 'None'],
        ['Candidate State', activeCandidate?.state || 'NONE'],
        ['Candidate Gain', pairedSession?.gain != null ? (pairedSession.gain * 100).toFixed(2) + '%' : 'N/A'],
        ['Paired b (Cand Correct, Active Wrong)', (pairedSession?.b ?? 0).toString()],
        ['Paired c (Active Correct, Cand Wrong)', (pairedSession?.c ?? 0).toString()],
        ['Total Budget Debits', (selectedRunDetail.label_accounting?.budget_debits ?? 0).toString()],
        ['Total Unique Labels', (selectedRunDetail.label_accounting?.total_unique_acquisitions ?? 0).toString()],
      ];
      content = rows.map((r) => r.map((c) => `"${c.replace(/"/g, '""')}"`).join(',')).join('\n');
      mimeType = 'text/csv';
    }

    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const filteredRuns = (runsData?.items || []).filter((r) => {
    if (scenarioFilter !== 'all' && r.scenario !== scenarioFilter) return false;
    if (searchQuery.trim() !== '') {
      const q = searchQuery.toLowerCase();
      return r.run_id.toLowerCase().includes(q) || r.scenario.toLowerCase().includes(q);
    }
    return true;
  });

  const totalCompletedCount = (runsData?.items || []).filter(r => r.state === 'COMPLETED').length;

  const pairedSession = selectedRunDetail?.paired_summary?.sessions?.[0];
  const activeCandidate = selectedRunDetail?.candidate_summary?.candidates?.[0];
  const activeErrRate = selectedRunDetail?.metrics?.full_synthetic?.error_rate ?? selectedRunDetail?.metrics?.monitor_channel?.error_rate ?? selectedRunDetail?.metrics?.random_monitoring?.error_rate;
  const activeErrStr = activeErrRate != null ? `${(activeErrRate * 100).toFixed(1)}%` : 'N/A';
  const gainStr = pairedSession?.gain != null ? `+${(pairedSession.gain * 100).toFixed(1)} pp` : '—';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.625rem', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
            Runs, incidents & reports
          </h1>
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginTop: '0.125rem' }}>
            Audit ledger of model decisions, label accounting, and paired evaluation reports.
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          <div style={{ position: 'relative' }}>
            <Search size={13} style={{ position: 'absolute', left: '0.625rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input
              type="text"
              placeholder="Search runs, scenarios or incidents..."
              className="form-input"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ paddingLeft: '1.875rem', fontSize: '0.75rem', width: '240px' }}
            />
          </div>

          <select
            className="form-select"
            value={scenarioFilter}
            onChange={(e) => setScenarioFilter(e.target.value)}
            style={{ padding: '0.375rem 0.75rem', fontSize: '0.75rem' }}
          >
            <option value="all">All scenarios</option>
            <option value="abrupt">Abrupt drift</option>
            <option value="stationary">Stationary</option>
            <option value="gradual">Gradual</option>
            <option value="recurring">Recurring</option>
            <option value="rare_region">Rare region</option>
            <option value="adversary">Adversary</option>
          </select>

          <button className="btn btn-secondary btn-sm" style={{ fontSize: '0.75rem' }}>
            <Calendar size={13} /> Saved Ledger
          </button>

          <button
            className="btn btn-primary btn-sm"
            onClick={() => handleDownloadReport('json')}
            disabled={!selectedRunDetail}
            style={{ fontWeight: 600 }}
          >
            <Download size={13} /> Export summary report
          </button>
        </div>
      </div>

      {/* 4 Summary Stats Cards from Actual Backend Data */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-card-header">
            <span className="kpi-card-label">Total recorded runs</span>
            <Database size={16} color="var(--cobalt-600)" />
          </div>
          <div className="kpi-card-value">{runsData ? runsData.total : '—'}</div>
          <div className="kpi-card-subtitle">SQLite persistent ledger</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-card-header">
            <span className="kpi-card-label">Completed runs</span>
            <CheckCircle2 size={16} color="var(--success-solid)" />
          </div>
          <div className="kpi-card-value">{runsData ? totalCompletedCount : '—'}</div>
          <div className="kpi-card-subtitle">On current page</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-card-header">
            <span className="kpi-card-label">Selected run state</span>
            <TrendingUp size={16} color="var(--cobalt-600)" />
          </div>
          <div className="kpi-card-value" style={{ fontSize: '1.25rem' }}>
            {selectedRunDetail?.state || '—'}
          </div>
          <div className="kpi-card-subtitle">{selectedRunDetail?.run_id || 'No run selected'}</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-card-header">
            <span className="kpi-card-label">Selected run labels</span>
            <FileText size={16} color="var(--cobalt-600)" />
          </div>
          <div className="kpi-card-value">
            {selectedRunDetail?.label_accounting?.total_unique_acquisitions ?? '—'}
          </div>
          <div className="kpi-card-subtitle">Unique acquired labels</div>
        </div>
      </div>

      {error && (
        <div className="card" style={{ backgroundColor: 'var(--danger-bg)', borderColor: 'var(--danger-border)', color: 'var(--danger-text)', padding: '0.75rem 1rem' }}>
          {error}
        </div>
      )}

      {/* Ledger Table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          {error && !runsData ? (
            <div style={{ padding: '3rem 1rem', textAlign: 'center', color: 'var(--text-muted)' }}>
              <Database size={28} style={{ margin: '0 auto 0.5rem auto', color: 'var(--danger-solid)', opacity: 0.8 }} />
              <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Failed to load simulation runs</div>
              <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>{error}</div>
            </div>
          ) : (
            <table className="table" style={{ fontSize: '0.8125rem' }}>
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Scenario</th>
                  <th>Events</th>
                  <th>State</th>
                  <th>Seed</th>
                  <th>Created</th>
                  <th style={{ textAlign: 'right' }}>View Live</th>
                </tr>
              </thead>
              <tbody>
                {filteredRuns.length === 0 ? (
                  <tr>
                    <td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                      No runs recorded
                    </td>
                  </tr>
                ) : (
                  filteredRuns.map((r) => {
                    const isSelected = selectedRunDetail?.run_id === r.run_id;
                    return (
                      <tr
                        key={r.run_id}
                        onClick={() => handleSelectRunRow(r.run_id)}
                        style={{
                          cursor: 'pointer',
                          backgroundColor: isSelected ? 'var(--cobalt-50)' : 'transparent',
                        }}
                      >
                        <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            {isSelected && <span style={{ width: '3px', height: '14px', backgroundColor: 'var(--cobalt-600)', borderRadius: '2px' }} />}
                            <span>{r.run_id}</span>
                          </div>
                        </td>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                            <span style={{ fontWeight: 500 }}>Equipment {r.scenario}</span>
                            <span className="badge badge-info" style={{ fontSize: '0.5625rem', padding: '0.1rem 0.35rem' }}>
                              Synthetic
                            </span>
                          </div>
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)' }}>{r.config?.stream?.n_events ? r.config.stream.n_events.toLocaleString() : '—'}</td>
                        <td>
                          <span className={`badge ${r.state === 'COMPLETED' ? 'badge-success' : (r.state === 'RUNNING' ? 'badge-info' : 'badge-neutral')}`} style={{ fontSize: '0.6875rem' }}>
                            {r.state}
                          </span>
                        </td>
                        <td>{r.seed}</td>
                        <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          {r.created_at ? new Date(r.created_at * 1000).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—'}
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              onSelectRun(r.run_id);
                            }}
                          >
                            <Activity size={12} /> Live
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Comparison Report Breakdown Section from Actual Loaded Data */}
      {selectedRunDetail && (
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
              <span style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                {selectedRunDetail.run_id} summary report
              </span>
              <span className="badge badge-info" style={{ fontSize: '0.6875rem', fontFamily: 'var(--font-mono)' }}>
                {selectedRunDetail.state}
              </span>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Equipment {selectedRunDetail.scenario}
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                Generated {selectedRunDetail.created_at ? new Date(selectedRunDetail.created_at * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'Recent'}
              </span>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => handleDownloadReport('csv')}
                style={{ fontSize: '0.75rem' }}
              >
                <FileText size={12} /> Download Summary CSV
              </button>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => handleDownloadReport('json')}
                style={{ fontSize: '0.75rem' }}
              >
                <Download size={12} /> Download Summary JSON
              </button>
            </div>
          </div>

          {/* 4 Columns Comparison Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: '1.25rem' }}>
            {/* 1. Configuration */}
            <div>
              <div style={{ fontSize: '0.8125rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                <Layers size={13} color="var(--cobalt-600)" /> 1. Configuration
              </div>
              <div className="kv-list">
                <div className="kv-row">
                  <span className="kv-key">Scenario</span>
                  <span className="kv-val">{selectedRunDetail.scenario}</span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">Pacing</span>
                  <span className="kv-val">{selectedRunDetail.config?.stream?.events_per_second || 100} events/s</span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">Active model</span>
                  <span className="kv-val">{selectedRunDetail.active_model_version || 'v1.0-frozen'}</span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">Candidate version</span>
                  <span className="kv-val">{activeCandidate?.target_version || 'None'}</span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">Label delay</span>
                  <span className="kv-val">{selectedRunDetail.config?.labels?.label_delay || 0} events</span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">Budget debits</span>
                  <span className="kv-val">{selectedRunDetail.label_accounting?.budget_debits ?? 0}</span>
                </div>
              </div>
            </div>

            {/* 2. Evidence */}
            <div>
              <div style={{ fontSize: '0.8125rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                <Activity size={13} color="var(--cobalt-600)" /> 2. Evidence
              </div>
              <div className="kv-list">
                <div className="kv-row">
                  <span className="kv-key">Events processed</span>
                  <span className="kv-val">{selectedRunDetail.events_processed.toLocaleString()}</span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">Total stream events</span>
                  <span className="kv-val">{selectedRunDetail.total_events.toLocaleString()}</span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">Alert sequence</span>
                  <span className="kv-val">{selectedIncident?.event_sequence ? `#${selectedIncident.event_sequence}` : 'None'}</span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">Detection delay</span>
                  <span className="kv-val">{selectedIncident?.detection_delay != null ? `${selectedIncident.detection_delay} events` : '—'}</span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">Unique labels</span>
                  <span className="kv-val">{selectedRunDetail.label_accounting?.total_unique_acquisitions ?? 0}</span>
                </div>
              </div>
            </div>

            {/* 3. Evaluation */}
            <div>
              <div style={{ fontSize: '0.8125rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                <TrendingUp size={13} color="var(--teal-600)" /> 3. Evaluation
              </div>
              <div className="kv-list">
                <div className="kv-row">
                  <span className="kv-key">Active model error</span>
                  <span className="kv-val">{activeErrStr}</span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">Candidate state</span>
                  <span className="kv-val" style={{ color: 'var(--teal-600)' }}>
                    {selectedRunDetail.candidate_state || 'NONE'}
                  </span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">Observed paired gain</span>
                  <span className="kv-val" style={{ color: pairedSession?.gain ? 'var(--success-text)' : 'inherit' }}>
                    {gainStr}
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
              </div>
            </div>

            {/* 4. Decision */}
            <div>
              <div style={{ fontSize: '0.8125rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                <CheckCircle2 size={13} color="var(--success-solid)" /> 4. Decision
              </div>
              <div className="kv-list">
                <div className="kv-row">
                  <span className="kv-key">Run State</span>
                  <span className="kv-val">
                    <span className="badge badge-neutral" style={{ fontSize: '0.625rem' }}>{selectedRunDetail.state}</span>
                  </span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">Candidate decision</span>
                  <span className="kv-val" style={{ fontWeight: 600, color: pairedSession?.decision === 'PROMOTE' ? 'var(--success-text)' : 'var(--text-primary)' }}>
                    {pairedSession?.decision || (selectedRunDetail.candidate_state === 'PROMOTED' ? 'PROMOTED' : 'NONE')}
                  </span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">Engine policy</span>
                  <span className="kv-val" style={{ fontSize: '0.6875rem', textAlign: 'right' }}>
                    Automated McNemar significance.
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', borderTop: '1px solid var(--border-subtle)', paddingTop: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
            <span>ⓘ Summary Exports: Downloads contain run configuration, error metrics, label accounting, and paired test decisions.</span>
          </div>
        </div>
      )}
    </div>
  );
};
