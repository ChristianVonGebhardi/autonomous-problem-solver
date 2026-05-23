import React from 'react';
import { ComplexityBadge, StatusBadge } from './Badges';

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
                    #{pr.pr_number} {pr.title}
                  </span>
                  <ComplexityBadge score={pr.complexity_score} />
                </div>
                <div className="queue-pr-meta">
                  {pr.repo_owner}/{pr.repo_name} · by @{pr.author}
                  {pr.lines_added + pr.lines_deleted > 0 && (
                    <> · <span style={{ color: 'var(--green)' }}>+{pr.lines_added}</span>/<span style={{ color: 'var(--red)' }}>-{pr.lines_deleted}</span></>
                  )}
                  {pr.estimated_minutes > 0 && ` · ~${pr.estimated_minutes}min to review`}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}