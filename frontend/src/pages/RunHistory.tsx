import React, { useEffect, useState } from 'react';
import {
  Database,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  Play,
  ExternalLink,
  Search,
  CheckCircle2,
  Clock,
} from 'lucide-react';
import { api } from '../lib/api';
import type { PaginatedResponse, RunSummary } from '../types';
import { StatusBadge } from '../components/StatusBadge';

interface RunHistoryProps {
  onSelectRun: (runId: string) => void;
  onNavigateNew: () => void;
}

export const RunHistory: React.FC<RunHistoryProps> = ({ onSelectRun, onNavigateNew }) => {
  const [runsData, setRunsData] = useState<PaginatedResponse<RunSummary> | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const [scenarioFilter, setScenarioFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRuns = async (targetPage: number) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getRuns(targetPage, pageSize);
      setRunsData(data);
      setPage(targetPage);
    } catch (err: any) {
      setError(err?.message || 'Failed to fetch saved runs from backend');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchRuns(1);
  }, []);

  const totalPages = runsData ? Math.max(1, Math.ceil(runsData.total / pageSize)) : 1;

  // Filtered items
  const filteredItems = (runsData?.items || []).filter((r) => {
    if (scenarioFilter !== 'all' && r.scenario !== scenarioFilter) return false;
    if (searchQuery.trim() !== '') {
      const q = searchQuery.toLowerCase();
      return r.run_id.toLowerCase().includes(q) || r.scenario.toLowerCase().includes(q);
    }
    return true;
  });

  const totalCompleted = (runsData?.items || []).filter(r => r.state === 'COMPLETED').length;
  const totalRunning = (runsData?.items || []).filter(r => r.state === 'RUNNING' || r.state === 'WARMUP').length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.625rem', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
            Streams & simulation runs
          </h1>
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem', marginTop: '0.125rem' }}>
            Persisted simulation ledger with exact reproducible random seeds.
          </div>
        </div>

        {/* Filter & Action Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem', flexWrap: 'wrap' }}>
          {/* Search Box */}
          <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
            <Search size={14} style={{ position: 'absolute', left: '0.625rem', color: 'var(--text-muted)' }} />
            <input
              type="text"
              placeholder="Search runs, scenarios..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                padding: '0.375rem 0.75rem 0.375rem 2rem',
                fontSize: '0.75rem',
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
                outline: 'none',
                width: '190px',
              }}
            />
          </div>

          {/* Scenario Filter */}
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

          <button className="btn btn-secondary btn-sm" onClick={() => fetchRuns(page)} disabled={isLoading}>
            <RefreshCw size={13} className={isLoading ? 'spin' : ''} /> Refresh
          </button>

          <button className="btn btn-primary btn-sm" onClick={onNavigateNew} style={{ fontWeight: 600 }}>
            <Play size={13} fill="currentColor" /> Connect a stream
          </button>
        </div>
      </div>

      {/* 4 Summary Stats Cards from Actual Backend Counts */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-card-header">
            <span className="kpi-card-label">Total recorded runs</span>
            <Database size={16} color="var(--cobalt-600)" />
          </div>
          <div className="kpi-card-value">{runsData ? runsData.total : '—'}</div>
          <div className="kpi-card-subtitle">SQLite persistent store</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-card-header">
            <span className="kpi-card-label">Completed runs</span>
            <CheckCircle2 size={16} color="var(--success-solid)" />
          </div>
          <div className="kpi-card-value">{runsData ? totalCompleted : '—'}</div>
          <div className="kpi-card-subtitle">On current page</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-card-header">
            <span className="kpi-card-label">Active runs</span>
            <Clock size={16} color="var(--cobalt-600)" />
          </div>
          <div className="kpi-card-value">{runsData ? totalRunning : '—'}</div>
          <div className="kpi-card-subtitle">RUNNING or WARMUP</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-card-header">
            <span className="kpi-card-label">Scenarios available</span>
            <Play size={16} color="var(--cobalt-600)" />
          </div>
          <div className="kpi-card-value">6</div>
          <div className="kpi-card-subtitle">Stationary, Abrupt, Gradual...</div>
        </div>
      </div>

      {error && (
        <div className="card" style={{ backgroundColor: 'var(--danger-bg)', borderColor: 'var(--danger-border)', color: 'var(--danger-text)', padding: '0.75rem 1rem' }}>
          {error}
        </div>
      )}

      {/* Runs Table Card */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '0.875rem 1.25rem', borderBottom: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            Streams & Runs Ledger
          </span>
          {error && !runsData ? (
            <span className="badge badge-danger" style={{ fontSize: '0.6875rem' }}>
              Load failed
            </span>
          ) : (
            <span className="badge badge-neutral" style={{ fontSize: '0.6875rem' }}>
              {runsData ? `${filteredItems.length} Runs` : '—'}
            </span>
          )}
        </div>

        {isLoading && !runsData ? (
          <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
            Loading runs from SQLite...
          </div>
        ) : error && !runsData ? (
          <div style={{ padding: '3rem 1rem', textAlign: 'center', color: 'var(--text-muted)' }}>
            <Database size={28} style={{ margin: '0 auto 0.5rem auto', color: 'var(--danger-solid)', opacity: 0.8 }} />
            <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Failed to load simulation runs</div>
            <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>{error}</div>
            <button onClick={() => fetchRuns(page)} className="btn btn-secondary btn-sm" style={{ marginTop: '0.75rem' }}>
              <RefreshCw size={12} /> Retry
            </button>
          </div>
        ) : filteredItems.length === 0 ? (
          <div style={{ padding: '3rem 1rem', textAlign: 'center', color: 'var(--text-muted)' }}>
            <Database size={28} style={{ margin: '0 auto 0.5rem auto', opacity: 0.5 }} />
            <div style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>No runs match criteria</div>
          </div>
        ) : (
          <div className="table-wrapper" style={{ border: 'none', borderRadius: 0 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>Scenario</th>
                  <th>Events</th>
                  <th>Seed</th>
                  <th>Created</th>
                  <th>State</th>
                  <th style={{ textAlign: 'right' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.map((r) => {
                  return (
                    <tr key={r.run_id}>
                      <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                        {r.run_id}
                        {r.parent_run_id && (
                          <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                            replay of {r.parent_run_id}
                          </div>
                        )}
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
                      <td>{r.seed}</td>
                      <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        {r.created_at ? new Date(r.created_at * 1000).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—'}
                      </td>
                      <td>
                        <StatusBadge status={r.state} />
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => onSelectRun(r.run_id)}
                        >
                          <ExternalLink size={12} /> Open Run
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {runsData && runsData.total > 0 && (
          <div
            style={{
              padding: '0.75rem 1.25rem',
              borderTop: '1px solid var(--border-subtle)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: '0.75rem',
              color: 'var(--text-muted)',
            }}
          >
            <span>
              Page {page} of {totalPages} ({runsData.total} total runs)
            </span>
            <div style={{ display: 'flex', gap: '0.375rem' }}>
              <button
                className="btn btn-secondary btn-sm"
                disabled={page <= 1 || isLoading}
                onClick={() => fetchRuns(page - 1)}
              >
                <ChevronLeft size={12} /> Previous
              </button>
              <button
                className="btn btn-secondary btn-sm"
                disabled={page >= totalPages || isLoading}
                onClick={() => fetchRuns(page + 1)}
              >
                Next <ChevronRight size={12} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
