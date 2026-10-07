import React, { useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  ExternalLink,
  History,
  RefreshCw,
} from 'lucide-react';
import { api } from '../lib/api';
import { StatusBadge } from '../components/StatusBadge';
import { AssumptionsCard } from '../components/theory/AssumptionsCard';
import { FiniteDomainTab } from '../components/theory/FiniteDomainTab';
import { RareRegionTab } from '../components/theory/RareRegionTab';
import { TheoryHeader } from '../components/theory/TheoryHeader';
import type {
  CreateFiniteDomainRequest,
  CreateRareRegionRequest,
  TheoryExperimentDetail,
  TheoryExperimentSummary,
} from '../types';

export const TheoryLab: React.FC = () => {
  const [activeMode, setActiveMode] = useState<'rare-region' | 'finite-domain'>('rare-region');
  const [currentExperiment, setCurrentExperiment] = useState<TheoryExperimentDetail | null>(null);
  const [recentExperiments, setRecentExperiments] = useState<TheoryExperimentSummary[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(false);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const pollTimerRef = useRef<any>(null);

  // 1. Fetch recent experiments history
  const loadRecentHistory = async () => {
    setIsLoadingHistory(true);
    try {
      const data = await api.getTheoryExperiments(10, 0);
      setRecentExperiments(data.items || []);
    } catch (err: any) {
      console.error('[TheoryLab] Failed to load history:', err);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  useEffect(() => {
    loadRecentHistory();
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, []);

  // 2. Poll active experiment until completion
  const startPollingExperiment = (expId: string) => {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    setIsRunning(true);

    pollTimerRef.current = setInterval(async () => {
      try {
        const detail: TheoryExperimentDetail = await api.getTheoryExperiment(expId);
        setCurrentExperiment(detail);

        if (detail.status === 'COMPLETED' || detail.status === 'FAILED' || detail.status === 'INTERRUPTED') {
          clearInterval(pollTimerRef.current);
          pollTimerRef.current = null;
          setIsRunning(false);
          loadRecentHistory();
        }
      } catch (err: any) {
        console.error('[TheoryLab] Polling error:', err);
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
        setIsRunning(false);
      }
    }, 800);
  };

  // 3. Launch an experiment
  const handleLaunchExperiment = async (payload: CreateRareRegionRequest | CreateFiniteDomainRequest) => {
    setError(null);
    setIsRunning(true);
    try {
      const summary = await api.createTheoryExperiment(payload);
      setCurrentExperiment({ ...summary, results: null });
      startPollingExperiment(summary.experiment_id);
    } catch (err: any) {
      setError(err?.message || 'Failed to launch theory experiment');
      setIsRunning(false);
    }
  };

  // 4. Select and open a historical experiment
  const handleSelectExperiment = async (expId: string) => {
    setError(null);
    try {
      const detail: TheoryExperimentDetail = await api.getTheoryExperiment(expId);
      setCurrentExperiment(detail);
      setActiveMode(detail.mode as any);
      if (detail.status === 'QUEUED' || detail.status === 'RUNNING') {
        startPollingExperiment(detail.experiment_id);
      }
    } catch (err: any) {
      setError(err?.message || `Failed to load theory experiment '${expId}'`);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Header & Guarantees Banner */}
      <TheoryHeader
        activeMode={activeMode}
        onSelectMode={(mode) => {
          setActiveMode(mode);
          setError(null);
        }}
      />

      {/* Assumptions & Model Definitions */}
      <AssumptionsCard mode={activeMode} />

      {/* Error Alert */}
      {error && (
        <div
          style={{
            padding: '1rem',
            backgroundColor: 'var(--danger-bg)',
            color: 'var(--danger-text)',
            border: '1px solid var(--danger-border)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.875rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* Active Tab View */}
      {activeMode === 'rare-region' ? (
        <RareRegionTab
          experiment={currentExperiment?.mode === 'rare-region' ? currentExperiment : null}
          isRunning={isRunning}
          onLaunchExperiment={handleLaunchExperiment}
        />
      ) : (
        <FiniteDomainTab
          experiment={currentExperiment?.mode === 'finite-domain' ? currentExperiment : null}
          isRunning={isRunning}
          onLaunchExperiment={handleLaunchExperiment}
        />
      )}

      {/* Recent Theory Experiments History Table */}
      <div className="card" style={{ padding: '1.25rem', marginTop: '0.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
          <div style={{ fontWeight: 600, fontSize: '0.9375rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <History size={16} color="var(--cobalt-600)" />
            Recent Theory Lab Experiments
          </div>
          <button
            className="btn btn-secondary btn-sm"
            onClick={loadRecentHistory}
            disabled={isLoadingHistory}
          >
            <RefreshCw size={13} className={isLoadingHistory ? 'spin' : ''} /> Refresh History
          </button>
        </div>

        {recentExperiments.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            No Theory Lab experiments recorded yet. Configure parameters above and run an experiment.
          </div>
        ) : (
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Experiment ID</th>
                  <th>Mode</th>
                  <th>Seed</th>
                  <th>State</th>
                  <th>Parameters</th>
                  <th>Completed</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {recentExperiments.map((exp) => (
                  <tr key={exp.experiment_id}>
                    <td>
                      <code>{exp.experiment_id}</code>
                    </td>
                    <td>
                      <span className="badge" style={{ textTransform: 'uppercase' }}>
                        {exp.mode}
                      </span>
                    </td>
                    <td>{exp.seed}</td>
                    <td>
                      <StatusBadge status={exp.status} />
                    </td>
                    <td style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                      {exp.mode === 'rare-region'
                        ? `p=${exp.config.p}, q=${exp.config.q}, D=${exp.config.deadline}, trials=${exp.config.trials}`
                        : `N=${exp.config.n_domain}, scenario=${exp.config.scenario}`}
                    </td>
                    <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      {exp.completed_at
                        ? new Date(exp.completed_at * 1000).toLocaleTimeString()
                        : '—'}
                    </td>
                    <td>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleSelectExperiment(exp.experiment_id)}
                      >
                        <ExternalLink size={12} /> View Results
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
