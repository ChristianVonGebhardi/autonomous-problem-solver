import React from 'react';
import { formatDistanceToNow } from 'date-fns';

const EVENT_ICONS = {
  pull_request: '🔀',
  push: '📤',
  Merge_Request_Hook: '🔀',
  default: '📋',
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
            <p>No webhook events yet.</p>
            <p style={{ marginTop: 8, fontSize: 12 }}>
              Trigger a PR event via the ingestion service to see activity here.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">📝 Recent Webhook Events</span>
        <span style={{ fontSize: 12, color: 'var(--text2)' }}>{events.length} events</span>
      </div>
      <div className="card-body">
        <div className="activity-list">
          {events.map(evt => {
            const icon = EVENT_ICONS[evt.event_type] || EVENT_ICONS.default;
            let timeAgo = '';
            try {
              timeAgo = formatDistanceToNow(new Date(evt.created_at), { addSuffix: true });
            } catch {
              timeAgo = evt.created_at || '';
            }

            return (
              <div key={evt.id} className="activity-item">
                <span className="activity-icon">{icon}</span>
                <div className="activity-content">
                  <div className="activity-main">
                    <strong>{evt.event_type}</strong>
                    {evt.reviewer && (
                      <> from <span style={{ color: 'var(--accent)' }}>{evt.reviewer}</span></>
                    )}
                    {evt.processed !== undefined && (
                      <span style={{
                        marginLeft: 8, fontSize: 11,
                        color: evt.processed ? 'var(--green)' : 'var(--yellow)',
                      }}>
                        {evt.processed ? '✓ processed' : '⏳ pending'}
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