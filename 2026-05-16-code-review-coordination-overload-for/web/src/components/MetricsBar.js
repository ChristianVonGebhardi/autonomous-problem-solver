import React from 'react';

function fmt(val, decimals = 1) {
  if (val === null || val === undefined) return '—';
  return Number(val).toFixed(decimals);
}

export default function MetricsBar({ metrics, queueLength }) {
  const m = metrics?.metrics || {};

  const assignClass = m.avg_time_to_assign_minutes < 30 ? 'good' : m.avg_time_to_assign_minutes < 75 ? 'warn' : 'bad';
  const mergeClass = m.avg_time_to_merge_hours < 3 ? 'good' : m.avg_time_to_merge_hours < 24 ? 'warn' : 'bad';
  const queueClass = queueLength === 0 ? 'good' : queueLength < 5 ? 'warn' : 'bad';

  return (
    <div className="metrics-bar">
      <div className="metric-item">
        <span className="metric-label">Active PRs</span>
        <span className="metric-value">{m.active_prs ?? 0}</span>
        <span className="metric-sub">{m.prs_today ?? 0} opened today</span>
      </div>
      <div className="metric-item">
        <span className="metric-label">Queue Depth</span>
        <span className={`metric-value ${queueClass}`}>{queueLength ?? 0}</span>
        <span className="metric-sub">awaiting assignment</span>
      </div>
      <div className="metric-item">
        <span className="metric-label">Avg Assign Time</span>
        <span className={`metric-value ${assignClass}`}>{fmt(m.avg_time_to_assign_minutes)}m</span>
        <span className="metric-sub">target: &lt;75 min</span>
      </div>
      <div className="metric-item">
        <span className="metric-label">Avg Merge Time</span>
        <span className={`metric-value ${mergeClass}`}>{fmt(m.avg_time_to_merge_hours)}h</span>
        <span className="metric-sub">target: &lt;3 hours</span>
      </div>
      <div className="metric-item">
        <span className="metric-label">Completed Today</span>
        <span className="metric-value good">{m.prs_completed_today ?? 0}</span>
        <span className="metric-sub">reviews done</span>
      </div>
      {m.bottleneck_reviewers && m.bottleneck_reviewers.length > 0 && (
        <div className="metric-item">
          <span className="metric-label">⚠ Bottlenecks</span>
          <span className="metric-value bad">{m.bottleneck_reviewers.length}</span>
          <span className="metric-sub">{m.bottleneck_reviewers.join(', ')}</span>
        </div>
      )}
    </div>
  );
}