import React from 'react';
import { formatDistanceToNow } from 'date-fns';

function StatusBadge({ status }) {
  const colors = {
    pending:     { bg: 'rgba(88,166,255,0.15)',  color: '#58a6ff' },
    in_progress: { bg: 'rgba(188,140,255,0.15)', color: '#bc8cff' },
    completed:   { bg: 'rgba(63,185,80,0.15)',   color: '#3fb950' },
    reassigned:  { bg: 'rgba(139,148,158,0.15)', color: '#8b949e' },
  };
  const style = colors[status] || colors.pending;
  return (
    <span className="badge" style={{ background: style.bg, color: style.color, border: `1px solid ${style.color}33` }}>
      {status}
    </span>
  );
}

export default function AssignmentsView({ assignments }) {
  if (!assignments || assignments.length === 0) {
    return (
      <div className="card">
        <div className="card-header"><span className="card-title">🎯 Assignments</span></div>
        <div className="card-body">
          <div className="empty-state">
            <p>No assignments yet. Submit a PR to trigger automatic routing.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">🎯 Review Assignments</span>
        <span style={{ fontSize: 12, color: 'var(--text2)' }}>{assignments.length} total</span>
      </div>
      <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
        <table className="assignments-table">
          <thead>
            <tr>
              <th>PR</th>
              <th>Reviewer</th>
              <th>Status</th>
              <th>Score</th>
              <th>Routing Reason</th>
              <th>Assigned</th>
            </tr>
          </thead>
          <tbody>
            {assignments.map(a => {
              let timeAgo = '';
              try {
                timeAgo = formatDistanceToNow(new Date(a.assigned_at), { addSuffix: true });
              } catch { timeAgo = '—'; }

              return (
                <tr key={a.id}>
                  <td>
                    <div style={{ fontWeight: 500, fontSize: 13 }}>{a.pr_title}</div>
                    <div style={{ fontSize: 11, color: 'var(--text2)' }}>{a.pr_repo}</div>
                  </td>
                  <td>
                    <div style={{ fontWeight: 500 }}>{a.reviewer_name || a.reviewer_username}</div>
                    <div style={{ fontSize: 11, color: 'var(--text2)' }}>@{a.reviewer_username}</div>
                  </td>
                  <td><StatusBadge status={a.status} /></td>
                  <td style={{ color: 'var(--accent)', fontWeight: 600 }}>
                    {typeof a.score === 'number' ? a.score.toFixed(2) : '—'}
                  </td>
                  <td style={{ fontSize: 12, color: 'var(--text2)', maxWidth: 200 }}>
                    {a.routing_reason || '—'}
                  </td>
                  <td style={{ fontSize: 12, color: 'var(--text2)', whiteSpace: 'nowrap' }}>
                    {timeAgo}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}