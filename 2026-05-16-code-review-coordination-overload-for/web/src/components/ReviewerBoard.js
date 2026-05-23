import React from 'react';

function LoadBar({ current, max }) {
  const pct = max > 0 ? Math.min(1, current / max) : 0;
  const cls = pct < 0.5 ? 'load-low' : pct < 0.85 ? 'load-med' : 'load-high';
  return (
    <div className="reviewer-load">
      <div className="load-bar-bg">
        <div className={`load-bar ${cls}`} style={{ width: `${pct * 100}%` }} />
      </div>
      <span className="load-text">{current}/{max}</span>
    </div>
  );
}

export default function ReviewerBoard({ reviewers, detailed }) {
  if (!reviewers || reviewers.length === 0) {
    return (
      <div className="card">
        <div className="card-header"><span className="card-title">👥 Reviewers</span></div>
        <div className="card-body">
          <div className="empty-state">
            <p>No reviewers configured yet.</p>
            <p style={{ marginTop: 8, fontSize: 12 }}>
              POST to <code>/api/reviewers</code> on the capacity service (port 8083) to add reviewers.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">👥 Reviewer Capacity</span>
        <span style={{ fontSize: 12, color: 'var(--text2)' }}>{reviewers.length} reviewers</span>
      </div>
      <div className="card-body">
        <div className="reviewer-list">
          {reviewers.map(r => {
            const initials = (r.full_name || r.username)
              .split(/[\s_-]/).map(w => w[0]).join('').toUpperCase().slice(0, 2);
            const statusClass = !r.is_available
              ? 'status-unavailable'
              : r.current_load >= r.max_load
              ? 'status-busy'
              : 'status-available';
            const utilPct = r.max_load > 0 ? (r.current_load / r.max_load) * 100 : 0;

            return (
              <div key={r.username} className="reviewer-row">
                <div className="reviewer-avatar" style={{
                  background: stringToColor(r.username)
                }}>{initials}</div>
                <div className="reviewer-info">
                  <div className="reviewer-name">{r.full_name || r.username}</div>
                  <div className="reviewer-meta">@{r.username}{detailed && r.avg_review_time > 0 ? ` · avg ${r.avg_review_time}min/review` : ''}</div>
                </div>
                <LoadBar current={r.current_load} max={r.max_load} />
                {detailed && (
                  <span className="badge" style={{ marginLeft: 8, fontSize: 11, color: 'var(--text2)' }}>
                    {r.total_reviews} done
                  </span>
                )}
                <div className={`status-dot ${statusClass}`} title={
                  !r.is_available ? 'Unavailable' : r.current_load >= r.max_load ? 'At capacity' : 'Available'
                } />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function stringToColor(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const colors = ['#1f6feb', '#388bfd', '#58a6ff', '#7c3aed', '#9c1b95', '#c0392b', '#16a085', '#d35400'];
  return colors[Math.abs(hash) % colors.length];
}