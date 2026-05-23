import React, { useState } from 'react';
import { api } from '../api';

const STATUS_FILTERS = ['all', 'open', 'assigned', 'in_review', 'completed', 'merged'];

function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{status}</span>;
}

export default function PRList({ prs, reviewers, onRefresh }) {
  const [filter, setFilter] = useState('all');
  const [reassignModal, setReassignModal] = useState(null);
  const [selectedReviewer, setSelectedReviewer] = useState('');
  const [reassignReason, setReassignReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const filtered = filter === 'all' ? prs : prs.filter(p => p.status === filter || p.state === filter);

  const handleReassign = async () => {
    if (!selectedReviewer || !reassignModal) return;
    setSubmitting(true);
    try {
      await api.reassignPR(reassignModal.id, selectedReviewer, reassignReason);
      setReassignModal(null);
      setSelectedReviewer('');
      setReassignReason('');
      onRefresh();
    } catch (e) {
      alert(`Reassign failed: ${e.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const countByStatus = (s) => prs.filter(p => (p.status || p.state) === s).length;

  return (
    <div>
      <div className="filter-bar">
        {STATUS_FILTERS.map(s => (
          <button
            key={s}
            className={`filter-btn ${filter === s ? 'active' : ''}`}
            onClick={() => setFilter(s)}
          >
            {s === 'all' ? `All (${prs.length})` : `${s} (${countByStatus(s)})`}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="empty-state"><p>No PRs found.</p></div>
      ) : (
        <div className="pr-list">
          {filtered.map(pr => {
            const status = pr.status || pr.state || 'open';
            const linesAdded = pr.lines_added || 0;
            const linesDeleted = pr.lines_deleted || 0;
            const complexity = pr.complexity_score;

            return (
              <div key={pr.id} className="pr-item">
                <div className="pr-item-header">
                  <span className="pr-number">{pr.external_id ? `#${pr.external_id}` : `#${pr.id?.slice(0,8)}`}</span>
                  <span className="pr-title" title={pr.title}>{pr.title}</span>
                  <StatusBadge status={status} />
                </div>
                <div className="pr-item-meta">
                  <span className="pr-meta-item">📁 {pr.repo_full_name}</span>
                  <span className="pr-meta-item">👤 @{pr.author_username || pr.author}</span>
                  {linesAdded + linesDeleted > 0 && (
                    <span className="pr-meta-item">
                      <span style={{ color: 'var(--green)' }}>+{linesAdded}</span>
                      {' / '}
                      <span style={{ color: 'var(--red)' }}>-{linesDeleted}</span>
                    </span>
                  )}
                  {complexity != null && (
                    <span className="pr-meta-item">
                      complexity: {complexity.toFixed(1)}/10
                    </span>
                  )}
                  {pr.estimated_review_minutes > 0 && (
                    <span className="pr-meta-item">⏱ ~{pr.estimated_review_minutes}min</span>
                  )}
                  {(status === 'assigned' || status === 'open') && (
                    <button
                      className="btn btn-ghost"
                      style={{ padding: '2px 10px', fontSize: 11, marginLeft: 'auto' }}
                      onClick={() => {
                        setReassignModal(pr);
                        setSelectedReviewer('');
                      }}
                    >
                      ↩ Reassign
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {reassignModal && (
        <div className="modal-overlay" onClick={() => setReassignModal(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>Reassign PR</h3>
            <p style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 16 }}>
              {reassignModal.title}
            </p>
            <label>New Reviewer</label>
            <select value={selectedReviewer} onChange={e => setSelectedReviewer(e.target.value)}>
              <option value="">— Select reviewer —</option>
              {reviewers
                .filter(r => r.username !== (reassignModal.author_username || reassignModal.author))
                .map(r => (
                  <option key={r.username} value={r.username}>
                    {r.display_name || r.username} ({r.current_load ?? 0}/{r.max_load || r.max_concurrent_reviews || 3} active)
                  </option>
                ))}
            </select>
            <label>Reason (optional)</label>
            <input
              type="text"
              placeholder="e.g. Better expertise match"
              value={reassignReason}
              onChange={e => setReassignReason(e.target.value)}
            />
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setReassignModal(null)}>Cancel</button>
              <button
                className="btn btn-primary"
                onClick={handleReassign}
                disabled={!selectedReviewer || submitting}
              >
                {submitting ? 'Assigning...' : 'Reassign'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}