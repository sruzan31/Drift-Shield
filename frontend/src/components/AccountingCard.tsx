import React from 'react';
import { DollarSign } from 'lucide-react';
import type { LabelAccounting } from '../types';

interface AccountingCardProps {
  accounting: LabelAccounting;
  monitoringCoverage: number;
  labelBudget: number;
}

export const AccountingCard: React.FC<AccountingCardProps> = ({
  accounting,
  monitoringCoverage,
  labelBudget,
}) => {
  const budgetUsedPct = labelBudget > 0 ? (accounting.budget_debits / labelBudget) * 100 : 0;

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">
          <DollarSign size={16} color="var(--cobalt-600)" />
          Label Acquisitions & Budget Accounting
        </span>
        <span className="badge badge-neutral" style={{ fontSize: '0.6875rem' }}>
          Physical Counts
        </span>
      </div>

      <div className="grid-2">
        {/* Budget Debits Progress */}
        <div
          style={{
            padding: '1rem',
            backgroundColor: 'var(--bg-surface-subtle)',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', fontSize: '0.8125rem' }}>
            <span style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>Post-Warmup Budget Debits:</span>
            <span style={{ fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
              {accounting.budget_debits} / {labelBudget} ({budgetUsedPct.toFixed(1)}%)
            </span>
          </div>

          <div
            style={{
              width: '100%',
              height: '8px',
              backgroundColor: 'var(--border-subtle)',
              borderRadius: '4px',
              overflow: 'hidden',
              marginBottom: '1rem',
            }}
          >
            <div
              style={{
                width: `${Math.min(100, budgetUsedPct)}%`,
                height: '100%',
                backgroundColor: budgetUsedPct >= 100 ? 'var(--danger-solid)' : 'var(--cobalt-600)',
                transition: 'width 0.3s ease',
              }}
            />
          </div>

          <div className="kv-list">
            <div className="kv-row">
              <span className="kv-key">Monitoring Channel Acquisitions:</span>
              <span className="kv-val">{accounting.monitor_acquisitions}</span>
            </div>
            <div className="kv-row">
              <span className="kv-key">Selective (Low-Margin) Acquisitions:</span>
              <span className="kv-val">{accounting.selective_acquisitions}</span>
            </div>
            <div className="kv-row">
              <span className="kv-key">Total Unique Acquired Labels:</span>
              <span className="kv-val">{accounting.total_unique_acquisitions}</span>
            </div>
          </div>
        </div>

        {/* Monitoring Coverage & Warmup */}
        <div
          style={{
            padding: '1rem',
            backgroundColor: 'var(--bg-surface-subtle)',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          <div style={{ marginBottom: '0.75rem' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Monitoring Coverage (Post-Warmup)</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--cobalt-700)' }}>
              {(monitoringCoverage * 100).toFixed(2)}%
            </div>
          </div>

          <div className="kv-list">
            <div className="kv-row">
              <span className="kv-key">Warmup Labels (Initial Fit):</span>
              <span className="kv-val">{accounting.warmup_acquisitions} (Cost: 0)</span>
            </div>
            <div className="kv-row">
              <span className="kv-key">Post-Warmup Unique Labels:</span>
              <span className="kv-val">{accounting.post_warmup_acquisitions}</span>
            </div>
            <div className="kv-row">
              <span className="kv-key">Channel Overlap Deduplication:</span>
              <span className="kv-val" style={{ color: 'var(--success-text)' }}>Exact 1:1 Debit</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
