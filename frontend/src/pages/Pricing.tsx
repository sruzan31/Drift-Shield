import React from 'react';
import { Link } from 'react-router-dom';

export const Pricing: React.FC = () => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem', padding: '2rem' }}>
      <h1 style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--text-primary)' }}>Pricing</h1>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem' }}>
        {/* Starter */}
        <div className="card" style={{ padding: '1rem', border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-sm)', backgroundColor: 'var(--bg-surface)' }}>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>Starter</h2>
          <p style={{ fontSize: '1rem', color: 'var(--text-secondary)' }}>Free, local use with your own computing resources.</p>
          <button className="btn btn-primary" style={{ marginTop: '0.5rem' }}>Get Started</button>
        </div>
        {/* Team Pilot */}
        <div className="card" style={{ padding: '1rem', border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-sm)', backgroundColor: 'var(--bg-surface)' }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>Team Pilot</h2>
            <p style={{ fontSize: '1rem', color: 'var(--text-primary)', fontWeight: 600, marginBottom: '0.25rem' }}>₹999/month</p>
            <span className="badge badge-info" style={{ fontSize: '0.75rem', marginBottom: '0.5rem', display: 'inline-block' }}>Planned — proposed launch price</span>
            <p style={{ fontSize: '1rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>For small teams evaluating model-performance monitoring.</p>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>This plan is not yet available for purchase.</p>
          </div>
        {/* Enterprise */}
        <div className="card" style={{ padding: '1rem', border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-sm)', backgroundColor: 'var(--bg-surface)' }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>Enterprise</h2>
            <p style={{ fontSize: '1rem', color: 'var(--text-primary)', fontWeight: 600, marginBottom: '0.25rem' }}>Starting at ₹4,999/month</p>
            <span className="badge badge-info" style={{ fontSize: '0.75rem', marginBottom: '0.5rem', display: 'inline-block' }}>Planned — proposed launch price</span>
            <p style={{ fontSize: '1rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>For organizations seeking deployment, integration, and support tailored to their requirements.</p>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>Final pricing depends on usage, hosting, and support requirements. This plan is not yet available for purchase.</p>
          </div>
      </div>
      <div style={{ marginTop: '1rem' }}>
        <Link to="/" className="btn btn-primary">Back to Home</Link>
      </div>
    </div>
  );
};
