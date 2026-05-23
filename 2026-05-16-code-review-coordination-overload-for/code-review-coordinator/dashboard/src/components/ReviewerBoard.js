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

function stringToColor(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const colors = ['#1f6feb', '#388bfd', '#58a6ff', '#7c3aed', '#9c1b95', '#c0392b', '#16a085', '#d35400'];
  return colors[Math.abs(hash) % colors.length];
}

export default function ReviewerBoard({ reviewers, detailed }) {
  if (!reviewers || reviewers.length === 0) {
    return (
      <div className="card">
        <div className="card-header"><span className="card-title">👥 Reviewers</span></div>
        <div className="card-body">
          <div className="empty-state">
            <p>No reviewers configured yet.</p>
            <p style={{ marginTop: 8, fontSize: 12, color: 'var(--text2)' }}>
              Run <code style={{ background: 'var(--bg3)', padding: '2px 6px', borderRadius: 4 }}>./scripts/seed.sh</code> to add sample data.
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
            const name = r.display_name || r.username;
            const initials = name.split(/[\s_-]/).map(w => w[0]).join('').toUpperCase().slice(0, 2);
            const load = r.current_load ?? 0;
            const maxLoad = r.max_load || r.max_concurrent_reviews || 3;
            const statusClass = !r.is_active
              ? 'status-unavailable'
              : load >= maxLoad
              ? 'status-busy'
              : 'status-available';

            return (
              <div key={r.username} className="reviewer-row">
                <div className="reviewer-avatar" style={{ background: stringToColor(r.username) }}>
                  {initials}
                </div>
                <div className="reviewer-info">
                  <div className="reviewer-name">{name}</div>
                  <div className="reviewer-meta">
                    @{r.username}
                    {detailed && r.avg_review_time_minutes > 0 && ` · avg ${r.avg_review_time_minutes}min/review`}
                  </div>
                </div>
                <LoadBar current={load} max={maxLoad} />
                {detailed && (
                  <span className="badge" style={{ marginLeft: 8, fontSize: 11, color: 'var(--text2)' }}>
                    {r.completed_today ?? 0} done today
                  </span>
                )}
                <div
                  className={`status-dot ${statusClass}`}
                  title={!r.is_active ? 'Unavailable' : load >= maxLoad ? 'At capacity' : 'Available'}
                />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}