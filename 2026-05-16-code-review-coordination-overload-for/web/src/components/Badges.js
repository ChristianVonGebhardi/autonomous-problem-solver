import React from 'react';

export function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{status}</span>;
}

export function ComplexityBadge({ score }) {
  if (!score && score !== 0) return null;
  const pct = Math.round(score * 100);
  const level = score > 0.7 ? 'high' : score > 0.4 ? 'medium' : 'low';
  return (
    <span className="complexity-bar">
      <div className="complexity-track">
        <div
          className="complexity-fill"
          style={{
            width: `${pct}%`,
            background: level === 'high' ? 'var(--red)' : level === 'medium' ? 'var(--yellow)' : 'var(--green)',
          }}
        />
      </div>
      <span className={`badge badge-${level}`} style={{ fontSize: 11 }}>{pct}%</span>
    </span>
  );
}