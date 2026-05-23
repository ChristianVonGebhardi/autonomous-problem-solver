import React from 'react';

function ComplexityBadge({ score }) {
  if (!score && score !== 0) return null;
  const pct = Math.round(score * 10);  // score is 0-10
  const normalized = score / 10;
  const level = score > 7 ? 'high' : score > 4 ? 'medium' : 'low';
  const colors = { high: 'var(--red)', medium: 'var(--yellow)', low: 'var(--green)' };
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      <div style={{ width: 50, height: 4, background: 'var(--bg)', borderRadius: 2 }}>
        <div style={{ width: `${normalized * 100}%`, height: '100%', background: colors[level], borderRadius: 2 }} />
      </div>
      <span className={`badge badge-${level}`} style={{ fontSize: 10 }}>{score?.toFixed(1)}</span>
    </span>
  );
}

export default function PRQueue({ queue, onRefresh, detailed }) {
  const prs = queue?.prs || [];

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">⏳ Review Queue</span>
        <span style={{ fontSize: 12, color: 'var(--text2)' }}>
          {queue?.queue_length ?? 0} pending
        </span>
      </div>
      <div className="card-body">
        {prs.length === 0 ? (
          <div className="queue-empty">
            ✅ Queue is empty — all PRs are assigned!
          </div>
        ) : (
          <div className="pr-queue-list">
            {prs.map(pr => (
              <div key={pr.id} className="queue-item">
                <div className="queue-item-header">
                  <span className="queue-pr-title" title={pr.title}>
                    {pr.external_id && `#${pr.external_id} `}{pr.title}
                  </span>
                  <ComplexityBadge score={pr.complexity_score} />
                </div>
                <div className="queue-pr-meta">
                  {pr.repo_full_name} · by @{pr.author}
                  {(pr.lines_added + pr.lines_deleted) > 0 && (
                    <> · <span style={{ color: 'var(--green)' }}>+{pr.lines_added}</span>/<span style={{ color: 'var(--red)' }}>-{pr.lines_deleted}</span></>
                  )}
                  {pr.estimated_minutes && ` · ~${pr.estimated_minutes}min`}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}