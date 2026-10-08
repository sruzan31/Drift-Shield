import { useEffect, useState } from 'react';
import { api } from './lib/api';
import type { HealthStatus } from './types';
import { Sidebar } from './components/Sidebar';
import type { NavigationTab } from './components/Sidebar';
import { Header } from './components/Header';
import { Overview } from './pages/Overview';
import { RunHistory } from './pages/RunHistory';
import { NewRun } from './pages/NewRun';
import { LiveRun } from './pages/LiveRun';
import { Incidents } from './pages/Incidents';
import { Insights } from './pages/Insights';
import { Actions } from './pages/Actions';
import { Reports } from './pages/Reports';
import { TheoryLab } from './pages/TheoryLab';
import './styles/theme.css';

export function App() {
  const [currentTab, setCurrentTab] = useState<NavigationTab>('overview');
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(false);

  // Poll health status and initial run selection
  const checkHealth = async () => {
    try {
      const h = await api.getHealth();
      setHealth(h);
      if (h.active_run_id) {
        setActiveRunId(h.active_run_id);
      } else {
        setActiveRunId(null);
      }
    } catch {
      setHealth(null);
    }
  };

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 10000);

    // Initial load of latest run for selectedRunId
    const initSelectedRun = async () => {
      try {
        const runs = await api.getRuns(1, 1);
        if (runs.items.length > 0) {
          setSelectedRunId((prev) => prev || runs.items[0].run_id);
        }
      } catch (err) {
        console.warn('Could not fetch initial runs:', err);
      }
    };
    initSelectedRun();

    return () => clearInterval(interval);
  }, []);

  const handleSelectRun = (runId: string) => {
    setSelectedRunId(runId);
    setCurrentTab('live');
  };

  const handleRunCreated = (runId: string) => {
    setSelectedRunId(runId);
    setActiveRunId(runId);
    setCurrentTab('live');
  };

  const effectiveRunId = activeRunId || selectedRunId;

  return (
    <div className="app-shell">
      {/* Shared Left Sidebar */}
      <Sidebar
        currentTab={currentTab}
        onSelectTab={setCurrentTab}
        activeRunId={effectiveRunId}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      {/* Main Content Area */}
      <div className="app-main-wrapper">
        <Header
          currentTab={currentTab}
          activeRunId={effectiveRunId}
          health={health}
          onOpenSidebar={() => setSidebarOpen(true)}
          onNavigateNew={() => setCurrentTab('new')}
        />

        <main className="app-content">
          {currentTab === 'overview' && (
            <Overview
              activeRunId={effectiveRunId}
              onNavigateNew={() => setCurrentTab('new')}
              onNavigateLive={handleSelectRun}
              onNavigateIncidents={(id) => {
                if (id) setSelectedRunId(id);
                setCurrentTab('incidents');
              }}
              onNavigateActions={(id) => {
                if (id) setSelectedRunId(id);
                setCurrentTab('actions');
              }}
            />
          )}

          {currentTab === 'streams' && (
            <RunHistory
              onSelectRun={handleSelectRun}
              onNavigateNew={() => setCurrentTab('new')}
            />
          )}

          {currentTab === 'new' && (
            <NewRun
              onRunCreated={handleRunCreated}
              onCancel={() => setCurrentTab('streams')}
            />
          )}

          {currentTab === 'live' && (
            <LiveRun
              runId={effectiveRunId || ''}
              onNavigateBack={() => setCurrentTab('streams')}
              onNavigateIncidents={() => setCurrentTab('incidents')}
              onNavigateActions={() => setCurrentTab('actions')}
            />
          )}

          {currentTab === 'incidents' && (
            <Incidents
              runId={effectiveRunId}
              onNavigateActions={() => setCurrentTab('actions')}
            />
          )}

          {currentTab === 'insights' && (
            <Insights
              runId={effectiveRunId}
              onNavigateActions={() => setCurrentTab('actions')}
            />
          )}

          {currentTab === 'actions' && (
            <Actions
              runId={effectiveRunId}
            />
          )}

          {currentTab === 'reports' && (
            <Reports
              onSelectRun={handleSelectRun}
              onNavigateNew={() => setCurrentTab('new')}
            />
          )}

          {currentTab === 'theory' && <TheoryLab />}
        </main>
      </div>
    </div>
  );
}

export default App;
