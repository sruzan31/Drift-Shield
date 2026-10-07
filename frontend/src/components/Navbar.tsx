import React from 'react';
import { Activity, Database, PlusCircle, Server } from 'lucide-react';
import type { HealthStatus } from '../types';

interface NavbarProps {
  currentTab: 'history' | 'new' | 'live' | 'theory';
  onSelectTab: (tab: 'history' | 'new' | 'live' | 'theory') => void;
  activeRunId: string | null;
  health: HealthStatus | null;
}

export const Navbar: React.FC<NavbarProps> = ({
  currentTab,
  onSelectTab,
  activeRunId,
  health,
}) => {
  return (
    <header
      style={{
        backgroundColor: 'var(--bg-surface)',
        borderBottom: '1px solid var(--border-subtle)',
        position: 'sticky',
        top: 0,
        zIndex: 40,
        boxShadow: 'var(--shadow-sm)',
      }}
    >
      <div
        className="container"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '0.75rem',
          paddingTop: '0.5rem',
          paddingBottom: '0.5rem',
          minHeight: '60px',
        }}
      >
        {/* Brand & Tabs */}
        <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
            <div
              style={{
                width: '32px',
                height: '32px',
                backgroundColor: 'var(--cobalt-600)',
                color: 'var(--text-inverse)',
                borderRadius: 'var(--radius-sm)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 700,
                fontSize: '1.125rem',
                flexShrink: 0,
              }}
            >
              D
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: '1rem', letterSpacing: '-0.01em', color: 'var(--text-primary)' }}>
                DriftShield
              </div>
              <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', lineHeight: 1 }}>
                ML Monitoring & Adaptation
              </div>
            </div>
          </div>

          {/* Navigation Links */}
          <nav style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '0.375rem' }}>
            <button
              className={`btn btn-sm ${currentTab === 'history' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => onSelectTab('history')}
              style={{ border: currentTab === 'history' ? 'none' : undefined }}
            >
              <Database size={14} />
              Run History
            </button>
            <button
              className={`btn btn-sm ${currentTab === 'new' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => onSelectTab('new')}
              style={{ border: currentTab === 'new' ? 'none' : undefined }}
            >
              <PlusCircle size={14} />
              New Run
            </button>
            <button
              className={`btn btn-sm ${currentTab === 'live' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => onSelectTab('live')}
              disabled={!activeRunId}
              style={{
                border: currentTab === 'live' ? 'none' : undefined,
                opacity: !activeRunId ? 0.5 : 1,
              }}
            >
              <Activity size={14} />
              Live Run
            </button>
            <button
              className={`btn btn-sm ${currentTab === 'theory' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => onSelectTab('theory')}
              style={{ border: currentTab === 'theory' ? 'none' : undefined }}
            >
              <Activity size={14} />
              Theory Lab
            </button>
          </nav>
        </div>

        {/* Health Probe Indicator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '0.75rem' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.375rem',
              padding: '0.25rem 0.625rem',
              backgroundColor: health?.status === 'ok' ? 'var(--success-bg)' : 'var(--danger-bg)',
              color: health?.status === 'ok' ? 'var(--success-text)' : 'var(--danger-text)',
              border: `1px solid ${health?.status === 'ok' ? 'var(--success-border)' : 'var(--danger-border)'}`,
              borderRadius: 'var(--radius-sm)',
              fontWeight: 500,
            }}
          >
            <Server size={12} />
            <span>
              {health?.status === 'ok'
                ? 'Backend Ready'
                : 'Backend Unavailable'}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
};
