import React, { useState, useEffect } from 'react';
import {
  ArrowRight,
  AlertTriangle,
  CheckCircle2,
} from 'lucide-react';
import { api } from '../lib/api';
import type { IncidentItem, RunDetail } from '../types';

interface IncidentsProps {
  runId?: string | null;
  onNavigateActions?: (runId?: string) => void;
}

export const Incidents: React.FC<IncidentsProps> = ({ runId, onNavigateActions }) => {
  const [activeTab, setActiveTab] = useState<'summary' | 'analysis' | 'evidence' | 'actions'>('analysis');
  const [incident, setIncident] = useState<IncidentItem | null>(null);
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    const loadIncident = async () => {
      setLoading(true);
      let targetRun = runId;
      if (!targetRun) {
        const runsRes = await api.getRuns(1, 1);
        if (runsRes.items.length > 0) {
          targetRun = runsRes.items[0].run_id;
        }
      }
      if (targetRun) {
        try {
          const detail = await api.getRunDetail(targetRun);
          if (isMounted) setRunDetail(detail);

          const incRes = await api.getIncidents(targetRun, 1, 1);
          if (incRes.items.length > 0 && isMounted) {
            setIncident(incRes.items[0]);
          } else if (isMounted) {
            setIncident(null);
          }
        } catch (err) {
          console.error('Failed to load incident detail:', err);
        } finally {
          if (isMounted) setLoading(false);
        }
      } else {
        if (isMounted) setLoading(false);
      }
    };
    loadIncident();
    return () => {
      isMounted = false;
    };
  }, [runId]);

  const activeVersion = runDetail?.active_model_version || 'v1.0-frozen';
  const candidateVersion = runDetail?.candidate_summary?.candidates?.[0]?.target_version || 'v2.0';
  const detectionDelay = incident?.detection_delay ?? (incident?.evidence?.detection_delay ?? null);
  
  const fullSyntheticError = runDetail?.metrics?.full_synthetic;
  const monitorChannelError = runDetail?.metrics?.monitor_channel;
  const currentError = fullSyntheticError?.error_rate ?? monitorChannelError?.error_rate;
  const errorRateStr = currentError != null ? `${(currentError * 100).toFixed(1)}%` : 'Not available';

  const pairedSession = runDetail?.paired_summary?.sessions?.[0] || incident?.evidence?.paired_summary;
  const gainStr = pairedSession?.gain != null ? `+${(pairedSession.gain * 100).toFixed(1)} pp` : 'Awaiting eval';
  const bCount = pairedSession?.b ?? incident?.evidence?.b ?? 0;
  const cCount = pairedSession?.c ?? incident?.evidence?.c ?? 0;

  if (loading) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
        Loading incident records...
      </div>
    );
  }

  if (!incident && !runDetail) {
    return (
      <div className="card" style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
        <AlertTriangle size={32} style={{ marginBottom: '1rem', color: 'var(--text-muted)' }} />
        <div style={{ fontSize: '1.125rem', fontWeight: 600, color: 'var(--text-primary)' }}>No Incidents Found</div>
        <div style={{ fontSize: '0.8125rem', marginTop: '0.25rem' }}>
          Select or start a stream run to view incident investigations.
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
            <h1 style={{ fontSize: '1.625rem', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
              {activeTab === 'evidence'
                ? 'Why was this alert raised?'
                : `${incident?.incident_id || 'Alert'} • Concept Drift Investigation`}
            </h1>
            <span className={`badge ${incident ? 'badge-danger' : 'badge-success'}`} style={{ fontSize: '0.6875rem' }}>
              {incident ? `● Triggered at Seq #${incident.event_sequence}` : 'Nominal · Clean Stream'}
            </span>
          </div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginTop: '0.125rem' }}>
            Scenario: {runDetail?.scenario || 'abrupt'} · <span style={{ fontFamily: 'var(--font-mono)' }}>{runDetail?.run_id || runId}</span>
            {detectionDelay != null && ` · Detection delay: ${detectionDelay} events`}
          </div>
        </div>

        {/* Top Mini Key Stats Bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', backgroundColor: 'var(--bg-surface)', padding: '0.5rem 1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', fontSize: '0.75rem' }}>
          <div>
            <div style={{ fontSize: '0.625rem', color: 'var(--text-muted)' }}>Active model</div>
            <div style={{ fontWeight: 700, color: 'var(--cobalt-600)' }}>{activeVersion}</div>
          </div>
          <div>
            <div style={{ fontSize: '0.625rem', color: 'var(--text-muted)' }}>Candidate model</div>
            <div style={{ fontWeight: 700, color: 'var(--teal-600)' }}>{candidateVersion}</div>
          </div>
          <div>
            <div style={{ fontSize: '0.625rem', color: 'var(--text-muted)' }}>Observed gain</div>
            <div style={{ fontWeight: 700, color: 'var(--success-text)' }}>{gainStr}</div>
          </div>
          <div>
            <div style={{ fontSize: '0.625rem', color: 'var(--text-muted)' }}>Evaluation labels</div>
            <div style={{ fontWeight: 700, color: 'var(--text-primary)' }}>
              {runDetail?.config?.adaptation?.evaluation_target_events || 500}
            </div>
          </div>
        </div>
      </div>

      {/* Sub Tabs */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border-subtle)', gap: '1.5rem' }}>
        {(['summary', 'analysis', 'evidence', 'actions'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              background: 'none',
              border: 'none',
              borderBottom: activeTab === tab ? '2px solid var(--cobalt-600)' : '2px solid transparent',
              padding: '0.5rem 0.25rem',
              fontSize: '0.8125rem',
              fontWeight: activeTab === tab ? 600 : 500,
              color: activeTab === tab ? 'var(--cobalt-600)' : 'var(--text-secondary)',
              cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* VIEW: Evidence Tab */}
      {activeTab === 'evidence' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.8fr) minmax(0, 1.2fr)', gap: '1.25rem' }}>
          {/* Left: 3 Numbered Cards */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {/* 1. Prediction error increased */}
            <div className="card">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem', marginBottom: '0.75rem' }}>
                <span style={{ width: '22px', height: '22px', borderRadius: '50%', backgroundColor: 'var(--cobalt-50)', color: 'var(--cobalt-600)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '0.75rem' }}>
                  1
                </span>
                <div>
                  <div style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                    Prediction error increased
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Statistical change detected on streaming monitoring channel.
                  </div>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '1rem' }}>
                <div style={{ background: 'var(--bg-surface-subtle)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                  <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>Current observed error</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--danger-text)', margin: '0.25rem 0' }}>
                    {errorRateStr}
                  </div>
                  <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                    {fullSyntheticError?.sample_count ? `${fullSyntheticError.sample_count} evaluated events` : 'Monitored evaluation'}
                  </div>
                </div>

                <div style={{ background: 'var(--bg-surface-subtle)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                  <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>Detector delta (ADWIN)</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--cobalt-600)', margin: '0.25rem 0' }}>
                    {runDetail?.config?.monitoring?.adwin_delta || 0.002}
                  </div>
                  <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                    Confidence threshold parameter
                  </div>
                </div>
              </div>
            </div>

            {/* 2. Random labels support the change */}
            <div className="card">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem', marginBottom: '0.75rem' }}>
                <span style={{ width: '22px', height: '22px', borderRadius: '50%', backgroundColor: 'var(--cobalt-50)', color: 'var(--cobalt-600)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '0.75rem' }}>
                  2
                </span>
                <div>
                  <div style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                    Independent random monitoring labels
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Random labels sampled from stream for unbiased candidate evaluation.
                  </div>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '0.75rem' }}>
                <div style={{ background: 'var(--bg-surface-subtle)', padding: '0.75rem', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>Monitoring rate</div>
                  <div style={{ fontSize: '1.125rem', fontWeight: 700, color: 'var(--cobalt-600)' }}>
                    {((runDetail?.monitoring_coverage ?? 0.2) * 100).toFixed(0)}%
                  </div>
                  <div style={{ fontSize: '0.625rem', color: 'var(--text-muted)' }}>Independent random sample</div>
                </div>

                <div style={{ background: 'var(--bg-surface-subtle)', padding: '0.75rem', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>Target eval labels</div>
                  <div style={{ fontSize: '1.125rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                    {runDetail?.config?.adaptation?.evaluation_target_events || 500}
                  </div>
                  <div style={{ fontSize: '0.625rem', color: 'var(--text-muted)' }}>Post-alert quota</div>
                </div>

                <div style={{ background: 'var(--bg-surface-subtle)', padding: '0.75rem', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>Label delay</div>
                  <div style={{ fontSize: '1.125rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                    {runDetail?.config?.labels?.label_delay || 0}
                  </div>
                  <div style={{ fontSize: '0.625rem', color: 'var(--text-muted)' }}>Configured event delay</div>
                </div>
              </div>
            </div>

            {/* 3. Candidate improves observed outcomes */}
            <div className="card">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem', marginBottom: '0.75rem' }}>
                <span style={{ width: '22px', height: '22px', borderRadius: '50%', backgroundColor: 'var(--teal-50)', color: 'var(--teal-600)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '0.75rem' }}>
                  3
                </span>
                <div>
                  <div style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                    Paired McNemar evaluation
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Candidate vs active model comparison on identical observations.
                  </div>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '0.75rem' }}>
                <div style={{ background: 'var(--teal-50)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--teal-200)' }}>
                  <div style={{ fontSize: '0.6875rem', color: 'var(--teal-800)', fontWeight: 600 }}>Candidate wins (b)</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--teal-700)' }}>{bCount}</div>
                  <div style={{ fontSize: '0.625rem', color: 'var(--teal-600)' }}>Cand correct, active wrong</div>
                </div>

                <div style={{ background: 'var(--bg-surface-subtle)', padding: '0.75rem', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>Active wins (c)</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>{cCount}</div>
                  <div style={{ fontSize: '0.625rem', color: 'var(--text-muted)' }}>Active correct, cand wrong</div>
                </div>

                <div style={{ background: 'var(--success-bg)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--success-border)' }}>
                  <div style={{ fontSize: '0.6875rem', color: 'var(--success-text)', fontWeight: 600 }}>Observed gain</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--success-text)' }}>{gainStr}</div>
                  <div style={{ fontSize: '0.625rem', color: 'var(--success-text)' }}>Statistically evaluated</div>
                </div>
              </div>
            </div>
          </div>

          {/* Right: Conclusions & Uncertainty */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div className="card">
              <div style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.75rem' }}>
                Incident Audit Findings
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.75rem' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem' }}>
                  <CheckCircle2 size={15} color="var(--teal-600)" style={{ flexShrink: 0, marginTop: '2px' }} />
                  <div>
                    <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Alert confirmed: </span>
                    <span style={{ color: 'var(--text-secondary)' }}>
                      Detector triggered at event sequence #{incident?.event_sequence || '—'}.
                    </span>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem' }}>
                  <CheckCircle2 size={15} color="var(--teal-600)" style={{ flexShrink: 0, marginTop: '2px' }} />
                  <div>
                    <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Candidate state: </span>
                    <span style={{ color: 'var(--text-secondary)' }}>
                      {runDetail?.candidate_state || 'NONE'} (gain: {gainStr}).
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div className="card" style={{ fontSize: '0.75rem' }}>
              <div style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
                Assumptions & Design
              </div>
              <div className="kv-list">
                <div className="kv-row">
                  <span className="kv-key">Evaluation design</span>
                  <span className="kv-val">Independent random monitoring</span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">Significance test</span>
                  <span className="kv-val">Paired McNemar (b vs c)</span>
                </div>
                <div className="kv-row">
                  <span className="kv-key">Stream type</span>
                  <span className="kv-val">Controlled synthetic stream</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* VIEW: Analysis Tab */}
      {activeTab === 'analysis' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)', gap: '1.25rem' }}>
          <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div className="card-header">
              <span className="card-title" style={{ fontSize: '0.875rem' }}>
                Incident Analysis & Evidence Ledger
              </span>
            </div>

            <div className="kv-list" style={{ fontSize: '0.8125rem' }}>
              <div className="kv-row">
                <span className="kv-key">Incident ID</span>
                <span className="kv-val" style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{incident?.incident_id || 'DRF-0248'}</span>
              </div>
              <div className="kv-row">
                <span className="kv-key">Triggered at sequence</span>
                <span className="kv-val">Event #{incident?.event_sequence || '—'}</span>
              </div>
              <div className="kv-row">
                <span className="kv-key">Detection delay</span>
                <span className="kv-val">{detectionDelay != null ? `${detectionDelay} events` : '—'}</span>
              </div>
              <div className="kv-row">
                <span className="kv-key">Affected baseline model</span>
                <span className="kv-val">{activeVersion}</span>
              </div>
              <div className="kv-row">
                <span className="kv-key">Candidate lifecycle</span>
                <span className="kv-val" style={{ color: 'var(--teal-600)', fontWeight: 600 }}>
                  {runDetail?.candidate_state || 'NONE'}
                </span>
              </div>
              <div className="kv-row">
                <span className="kv-key">Observed paired gain</span>
                <span className="kv-val" style={{ color: 'var(--success-text)', fontWeight: 600 }}>
                  {gainStr}
                </span>
              </div>
            </div>
          </div>

          <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              Quick Actions
            </div>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              Candidate models that pass the paired McNemar significance test are automatically promoted by the DriftShield engine.
            </p>
            <button
              className="btn btn-primary"
              style={{ marginTop: 'auto', fontWeight: 600 }}
              onClick={() => onNavigateActions && onNavigateActions(runDetail?.run_id || runId || undefined)}
            >
              Review promotion action <ArrowRight size={14} />
            </button>
          </div>
        </div>
      )}

      {/* VIEW: Summary Tab */}
      {activeTab === 'summary' && (
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            Incident Summary
          </div>
          <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            Incident {incident?.incident_id || 'DRF-0248'} was triggered at sequence #{incident?.event_sequence || '—'} following statistical drift detection. Background candidate training and paired McNemar evaluation were conducted on independent random monitoring labels.
          </p>
        </div>
      )}

      {/* VIEW: Actions Tab */}
      {activeTab === 'actions' && (
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            Available Incident Actions
          </div>
          <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
            Proceed to the Actions page to review candidate model comparison and automated promotion readiness.
          </p>
          <button
            className="btn btn-primary"
            style={{ width: 'fit-content' }}
            onClick={() => onNavigateActions && onNavigateActions(runDetail?.run_id || runId || undefined)}
          >
            Go to Model Promotion Review <ArrowRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
};
