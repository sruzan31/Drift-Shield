import React from 'react';

interface StatusBadgeProps {
  status: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  const norm = (status || 'UNKNOWN').toUpperCase();

  let badgeClass = 'badge-neutral';

  switch (norm) {
    case 'RUNNING':
    case 'PROMOTED':
    case 'TRAINING_COMPLETED':
      badgeClass = 'badge-success';
      break;
    case 'WARMUP':
    case 'INITIALIZING':
    case 'TRAINING':
    case 'READY_FOR_EVALUATION':
    case 'EVALUATING':
    case 'TRAINING_INITIATED':
      badgeClass = 'badge-info';
      break;
    case 'PAUSED':
    case 'INCOMPLETE':
    case 'IGNORED':
      badgeClass = 'badge-warning';
      break;
    case 'STOPPED':
    case 'INTERRUPTED':
    case 'REJECTED':
      badgeClass = 'badge-danger';
      break;
    case 'COMPLETED':
      badgeClass = 'badge-success';
      break;
    default:
      badgeClass = 'badge-neutral';
  }

  return <span className={`badge ${badgeClass}`}>{norm}</span>;
};
