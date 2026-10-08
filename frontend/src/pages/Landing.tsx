import React, { useEffect, useRef } from 'react';
import { pricingPlans } from '../lib/pricingData';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  Activity,
  CheckCircle2,
  BookOpen,
  Shield,
} from 'lucide-react';

// Public‑only header – lightweight, no workspace breadcrumbs
const PublicHeader: React.FC = () => {
  return (
    <header
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '1rem 2rem',
        borderBottom: '1px solid var(--border-strong)',
        backgroundColor: 'var(--bg-surface)',
      }}
    >
      <div style={{ fontWeight: 800, fontSize: '1.25rem', color: 'var(--text-primary)' }}>
        DriftShield
      </div>
      <nav style={{ display: 'flex', gap: '1.5rem' }}>
        <Link to="/" style={{ color: 'var(--text-primary)', textDecoration: 'none' }}>
          Product
        </Link>
        <Link to="/" style={{ color: 'var(--text-primary)', textDecoration: 'none' }}>
          How it works
        </Link>
        <Link to="/pricing" style={{ color: 'var(--text-primary)', textDecoration: 'none' }}>
          Pricing
        </Link>
        <Link to="/app" style={{ color: 'var(--text-primary)', textDecoration: 'none' }}>
          Open workspace
        </Link>
      </nav>
    </header>
  );
};

// Helper hook for reduced‑motion support
const usePrefersReducedMotion = () => {
  const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  return mediaQuery.matches;
};

export const Landing: React.FC = () => {
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const prefersReduced = usePrefersReducedMotion();

  useEffect(() => {
    if (prefersReduced) return;
    const el = containerRef.current;
    if (!el) return;
    const children = Array.from(el.querySelectorAll<HTMLElement>('.reveal'));
    children.forEach((child, i) => {
      child.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
      child.style.opacity = '0';
      child.style.transform = 'translateY(20px)';
      setTimeout(() => {
        child.style.opacity = '1';
        child.style.transform = 'translateY(0)';
      }, i * 120);
    });
  }, [prefersReduced]);

  return (
    <div ref={containerRef} style={{ backgroundColor: 'var(--bg-surface-subtle)', minHeight: '100vh' }}>
      <PublicHeader />

      {/* Central wrapper */}
      <main
        style={{
          maxWidth: '1200px',
          margin: '0 auto',
          padding: '2rem 1.5rem',
          display: 'flex',
          flexDirection: 'column',
          gap: '4rem',
        }}
      >
        {/* Hero Section */}
        <section className="reveal" style={{ display: 'flex', flexWrap: 'wrap', gap: '2rem' }}>
          <div style={{ flex: '1 1 300px' }}>
            <h1
              style={{
                fontSize: '2.5rem',
                fontWeight: 800,
                color: 'var(--text-primary)',
                lineHeight: 1.2,
                marginBottom: '1rem',
              }}
            >
              Monitor model performance. Evaluate replacements.
            </h1>
            <p style={{ fontSize: '1.0625rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              Track prediction errors, detect concept drift, and compare candidate models before switching.
            </p>
            <div style={{ marginTop: '1.5rem', display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
              <button
                className="btn btn-primary"
                onClick={() => navigate('/app')}
                style={{ padding: '0.6rem 1.2rem', fontWeight: 600, fontSize: '0.875rem' }}
              >
                Explore DriftShield <ArrowRight size={15} />
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => navigate('/')}
                style={{ padding: '0.6rem 1.2rem', fontWeight: 600, fontSize: '0.875rem' }}
              >
                How it works
              </button>
            </div>
          </div>
          {/* Right‑hand illustrative workflow */}
          <div
            className="card"
            style={{
              flex: '1 1 300px',
              padding: '1rem',
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-strong)',
              borderRadius: 'var(--radius-sm)',
              boxShadow: 'var(--shadow-md)',
            }}
          >
            <h2 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '0.75rem', color: 'var(--text-primary)' }}>
              Illustrative workflow
            </h2>
            <ol style={{ listStyle: 'decimal inside', paddingLeft: 0, margin: 0, color: 'var(--text-secondary)' }}>
              <li style={{ marginBottom: '0.5rem' }}>Monitoring live predictions</li>
              <li style={{ marginBottom: '0.5rem' }}>Candidate training on new data</li>
              <li style={{ marginBottom: '0.5rem' }}>Evaluation of candidate vs current model</li>
              <li>Decision and model promotion</li>
            </ol>
          </div>
        </section>

        {/* Evidence before model replacement (workflow steps) */}
        <section className="reveal" style={{}}>
          <h2 style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '1.5rem' }}>
            Evidence before model replacement
          </h2>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
              gap: '1.5rem',
            }}
          >
            <div className="card" style={{ padding: '1rem', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-xs)', backgroundColor: 'var(--bg-surface)' }}>
              <Activity size={24} color="var(--cobalt-600)" />
              <h3 style={{ fontSize: '1rem', marginTop: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                Configure a run
              </h3>
              <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                Define data streams, thresholds and monitoring windows.
              </p>
            </div>
            <div className="card" style={{ padding: '1rem', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-xs)', backgroundColor: 'var(--bg-surface)' }}>
              <Shield size={24} color="var(--cobalt-600)" />
              <h3 style={{ fontSize: '1rem', marginTop: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                Monitor errors
              </h3>
              <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                Continuously watch prediction error rates and drift signals.
              </p>
            </div>
            <div className="card" style={{ padding: '1rem', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-xs)', backgroundColor: 'var(--bg-surface)' }}>
              <CheckCircle2 size={24} color="var(--teal-600)" />
              <h3 style={{ fontSize: '1rem', marginTop: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                Evaluate a candidate
              </h3>
              <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                Train a new model on recent data and compare performance.
              </p>
            </div>
            <div className="card" style={{ padding: '1rem', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-xs)', backgroundColor: 'var(--bg-surface)' }}>
              <BookOpen size={24} color="var(--cobalt-600)" />
              <h3 style={{ fontSize: '1rem', marginTop: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                Review the decision
              </h3>
              <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                Inspect logs, charts and trigger model promotion.
              </p>
            </div>
          </div>
        </section>

        {/* Feature highlights */}
        <section className="reveal" style={{}}>
          <h2 style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '1.5rem' }}>
            Why DriftShield?
          </h2>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
              gap: '1.5rem',
            }}
          >
            <div className="card" style={{ padding: '1rem', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-xs)', backgroundColor: 'var(--bg-surface)' }}>
              <Activity size={20} color="var(--cobalt-600)" />
              <h3 style={{ fontSize: '1rem', marginTop: '0.5rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                Live monitoring
              </h3>
              <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                Stream predictions in real‑time and see drift signals instantly.
              </p>
            </div>
            <div className="card" style={{ padding: '1rem', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-xs)', backgroundColor: 'var(--bg-surface)' }}>
              <CheckCircle2 size={20} color="var(--teal-600)" />
              <h3 style={{ fontSize: '1rem', marginTop: '0.5rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                Traceable decisions
              </h3>
              <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                All model promotions are logged with full audit trail.
              </p>
            </div>
            <div className="card" style={{ padding: '1rem', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-xs)', backgroundColor: 'var(--bg-surface)' }}>
              <BookOpen size={20} color="var(--cobalt-600)" />
              <h3 style={{ fontSize: '1rem', marginTop: '0.5rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                Theory Lab
              </h3>
              <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                Explore drift concepts, metrics and experimental controls.
              </p>
            </div>
          </div>
        </section>

        {/* Pricing Section */}
        <section id="pricing" className="reveal" style={{ textAlign: 'center' }}>
          <h2 style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>Start locally. Grow with your team.</h2>
          <p style={{ fontSize: '1.125rem', color: 'var(--text-secondary)', marginBottom: '2rem' }}>Choose an option for your model‑monitoring workflow.</p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1.5rem', justifyItems: 'center' }}>
            {pricingPlans.map(plan => (
              <div key={plan.id} className="card" style={{ padding: '1rem', border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-sm)', backgroundColor: 'var(--bg-surface)', width: '100%', maxWidth: '300px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>{plan.title}</h2>
                <p style={{ fontSize: '1rem', color: 'var(--text-primary)', fontWeight: 600, marginBottom: '0.25rem' }}>{plan.price}</p>
                {plan.badge && (
                  <span className="badge badge-info" style={{ fontSize: '0.75rem', marginBottom: '0.5rem', display: 'inline-block' }}>{plan.badge}</span>
                )}
                <p style={{ fontSize: '1rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>{plan.description}</p>
                <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>{plan.note}</p>
                {plan.buttonLabel && plan.buttonLink ? (
                  <Link to={plan.buttonLink} className="btn btn-primary" style={{ marginTop: '0.75rem', alignSelf: 'flex-start' }}>{plan.buttonLabel}</Link>
                ) : (
                  <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '0.75rem' }}>Contact details coming soon</p>
                )}
              </div>
            ))}
          </div>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '2rem' }}><em>Paid plans are proposed. Pricing and included services will be finalized before launch. No payment is collected through this website.</em></p>
        </section>

        {/* Final Call to Action */}
        <section className="reveal" style={{ textAlign: 'center' }}>
          <h2 style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--text-primary)', marginBottom: '1rem' }}>
            Explore DriftShield
          </h2>
          <button
            className="btn btn-primary"
            onClick={() => navigate('/app')}
            style={{ padding: '0.75rem 1.5rem', fontWeight: 600, fontSize: '1rem' }}
          >
            Open workspace <ArrowRight size={16} />
          </button>
        </section>
      </main>
    </div>
  );
};
