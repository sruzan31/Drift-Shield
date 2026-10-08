// Harmless style comment for HMR stability check
import React from 'react';
import { Link } from 'react-router-dom';
import { Menu, Search, Bell } from 'lucide-react';

import type { HealthStatus } from '../types';
import type { NavigationTab } from './Sidebar';

interface HeaderProps {
  currentTab: NavigationTab;
  activeRunId: string | null;
  health: HealthStatus | null;
  onOpenSidebar: () => void;
  onNavigateNew?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  currentTab,
  activeRunId,
  health,
  onOpenSidebar,
}) => {
  const getBreadcrumbs = () => {
    switch (currentTab) {
      case 'overview':
        return ['Overview', activeRunId ? `Run ${activeRunId.slice(0, 12)}` : 'No active run'];
      case 'streams':
        return ['Streams', 'Runs & Datasets'];
      case 'new':
        return ['Streams', 'Connect a stream'];
      case 'live':
        return ['Live monitor', activeRunId ? `Run ${activeRunId.slice(0, 12)}` : 'No active stream'];
      case 'incidents':
        return ['Incidents', activeRunId ? `Run ${activeRunId.slice(0, 12)}` : 'All incidents'];
      case 'insights':
        return ['Insights', 'Stream risk & health'];
      case 'actions':
        return ['Actions', 'Review model promotion'];
      case 'reports':
        return ['Reports', 'Comparison exports'];
      case 'theory':
        return ['Theory Lab', 'Mathematical Verification'];
      default:
        return ['DriftShield'];
    }
  };

  const breadcrumbs = getBreadcrumbs();
  const isHealthy = health?.status === 'ok';

  return (
    <header className="app-header">
      {/* Public navigation */}
      <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginBottom: '0.5rem' }}>
        <Link to="/" style={{ color: 'var(--text-primary)', textDecoration: 'none', fontWeight: 500 }}>Product</Link>
        <Link to="/" style={{ color: 'var(--text-primary)', textDecoration: 'none', fontWeight: 500 }}>How it works</Link>
        <Link to="/pricing" style={{ color: 'var(--text-primary)', textDecoration: 'none', fontWeight: 500 }}>Pricing</Link>
        <Link to="/app" style={{ color: 'var(--text-primary)', textDecoration: 'none', fontWeight: 500 }}>Open workspace</Link>
      </div>
      {/* Left: Mobile Toggle & Breadcrumbs */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.875rem' }}>
        <button
          onClick={onOpenSidebar}
          style={{
            display: 'none',
            background: 'none',
            border: 'none',
            color: 'var(--text-secondary)',
            cursor: 'pointer',
            padding: '0.25rem',
          }}
          className="mobile-menu-btn"
          aria-label="Open navigation menu"
        >
          <Menu size={18} />
        </button>

        <nav aria-label="Breadcrumb" style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', fontSize: '0.8125rem' }}>
          <span style={{ color: 'var(--text-muted)', fontWeight: 500 }}>{breadcrumbs[0]}</span>
          <span style={{ color: 'var(--border-strong)' }}>›</span>
          <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{breadcrumbs[1]}</span>
          {activeRunId && health?.active_run_id === activeRunId && (
            <span className="badge badge-info" style={{ marginLeft: '0.375rem', fontSize: '0.625rem', fontFamily: 'var(--font-mono)' }}>
              LIVE
            </span>
          )}
        </nav>
      </div>

      {/* Right: Operational Status, Search, Alerts */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        {/* System Operational Status */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.4375rem',
            fontSize: '0.75rem',
            color: isHealthy ? 'var(--text-secondary)' : 'var(--danger-text)',
            fontWeight: 500,
          }}
        >
          <span
            style={{
              width: '7px',
              height: '7px',
              borderRadius: 'var(--radius-full)',
              backgroundColor: isHealthy ? 'var(--success-solid)' : 'var(--danger-solid)',
              boxShadow: isHealthy ? '0 0 0 2px var(--success-border)' : '0 0 0 2px var(--danger-border)',
            }}
          />
          <span className="hide-mobile">{isHealthy ? 'System operational' : 'Backend offline'}</span>
        </div>

        {/* Global Search Input */}
        <div
          style={{
            position: 'relative',
            display: 'flex',
            alignItems: 'center',
          }}
          className="hide-mobile"
        >
          <Search size={14} style={{ position: 'absolute', left: '0.625rem', color: 'var(--text-muted)' }} />
          <input
            type="text"
            placeholder="Search streams, incidents..."
            style={{
              padding: '0.375rem 2.25rem 0.375rem 2rem',
              fontSize: '0.75rem',
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
              outline: 'none',
              width: '210px',
              color: 'var(--text-primary)',
              transition: 'width 0.2s ease, border-color 0.2s ease',
            }}
            onFocus={(e) => (e.currentTarget.style.width = '260px')}
            onBlur={(e) => (e.currentTarget.style.width = '210px')}
          />
          <kbd
            style={{
              position: 'absolute',
              right: '0.5rem',
              fontSize: '0.625rem',
              padding: '0.1rem 0.25rem',
              background: 'var(--bg-surface-subtle)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '3px',
              color: 'var(--text-muted)',
              fontFamily: 'var(--font-mono)',
            }}
          >
            ⌘K
          </kbd>
        </div>

        {/* Notification Bell */}
        <button
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--text-muted)',
            cursor: 'pointer',
            padding: '0.375rem',
            borderRadius: 'var(--radius-sm)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
          aria-label="Notifications"
        >
          <Bell size={16} />
        </button>
      </div>
    </header>
  );
};
