import React, { useState } from 'react';
import { StatusBadge, ComplexityBadge } from './Badges';
import { api } from '../api';

const STATUS_FILTERS = ['all', 'open', 'assigned', 'in_review', 'completed', 'merged'];

export default function PRList({ prs, reviewers, onRefresh }) {
  const [filter, setFilter] = useState('all');
  const [reassignModal, setReassignModal] = useState(null);
  const [selectedReviewer, setSelectedReviewer] = useState('');
  const [reassignReason, setReassignReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const filtered = filter === 'all' ? prs : prs.filter(p => p.status === filter);

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

  return (
    <div>
      <div className="filter-bar">
        {STATUS_FILTERS.map(s => (
          <button
            key={s}
            className={`filter-btn ${filter === s ? 'active' : ''}`}
            onClick={() => setFilter(s)}
          >
            {s === 'all' ? `All (${prs.length})` : `${s} (${prs.filter(p => p.status === s).length})`}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="empty-state"><p>No PRs found.</p></div>
      ) : (
        <div className="pr-list">
          {filtered.map(pr => (
            <div key={pr.id} className="pr-item">
              <div className="pr-item-header">
                <span className="pr-number">#{pr.pr_number}</span>
                <span className="pr-title" title={pr.title}>{pr.title}</span>
                <StatusBadge status={pr.status} />
              </div>
              <div className="pr-item-meta">
                <span className="pr-meta-item">📁 {pr.repo_owner}/{pr.repo_name}</span>
                <span className="pr-meta-item">👤 @{pr.author}</span>
                {pr.assigned_reviewer && (
                  <span className="pr-meta-item">🔍 @{pr.assigned_reviewer}</span>
                )}
                {pr.lines_added + pr.lines_deleted > 0 && (
                  <span className="pr-meta-item">
                    <span style={{ color: 'var(--green)' }}>+{pr.lines_added}</span>
                    {' / '}
                    <span style={{ color: 'var(--red)' }}>-{pr.lines_deleted}</span>
                  </span>
                )}
                <ComplexityBadge score={pr.complexity_score} />
                {pr.estimated_minutes > 0 && (
                  <span className="pr-meta-item">⏱ ~{pr.estimated_minutes}min</span>
                )}
                {(pr.status === 'assigned' || pr.status === 'open') && (
                  <button
                    className="btn btn-ghost"
                    style={{ padding: '2px 10px', fontSize: 11, marginLeft: 'auto' }}
                    onClick={() => {
                      setReassignModal(pr);
                      setSelectedReviewer(pr.assigned_reviewer || '');
                    }}
                  >
                    ↩ Reassign
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {reassignModal && (
        <div className="modal-overlay" onClick={() => setReassignModal(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>Reassign PR #{reassignModal.pr_number}</h3>
            <p style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 16 }}>
              {reassignModal.title}
            </p>
            <label>New Reviewer</label>
            <select value={selectedReviewer} onChange={e => setSelectedReviewer(e.target.value)}>
              <option value="">— Select reviewer —</option>
              {reviewers
                .filter(r => r.username !== reassignModal.author)
                .map(r => (
                  <option key={r.username} value={r.username}>
                    {r.full_name || r.username} ({r.current_load}/{r.max_load} active)
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