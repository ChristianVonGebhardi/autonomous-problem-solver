const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8001';

async function fetchJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`API error ${response.status}: ${await response.text()}`);
  }
  return response.json();
}

export const api = {
  // Dashboard
  getDashboardSummary: () => fetchJson('/api/dashboard/summary'),

  // Templates
  getTemplates: () => fetchJson('/api/templates'),
  createTemplate: (data) => fetchJson('/api/templates', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  // Golden references
  getGoldenReferences: (templateId) =>
    fetchJson(`/api/golden-references${templateId ? `?template_id=${templateId}` : ''}`),
  createGoldenReference: (data) => fetchJson('/api/golden-references', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  // Metrics
  getTimeSeries: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return fetchJson(`/api/metrics/time-series${query ? `?${query}` : ''}`);
  },
  getLatestMetrics: (templateId) =>
    fetchJson(`/api/metrics/latest${templateId ? `?template_id=${templateId}` : ''}`),

  // Alerts
  getAlerts: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return fetchJson(`/api/alerts${query ? `?${query}` : ''}`);
  },
  acknowledgeAlert: (alertId) => fetchJson(`/api/alerts/${alertId}/acknowledge`, { method: 'POST' }),

  // Inference logs
  getInferenceLogs: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return fetchJson(`/api/inference-logs${query ? `?${query}` : ''}`);
  },
  getInferenceLog: (id) => fetchJson(`/api/inference-logs/${id}`),

  // Simulation
  simulateRegression: (params) => fetchJson('/api/simulate/regression', {
    method: 'POST',
    body: JSON.stringify(params),
  }),
  triggerDetection: (templateId) => fetchJson('/api/trigger/drift-detection', {
    method: 'POST',
    body: JSON.stringify(templateId ? { template_id: templateId } : {}),
  }),
};