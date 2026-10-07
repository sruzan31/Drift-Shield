import { useEffect, useState } from 'react';
import { api } from './lib/api';
import type { HealthStatus } from './types';
import { Navbar } from './components/Navbar';
import { RunHistory } from './pages/RunHistory';
import { NewRun } from './pages/NewRun';
import { LiveRun } from './pages/LiveRun';
import { TheoryLab } from './pages/TheoryLab';
import './styles/theme.css';

export function App() {
  const [currentTab, setCurrentTab] = useState<'history' | 'new' | 'live' | 'theory'>('history');
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);

  // Poll health status every 10 seconds
  const checkHealth = async () => {
    try {
      const h = await api.getHealth();
      setHealth(h);
      if (h.active_run_id && !activeRunId) {
        setActiveRunId(h.active_run_id);
      }
    } catch {
      setHealth(null);
    }
  };

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleSelectRun = (runId: string) => {
    setActiveRunId(runId);
    setCurrentTab('live');
  };

  const handleRunCreated = (runId: string) => {
    setActiveRunId(runId);
    setCurrentTab('live');
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: 'var(--bg-app)' }}>
      <Navbar
        currentTab={currentTab}
        onSelectTab={setCurrentTab}
        activeRunId={activeRunId}
        health={health}
      />

      <main className="container" style={{ flex: 1, padding: '1.75rem 1.5rem 3rem 1.5rem' }}>
        {currentTab === 'history' && (
          <RunHistory
            onSelectRun={handleSelectRun}
            onNavigateNew={() => setCurrentTab('new')}
          />
        )}

        {currentTab === 'new' && (
          <NewRun
            onRunCreated={handleRunCreated}
            onCancel={() => setCurrentTab('history')}
          />
        )}

        {currentTab === 'live' && activeRunId && (
          <LiveRun
            runId={activeRunId}
            onNavigateBack={() => setCurrentTab('history')}
          />
        )}

        {currentTab === 'theory' && <TheoryLab />}
      </main>

      <footer
        style={{
          borderTop: '1px solid var(--border-subtle)',
          backgroundColor: 'var(--bg-surface)',
          padding: '1rem 0',
          fontSize: '0.75rem',
          color: 'var(--text-muted)',
          textAlign: 'center',
        }}
      >
        <div className="container">
          DriftShield Phase 6B • Streaming ML Monitoring, Finite Adaptation & Theory Lab Prototype
        </div>
      </footer>
    </div>
  );
}

export default App;
