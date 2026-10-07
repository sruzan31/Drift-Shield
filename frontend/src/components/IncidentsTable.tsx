import React, { useState } from 'react';
import { AlertTriangle, ChevronLeft, ChevronRight, Info } from 'lucide-react';
import type { IncidentItem } from '../types';
import { StatusBadge } from './StatusBadge';

interface IncidentsTableProps {
  incidents: IncidentItem[];
  totalIncidents: number;
  page: number;
  pageSize: number;
  onPageChange: (newPage: number) => void;
  isLoading: boolean;
}

export const IncidentsTable: React.FC<IncidentsTableProps> = ({
  incidents,
  totalIncidents,
  page,
  pageSize,
  onPageChange,
  isLoading,
}) => {
  const [selectedIncident, setSelectedIncident] = useState<IncidentItem | null>(null);

  const totalPages = Math.max(1, Math.ceil(totalIncidents / pageSize));

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">
          <AlertTriangle size={16} color="var(--warning-solid)" />
          Error-Change Incidents & Adaptation Evidence
        </span>
        <span className="badge badge-neutral" style={{ fontSize: '0.6875rem' }}>
          {totalIncidents} Recorded Incidents
        </span>
      </div>

      {isLoading ? (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          Loading incident records...
        </div>
      ) : incidents.length === 0 ? (
        <div
          style={{
            padding: '2rem',
            textAlign: 'center',
            backgroundColor: 'var(--bg-surface-subtle)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--text-muted)',
            fontSize: '0.8125rem',
          }}
        >
          No error-change alerts or incidents triggered. (Classifier stable within statistical bounds).
        </div>
      ) : (
        <>
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th>Incident ID</th>
                  <th>Event Seq</th>
                  <th>Arrival Seq</th>
                  <th>Detection Delay</th>
                  <th>Model Version</th>
                  <th>Candidate ID</th>
                  <th>Outcome</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {incidents.map((inc) => (
                  <tr key={inc.incident_id}>
                    <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{inc.incident_id}</td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{inc.event_sequence}</td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{inc.arrival_sequence}</td>
                    <td>
                      <span className="badge badge-neutral" style={{ fontFamily: 'var(--font-mono)' }}>
                        +{inc.detection_delay} events
                      </span>
                    </td>
                    <td>{inc.model_version}</td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{inc.candidate_id || '—'}</td>
                    <td>
                      <StatusBadge status={inc.outcome || 'PENDING'} />
                    </td>
                    <td>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => setSelectedIncident(inc)}
                        title="View raw evidence json"
                      >
                        <Info size={12} /> Evidence
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginTop: '0.75rem',
                fontSize: '0.8125rem',
                color: 'var(--text-secondary)',
              }}
            >
              <div>
                Page {page} of {totalPages} ({totalIncidents} total)
              </div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  className="btn btn-secondary btn-sm"
                  disabled={page <= 1}
                  onClick={() => onPageChange(page - 1)}
                >
                  <ChevronLeft size={14} /> Previous
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  disabled={page >= totalPages}
                  onClick={() => onPageChange(page + 1)}
                >
                  Next <ChevronRight size={14} />
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Raw Evidence Modal */}
      {selectedIncident && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
            padding: '1rem',
          }}
          onClick={() => setSelectedIncident(null)}
        >
          <div
            className="card"
            style={{ maxWidth: '600px', width: '100%', maxHeight: '80vh', overflowY: 'auto' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="card-header">
              <span className="card-title">
                Evidence Record: {selectedIncident.incident_id}
              </span>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setSelectedIncident(null)}
              >
                Close
              </button>
            </div>
            <div style={{ marginBottom: '1rem' }}>
              <div style={{ fontWeight: 600, fontSize: '0.875rem', marginBottom: '0.25rem' }}>
                Alert Description
              </div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem' }}>
                {selectedIncident.alert_type}
              </div>
            </div>
            <div>
              <div style={{ fontWeight: 600, fontSize: '0.875rem', marginBottom: '0.5rem' }}>
                Structured Evidence Payload (Persisted SQLite JSON)
              </div>
              <pre
                style={{
                  backgroundColor: 'var(--bg-app)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '0.75rem',
                  fontSize: '0.75rem',
                  fontFamily: 'var(--font-mono)',
                  overflowX: 'auto',
                  color: 'var(--text-primary)',
                }}
              >
                {JSON.stringify(selectedIncident.evidence, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
