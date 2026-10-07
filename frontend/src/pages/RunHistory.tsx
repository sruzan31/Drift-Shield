import React, { useEffect, useState } from 'react';
import { Database, RefreshCw, ChevronLeft, ChevronRight, Play, ExternalLink } from 'lucide-react';
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
      setError(err?.message || 'Failed to fetch saved runs');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchRuns(1);
  }, []);

  const totalPages = runsData ? Math.max(1, Math.ceil(runsData.total / pageSize)) : 1;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Top Action Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            Persisted Run History
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
            SQLite durable simulation records, execution lifecycles, and model promotions.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button className="btn btn-secondary" onClick={() => fetchRuns(page)} disabled={isLoading}>
            <RefreshCw size={14} className={isLoading ? 'spin' : ''} /> Refresh History
          </button>
          <button className="btn btn-primary" onClick={onNavigateNew}>
            <Play size={14} /> New Simulation Run
          </button>
        </div>
      </div>

      {error && (
        <div
          style={{
            padding: '1rem',
            backgroundColor: 'var(--danger-bg)',
            color: 'var(--danger-text)',
            border: '1px solid var(--danger-border)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.875rem',
          }}
        >
          {error}
        </div>
      )}

      {/* Runs Table Card */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <Database size={16} color="var(--cobalt-600)" />
            Saved Runs
          </span>
          <span className="badge badge-neutral" style={{ fontSize: '0.6875rem' }}>
            {runsData?.total ?? 0} Total Runs
          </span>
        </div>

        {isLoading && !runsData ? (
          <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
            Loading persisted runs from SQLite...
          </div>
        ) : !runsData || runsData.items.length === 0 ? (
          <div
            style={{
              padding: '3rem 1rem',
              textAlign: 'center',
              backgroundColor: 'var(--bg-surface-subtle)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--text-muted)',
            }}
          >
            <Database size={28} style={{ margin: '0 auto 0.75rem auto', opacity: 0.5 }} />
            <div style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>No runs found</div>
            <div style={{ fontSize: '0.8125rem', marginTop: '0.25rem' }}>
              Create a new simulation run to begin tracking drift monitoring.
            </div>
            <button className="btn btn-primary btn-sm" onClick={onNavigateNew} style={{ marginTop: '1rem' }}>
              Create First Run
            </button>
          </div>
        ) : (
          <>
            <div className="table-wrapper">
              <table className="table">
                <thead>
                  <tr>
                    <th>Run ID</th>
                    <th>Scenario</th>
                    <th>Seed</th>
                    <th>State</th>
                    <th>Created</th>
                    <th>Completed</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {runsData.items.map((r) => (
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
                        <span className="badge badge-neutral">{r.scenario}</span>
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{r.seed}</td>
                      <td>
                        <StatusBadge status={r.state} />
                      </td>
                      <td style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                        {new Date(r.created_at * 1000).toLocaleString()}
                      </td>
                      <td style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                        {r.completed_at ? new Date(r.completed_at * 1000).toLocaleString() : '—'}
                      </td>
                      <td>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => onSelectRun(r.run_id)}
                        >
                          <ExternalLink size={12} /> Open Live
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginTop: '1rem',
                  fontSize: '0.8125rem',
                  color: 'var(--text-secondary)',
                }}
              >
                <div>
                  Page {page} of {totalPages} ({runsData.total} runs)
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={page <= 1 || isLoading}
                    onClick={() => fetchRuns(page - 1)}
                  >
                    <ChevronLeft size={14} /> Previous
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={page >= totalPages || isLoading}
                    onClick={() => fetchRuns(page + 1)}
                  >
                    Next <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};
