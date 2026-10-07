import React from 'react';
import { TrendingUp } from 'lucide-react';

export interface ChartPoint {
  sequence: number;
  eventsProcessed: number;
  errorRate: number; // 0.0 to 1.0
  timestamp: number;
}

interface CumulativeChartProps {
  points: ChartPoint[];
  totalEvents: number;
}

export const CumulativeChart: React.FC<CumulativeChartProps> = ({ points, totalEvents }) => {
  if (points.length < 2) {
    return (
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <TrendingUp size={16} color="var(--cobalt-600)" />
            Real-Time Cumulative Error Trajectory
          </span>
          <span className="badge badge-neutral" style={{ fontSize: '0.6875rem' }}>
            Cumulative Error (Actual Snapshots)
          </span>
        </div>
        <div
          style={{
            height: '200px',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: 'var(--bg-surface-subtle)',
            borderRadius: 'var(--radius-sm)',
            border: '1px dashed var(--border-subtle)',
            color: 'var(--text-muted)',
            fontSize: '0.8125rem',
            gap: '0.5rem',
          }}
        >
          <div>Accumulating actual stream snapshot observations...</div>
          <div style={{ fontSize: '0.75rem' }}>Plot updates live every ~500 ms as evaluated losses arrive.</div>
        </div>
      </div>
    );
  }

  // SVG Chart dimensions
  const width = 800;
  const height = 220;
  const padding = { top: 20, right: 30, bottom: 35, left: 50 };

  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;

  const maxX = Math.max(totalEvents, points[points.length - 1].eventsProcessed);

  // Y axis scale: 0% to 100% or dynamic max
  const maxErr = Math.max(...points.map((p) => p.errorRate), 0.2);
  const maxY = Math.min(1.0, Math.ceil(maxErr * 10) / 10 + 0.1);

  const getX = (val: number) => padding.left + (val / maxX) * plotWidth;
  const getY = (val: number) => padding.top + plotHeight - (val / maxY) * plotHeight;

  // Build SVG path
  const pathD = points.reduce((acc, p, idx) => {
    const x = getX(p.eventsProcessed);
    const y = getY(p.errorRate);
    return idx === 0 ? `M ${x} ${y}` : `${acc} L ${x} ${y}`;
  }, '');

  // Fill area under path
  const firstX = getX(points[0].eventsProcessed);
  const lastX = getX(points[points.length - 1].eventsProcessed);
  const bottomY = padding.top + plotHeight;
  const areaD = `${pathD} L ${lastX} ${bottomY} L ${firstX} ${bottomY} Z`;

  const lastPoint = points[points.length - 1];

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">
          <TrendingUp size={16} color="var(--cobalt-600)" />
          Cumulative Classification Error Trajectory
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Latest Observed Mean:</span>
          <span className="badge badge-info" style={{ fontFamily: 'var(--font-mono)' }}>
            {(lastPoint.errorRate * 100).toFixed(2)}%
          </span>
          <span className="badge badge-neutral" style={{ fontSize: '0.6875rem' }}>
            Actual Live Snapshots
          </span>
        </div>
      </div>

      <div style={{ width: '100%', overflowX: 'auto' }}>
        <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto', minWidth: '500px' }}>
          {/* Grid lines (Y) */}
          {[0, 0.25, 0.5, 0.75, 1.0].map((tick) => {
            if (tick > maxY) return null;
            const y = getY(tick);
            return (
              <g key={tick}>
                <line
                  x1={padding.left}
                  y1={y}
                  x2={width - padding.right}
                  y2={y}
                  stroke="var(--border-subtle)"
                  strokeDasharray="3 3"
                />
                <text
                  x={padding.left - 8}
                  y={y + 4}
                  textAnchor="end"
                  fill="var(--text-muted)"
                  fontSize="10"
                  fontFamily="var(--font-mono)"
                >
                  {(tick * 100).toFixed(0)}%
                </text>
              </g>
            );
          })}

          {/* Grid lines (X) */}
          {[0, 0.25, 0.5, 0.75, 1.0].map((frac) => {
            const ev = Math.round(maxX * frac);
            const x = getX(ev);
            return (
              <g key={frac}>
                <line
                  x1={x}
                  y1={padding.top}
                  x2={x}
                  y2={padding.top + plotHeight}
                  stroke="var(--border-subtle)"
                  strokeDasharray="3 3"
                />
                <text
                  x={x}
                  y={height - 12}
                  textAnchor="middle"
                  fill="var(--text-muted)"
                  fontSize="10"
                  fontFamily="var(--font-mono)"
                >
                  {ev}
                </text>
              </g>
            );
          })}

          {/* Axis Labels */}
          <text
            x={padding.left + plotWidth / 2}
            y={height - 2}
            textAnchor="middle"
            fill="var(--text-secondary)"
            fontSize="11"
            fontWeight="500"
          >
            Stream Events Processed
          </text>

          {/* Shaded Area */}
          <path d={areaD} fill="var(--cobalt-50)" opacity="0.7" />

          {/* Trajectory Line */}
          <path d={pathD} fill="none" stroke="var(--cobalt-600)" strokeWidth="2.5" strokeLinecap="round" />

          {/* Current point dot */}
          <circle
            cx={getX(lastPoint.eventsProcessed)}
            cy={getY(lastPoint.errorRate)}
            r="4.5"
            fill="var(--cobalt-700)"
            stroke="var(--bg-surface)"
            strokeWidth="2"
          />
        </svg>
      </div>
      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.5rem', textAlign: 'right' }}>
        * Plotted strictly from authenticated backend snapshot records; not smoothed or synthesized.
      </div>
    </div>
  );
};
