const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8085';

async function fetchJSON(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  return res.json();
}

export const api = {
  getMetrics: () => fetchJSON('/api/metrics'),
  getReviewers: () => fetchJSON('/api/reviewers'),
  getReviewerStats: () => fetchJSON('/api/reviewers/stats'),
  getPRs: (status = '') => fetchJSON(`/api/prs${status ? `?status=${status}` : ''}`),
  getQueue: () => fetchJSON('/api/prs/queue'),
  getPR: (id) => fetchJSON(`/api/prs/${id}`),
  getEvents: () => fetchJSON('/api/events'),
  reassignPR: (id, reviewer, reason) =>
    fetchJSON(`/api/prs/${id}/reassign`, {
      method: 'POST',
      body: JSON.stringify({ reviewer, reason }),
    }),
};