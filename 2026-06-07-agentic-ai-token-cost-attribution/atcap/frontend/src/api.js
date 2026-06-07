import axios from 'axios';

const API_BASE = process.env.REACT_APP_API_URL
  ? `${process.env.REACT_APP_API_URL}/api/v1`
  : '/api/v1';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
});

export const fetchCostSummary = (period = '30d', team = null, feature = null) => {
  const params = { period };
  if (team) params.team = team;
  if (feature) params.feature = feature;
  return api.get('/costs/summary', { params }).then(r => r.data);
};

export const fetchCostsByTeam = (period = '30d') =>
  api.get('/costs/by-team', { params: { period } }).then(r => r.data);

export const fetchCostsByFeature = (period = '30d', team = null) => {
  const params = { period };
  if (team) params.team = team;
  return api.get('/costs/by-feature', { params }).then(r => r.data);
};

export const fetchCostsByModel = (period = '30d') =>
  api.get('/costs/by-model', { params: { period } }).then(r => r.data);

export const fetchTimeSeries = (period = '7d', granularity = '1h', team = null) => {
  const params = { period, granularity };
  if (team) params.team = team;
  return api.get('/costs/timeseries', { params }).then(r => r.data);
};

export const fetchTopEvents = (period = '24h', limit = 20) =>
  api.get('/costs/top-events', { params: { period, limit } }).then(r => r.data);

export const fetchBudgets = () =>
  api.get('/budgets').then(r => r.data);

export const createBudget = (data) =>
  api.post('/budgets', data).then(r => r.data);

export const deleteBudget = (id) =>
  api.delete(`/budgets/${id}`).then(r => r.data);

export const fetchAlerts = (unacknowledgedOnly = true) =>
  api.get('/alerts', { params: { unacknowledged_only: unacknowledgedOnly } }).then(r => r.data);

export const acknowledgeAlert = (id) =>
  api.post(`/alerts/${id}/acknowledge`).then(r => r.data);

export const evaluateBudgets = () =>
  api.post('/budgets/evaluate').then(r => r.data);

export const fetchROI = () =>
  api.get('/roi').then(r => r.data);

export const computeROI = () =>
  api.post('/roi/compute').then(r => r.data);

export const fetchValueEvents = (period = '30d', team = null) => {
  const params = { period };
  if (team) params.team = team;
  return api.get('/value-events', { params }).then(r => r.data);
};

export const fetchPricing = () =>
  api.get('/pricing').then(r => r.data);

export const sendTestAlert = () =>
  api.post('/alerts/test').then(r => r.data);