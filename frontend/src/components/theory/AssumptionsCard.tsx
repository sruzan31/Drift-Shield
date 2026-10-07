import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Info } from 'lucide-react';

interface AssumptionsCardProps {
  mode: 'rare-region' | 'finite-domain';
}

export const AssumptionsCard: React.FC<AssumptionsCardProps> = ({ mode }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="card" style={{ padding: '0.875rem 1.25rem', backgroundColor: 'var(--bg-surface)' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          cursor: 'pointer',
        }}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>
          <Info size={15} color="var(--cobalt-600)" />
          {mode === 'rare-region' ? 'T4 Rare-Region Theorem Assumptions & Parameter Definitions' : 'T5 Finite-Domain Exact Adaptation Theorem Assumptions'}
        </div>
        <button
          type="button"
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
        >
          {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      </div>

      {isExpanded && (
        <div style={{ marginTop: '1rem', paddingTop: '0.875rem', borderTop: '1px solid var(--border-subtle)', fontSize: '0.8125rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {mode === 'rare-region' ? (
            <>
              <div>
                <strong>Mathematical Model:</strong>
                <ul style={{ paddingLeft: '1.25rem', marginTop: '0.25rem' }}>
                  <li><strong>Feature Distribution:</strong> Input stream X_t ~ Uniform[0, 1] independently drawn at each event step t.</li>
                  <li><strong>Reference Rule (f0):</strong> Known baseline classification rule f0(x) = 0 for all x.</li>
                  <li><strong>Drift Concept (f1):</strong> Post-drift target rule f1(x) = 1 if x &lt; p, else 0. The rare-region size p defines the mass of disagreement.</li>
                  <li><strong>Random Querying (q):</strong> Each arrival is independently sampled for an authoritative label with probability q.</li>
                  <li><strong>Zero False Alarm Detector:</strong> The detector alerts at the first disclosed disagreement (y_t != f0(x_t)). Because labels are noiseless, false alarms are zero.</li>
                </ul>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem', backgroundColor: 'var(--bg-surface-subtle)', padding: '0.75rem', borderRadius: 'var(--radius-sm)' }}>
                <div>
                  <strong>p (Disagreement Mass):</strong> Proportion of feature space where concept changed.
                </div>
                <div>
                  <strong>q (Query Rate):</strong> Labeling probability per arrival. Effective per-event detection rate is r = q * p.
                </div>
                <div>
                  <strong>D (Deadline):</strong> Fixed stream observation budget in events.
                </div>
                <div>
                  <strong>delta (Target Miss Probability):</strong> Desired confidence bound P_miss &le; delta.
                </div>
              </div>
            </>
          ) : (
            <>
              <div>
                <strong>Mathematical Model:</strong>
                <ul style={{ paddingLeft: '1.25rem', marginTop: '0.25rem' }}>
                  <li><strong>Domain (X):</strong> Known finite domain of N distinct inputs X = &#123;0, 1, ..., N-1&#125;.</li>
                  <li><strong>Reference Rule (f0):</strong> Known prior rule f0(x) = 0 for all x in X.</li>
                  <li><strong>Target Concept (f1):</strong> Fixed target rule f1: X &rarr; &#123;0, 1&#125; accessible only through point oracle queries.</li>
                  <li><strong>Audit Adaptation:</strong> Querying every domain input once into a lookup table achieves exact full-domain accuracy.</li>
                  <li><strong>Information Isolation:</strong> Until an input is explicitly queried, its true label is unresolved; no zero-risk assertion is made for unqueried inputs.</li>
                </ul>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};
