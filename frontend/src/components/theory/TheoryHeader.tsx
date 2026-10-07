import React from 'react';
import { BookOpen, ShieldAlert, Terminal } from 'lucide-react';

interface TheoryHeaderProps {
  activeMode: 'rare-region' | 'finite-domain';
  onSelectMode: (mode: 'rare-region' | 'finite-domain') => void;
}

export const TheoryHeader: React.FC<TheoryHeaderProps> = ({
  activeMode,
  onSelectMode,
}) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      {/* Title & Mode Switcher */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
            <span className="badge" style={{ backgroundColor: 'var(--cobalt-50)', color: 'var(--cobalt-700)', borderColor: 'var(--cobalt-200)' }}>
              MATHEMATICAL BENCHMARK
            </span>
            <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
              Sections 3, 21 & Proof Guarantees
            </span>
          </div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            Theory Lab: Idealized Bounds & Exact Adaptation
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', maxWidth: '850px' }}>
            Interactive mathematical laboratory proving theoretical sample complexities, statistical detection guarantees, and finite-domain adaptation bounds under idealized oracle assumptions.
          </p>
        </div>

        {/* Experiment Mode Toggle */}
        <div style={{ display: 'flex', backgroundColor: 'var(--bg-surface-subtle)', padding: '0.25rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
          <button
            className={`btn btn-sm ${activeMode === 'rare-region' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => onSelectMode('rare-region')}
            style={{
              border: activeMode === 'rare-region' ? 'none' : 'transparent',
              boxShadow: activeMode === 'rare-region' ? 'var(--shadow-sm)' : 'none',
            }}
          >
            <ShieldAlert size={14} /> T4 Rare-Region Detection
          </button>
          <button
            className={`btn btn-sm ${activeMode === 'finite-domain' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => onSelectMode('finite-domain')}
            style={{
              border: activeMode === 'finite-domain' ? 'none' : 'transparent',
              boxShadow: activeMode === 'finite-domain' ? 'var(--shadow-sm)' : 'none',
            }}
          >
            <Terminal size={14} /> T5 Finite-Domain Adaptation
          </button>
        </div>
      </div>

      {/* Distinction & Isolation Banner */}
      <div
        style={{
          padding: '0.875rem 1.125rem',
          backgroundColor: 'var(--cobalt-50)',
          border: '1px solid var(--cobalt-200)',
          borderRadius: 'var(--radius-sm)',
          fontSize: '0.8125rem',
          color: 'var(--cobalt-900)',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '0.75rem',
        }}
      >
        <BookOpen size={16} color="var(--cobalt-700)" style={{ flexShrink: 0, marginTop: '2px' }} />
        <div>
          <strong>Theoretical Isolation & Proof Guarantees:</strong> Theory Lab experiments test closed-form mathematical theorems (P_miss = (1 - qp)^D, D*(delta) = ceil(ln(1/delta) / -ln(1-qp)), and exact N-query lookup adaptation). These mathematical guarantees assume noiseless labels and zero false-alarm detectors, distinct from the practical heuristics of streaming ADWIN and empirical logistic classifiers.
        </div>
      </div>
    </div>
  );
};
