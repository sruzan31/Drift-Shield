import React from 'react';
import {
  LayoutGrid,
  Activity,
  LineChart,
  AlertTriangle,
  BarChart2,
  Play,
  FileText,
  FlaskConical,
  Shield,
  X,
} from 'lucide-react';

export type NavigationTab =
  | 'overview'
  | 'streams'
  | 'live'
  | 'incidents'
  | 'insights'
  | 'actions'
  | 'reports'
  | 'theory'
  | 'new';

interface SidebarProps {
  currentTab: NavigationTab;
  onSelectTab: (tab: NavigationTab) => void;
  activeRunId: string | null;
  isOpen: boolean;
  onClose: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentTab,
  onSelectTab,
  activeRunId,
  isOpen,
  onClose,
}) => {
  const navItems = [
    { id: 'overview' as NavigationTab, label: 'Overview', icon: LayoutGrid },
    { id: 'streams' as NavigationTab, label: 'Streams', icon: Activity },
    { id: 'live' as NavigationTab, label: 'Live monitor', icon: LineChart, badge: activeRunId ? 'Active' : undefined },
    { id: 'incidents' as NavigationTab, label: 'Incidents', icon: AlertTriangle },
    { id: 'insights' as NavigationTab, label: 'Insights', icon: BarChart2 },
    { id: 'actions' as NavigationTab, label: 'Actions', icon: Play },
    { id: 'reports' as NavigationTab, label: 'Reports', icon: FileText },
    { id: 'theory' as NavigationTab, label: 'Theory Lab', icon: FlaskConical },
  ];

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          onClick={onClose}
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.4)',
            zIndex: 45,
            backdropFilter: 'blur(2px)',
          }}
        />
      )}

      <aside className={`app-sidebar ${isOpen ? 'open' : ''}`}>
        {/* Brand Header */}
        <div
          style={{
            padding: '1.125rem 1.25rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid var(--border-subtle)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
            <div
              style={{
                width: '30px',
                height: '30px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: 'var(--cobalt-50)',
                color: 'var(--cobalt-600)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Shield size={18} fill="currentColor" strokeWidth={1.5} />
            </div>
            <span
              style={{
                fontSize: '1.0625rem',
                fontWeight: 700,
                color: 'var(--text-primary)',
                letterSpacing: '-0.02em',
              }}
            >
              DriftShield
            </span>
          </div>

          <button
            onClick={onClose}
            className="mobile-close-btn"
            style={{
              display: isOpen ? 'flex' : 'none',
              background: 'none',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              padding: '0.25rem',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Navigation List */}
        <nav style={{ flex: 1, padding: '0.5rem 0.75rem', display: 'flex', flexDirection: 'column', gap: '0.1875rem' }}>
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive =
              currentTab === item.id || (item.id === 'streams' && currentTab === 'new');
            return (
              <button
                key={item.id}
                className={`sidebar-nav-item ${isActive ? 'active' : ''}`}
                onClick={() => {
                  onSelectTab(item.id);
                  onClose();
                }}
              >
                <Icon size={16} strokeWidth={isActive ? 2.2 : 1.75} />
                <span style={{ flex: 1 }}>{item.label}</span>
                {item.badge && (
                  <span
                    className="badge badge-info"
                    style={{ fontSize: '0.625rem', padding: '0.1rem 0.375rem' }}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Footer: Workspace Context */}
        <div
          style={{
            padding: '0.875rem 1rem',
            borderTop: '1px solid var(--border-subtle)',
            backgroundColor: 'var(--bg-surface)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
            <div
              style={{
                width: '28px',
                height: '28px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: 'var(--cobalt-50)',
                color: 'var(--cobalt-600)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '0.75rem',
                fontWeight: 700,
              }}
            >
              DS
            </div>
            <div>
              <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.2 }}>
                DriftShield
              </div>
              <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                Local Engine
              </div>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
};
