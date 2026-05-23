import React from 'react';
import { formatDistanceToNow } from 'date-fns';

const EVENT_ICONS = {
  assigned: '🎯',
  review_completed: '✅',
  review_started: '👀',
  reassigned: '↩️',
  opened: '🔀',
  closed: '🔒',
  merged: '🚀',
  default: '📝',
};

const EVENT_LABELS = {
  assigned: 'Assigned',
  review_completed: 'Review completed',
  review_started: 'Review started',
  reassigned: 'Reassigned',
  opened: 'PR opened',
  closed: 'PR closed',
  merged: 'PR merged',
};

export default function ActivityFeed({ events }) {
  if (!events || events.length === 0) {
    return (
      <div className="card">
        <div className="card-header">
          <span className="card-title">📝 Recent Activity</span>
        </div>
        <div className="card-body">
          <div className="empty-state">
            <p>No activity yet. Create a PR to get started.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">📝 Recent Activity</span>
        <span style={{ fontSize: 12, color: 'var(--text2)' }}>{events.length} events</span>
      </div>
      <div className="card-body">
        <div className="activity-list">
          {events.map(evt => {
            const icon = EVENT_ICONS[evt.event_type] || EVENT_ICONS.default;
            const label = EVENT_LABELS[evt.event_type] || evt.event_type;
            let timeAgo = '';
            try {
              timeAgo = formatDistanceToNow(new Date(evt.created_at), { addSuffix: true });
            } catch {
              timeAgo = evt.created_at;
            }

            return (
              <div key={evt.id} className="activity-item">
                <span className="activity-icon">{icon}</span>
                <div className="activity-content">
                  <div className="activity-main">
                    <strong>{label}</strong>
                    {evt.reviewer && <> — <span style={{ color: 'var(--accent)' }}>@{evt.reviewer}</span></>}
                    {evt.pr_id && (
                      <span style={{ color: 'var(--text2)', marginLeft: 6 }}>
                        PR #{evt.pr_id}
                      </span>
                    )}
                    {evt.details && (
                      <span style={{ color: 'var(--text2)', fontSize: 12, marginLeft: 6 }}>
                        · {evt.details}
                      </span>
                    )}
                  </div>
                  <div className="activity-time">{timeAgo}</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}