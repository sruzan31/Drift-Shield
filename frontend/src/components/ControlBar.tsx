import React, { useState } from 'react';
import { Play, Pause, Square, FastForward, AlertTriangle } from 'lucide-react';
import { StatusBadge } from './StatusBadge';

interface ControlBarProps {
  operationalState: string;
  onControl: (action: 'start' | 'pause' | 'resume' | 'stop') => Promise<void>;
  isLoading: boolean;
}

export const ControlBar: React.FC<ControlBarProps> = ({
  operationalState,
  onControl,
  isLoading,
}) => {
  const [showStopModal, setShowStopModal] = useState(false);

  const stateNorm = (operationalState || 'INITIALIZING').toUpperCase();

  const canStart = stateNorm === 'CREATED' || stateNorm === 'INITIALIZING' || stateNorm === 'WARMUP';
  const canPause = stateNorm === 'WARMUP' || stateNorm === 'RUNNING';
  const canResume = stateNorm === 'PAUSED';
  const canStop = ['CREATED', 'INITIALIZING', 'WARMUP', 'RUNNING', 'PAUSED'].includes(stateNorm);

  const handleStopConfirmed = async () => {
    setShowStopModal(false);
    await onControl('stop');
  };

  return (
    <>
      <div
        className="card"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '1rem',
          padding: '1rem 1.25rem',
        }}
      >
        {/* Left: Status Indicator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>
              Execution Lifecycle
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.125rem' }}>
              <StatusBadge status={stateNorm} />
            </div>
          </div>
        </div>

        {/* Right: Lifecycle Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {canStart && (
            <button
              id="btn-start-stream"
              className="btn btn-primary"
              onClick={() => onControl('start')}
              disabled={isLoading}
            >
              <Play size={14} /> Start Stream
            </button>
          )}

          {canPause && (
            <button
              id="btn-pause-stream"
              className="btn btn-secondary"
              onClick={() => onControl('pause')}
              disabled={isLoading}
            >
              <Pause size={14} /> Pause
            </button>
          )}

          {canResume && (
            <button
              id="btn-resume-stream"
              className="btn btn-primary"
              onClick={() => onControl('resume')}
              disabled={isLoading}
            >
              <FastForward size={14} /> Resume
            </button>
          )}

          {canStop && (
            <button
              id="btn-stop-stream"
              className="btn btn-danger"
              onClick={() => setShowStopModal(true)}
              disabled={isLoading}
            >
              <Square size={14} /> Stop
            </button>
          )}
        </div>
      </div>

      {/* Stop Confirmation Modal */}
      {showStopModal && (
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
          onClick={() => setShowStopModal(false)}
        >
          <div
            className="card"
            style={{ maxWidth: '480px', width: '100%' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="card-header">
              <span className="card-title" style={{ color: 'var(--danger-text)' }}>
                <AlertTriangle size={18} color="var(--danger-solid)" />
                Confirm Stream Termination
              </span>
            </div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: '1.25rem' }}>
              Are you sure you want to stop this simulation run?
              <ul style={{ marginTop: '0.5rem', paddingLeft: '1.25rem', color: 'var(--text-primary)' }}>
                <li>Pending authorized labels up to the stop sequence will be drained.</li>
                <li>Any active candidate training will be finalized as <strong>INCOMPLETE</strong>.</li>
                <li>The run state will transition permanently to <strong>STOPPED</strong>.</li>
              </ul>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
              <button
                className="btn btn-secondary"
                onClick={() => setShowStopModal(false)}
                disabled={isLoading}
              >
                Cancel
              </button>
              <button
                className="btn btn-danger"
                onClick={handleStopConfirmed}
                disabled={isLoading}
              >
                Confirm Stop
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
