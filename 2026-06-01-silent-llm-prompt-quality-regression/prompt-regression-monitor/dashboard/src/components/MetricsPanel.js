import React, { useState, useEffect, useCallback } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { format } from 'date-fns';
import { api } from '../api';

const METRIC_COLORS = [
  '#6366f1', '#10b981', '#f59e0b', '#ef4444',
  '#8b5cf6', '#06b6d4', '#f97316', '#ec4899',
];

const HOUR_OPTIONS = [
  { value: 6, label: '6h' },
  { value: 12, label: '12h' },
  { value: 24, label: '24h' },
  { value: 48, label: '48h' },
  { value: 168, label: '7d' },
];

export default function MetricsPanel() {
  const [series, setSeries] = useState([]);
  const [latestMetrics, setLatestMetrics] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState('');
  const [selectedMetric, setSelectedMetric] = useState('');
  const [hours, setHours] = useState(24);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchTemplates = useCallback(async () => {
    try {
      const data = await api.getTemplates();
      setTemplates(data);
    } catch (e) {
      // ignore
    }
  }, []);

  const fetchMetrics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = { hours };
      if (selectedTemplate) params.template_id = selectedTemplate;
      if (selectedMetric) params.metric_name = selectedMetric;

      const [ts, latest] = await Promise.all([
        api.getTimeSeries(params),
        api.getLatestMetrics(selectedTemplate || undefined),
      ]);
      setSeries(ts);
      setLatestMetrics(latest);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [selectedTemplate, selectedMetric, hours]);

  useEffect(() => { fetchTemplates(); }, [fetchTemplates]);
  useEffect(() => { fetchMetrics(); }, [fetchMetrics]);

  // Build chart data from series
  const chartData = buildChartData(series);
  const metricNames = [...new Set(series.map(s => s.metric_name))];

  return (
    <div>
      <div style={styles.header}>
        <h1 style={styles.title}>Quality Metrics</h1>
        <button style={styles.refreshBtn} onClick={fetchMetrics}>↻ Refresh</button>
      </div>

      {/* Filters */}
      <div style={styles.filters}>
        <select
          style={styles.select}
          value={selectedTemplate}
          onChange={e => setSelectedTemplate(e.target.value)}
        >
          <option value="">All templates</option>
          {templates.map(t => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>

        <select
          style={styles.select}
          value={selectedMetric}
          onChange={e => setSelectedMetric(e.target.value)}
        >
          <option value="">All metrics</option>
          {metricNames.map(m => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>

        <div style={styles.timeButtons}>
          {HOUR_OPTIONS.map(opt => (
            <button
              key={opt.value}
              style={{
                ...styles.timeBtn,
                ...(hours === opt.value ? styles.timeBtnActive : {}),
              }}
              onClick={() => setHours(opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {error && <div style={styles.errorBox}>{error}</div>}

      {/* Time series chart */}
      <div style={styles.chartCard}>
        <h3 style={styles.cardTitle}>Quality Score Over Time</h3>
        {loading ? (
          <div style={styles.loading}>Loading…</div>
        ) : chartData.length === 0 ? (
          <div style={styles.empty}>
            No data yet. Send requests through the proxy or use the Simulate panel to generate data.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={340}>
            <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis
                dataKey="time"
                tick={{ fill: '#64748b', fontSize: 11 }}
                tickFormatter={v => format(new Date(v), 'HH:mm')}
                stroke="#334155"
              />
              <YAxis
                tick={{ fill: '#64748b', fontSize: 11 }}
                domain={[0, 1]}
                tickFormatter={v => `${(v * 100).toFixed(0)}%`}
                stroke="#334155"
              />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }}
                labelStyle={{ color: '#94a3b8', fontSize: '12px' }}
                formatter={(value, name) => [`${(value * 100).toFixed(1)}%`, name]}
                labelFormatter={v => format(new Date(v), 'MMM d, HH:mm')}
              />
              <Legend
                wrapperStyle={{ fontSize: '12px', color: '#94a3b8' }}
              />
              <ReferenceLine y={0.7} stroke="#f59e0b" strokeDasharray="6 3" label={{ value: 'Warning', fill: '#f59e0b', fontSize: 10 }} />
              {series.map((s, i) => (
                <Line
                  key={`${s.metric_name}-${s.template_name}`}
                  type="monotone"
                  dataKey={`${s.metric_name}__${s.template_name}`}
                  name={`${s.metric_name} (${s.template_name})`}
                  stroke={METRIC_COLORS[i % METRIC_COLORS.length]}
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Latest metrics table */}
      <div style={styles.chartCard}>
        <h3 style={styles.cardTitle}>Latest Metrics (24h Average)</h3>
        {latestMetrics.length === 0 ? (
          <div style={styles.empty}>No metrics available yet.</div>
        ) : (
          <table style={styles.table}>
            <thead>
              <tr>
                {['Template', 'Metric', 'Avg Score', 'Min', 'Max', 'Count'].map(h => (
                  <th key={h} style={styles.th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {latestMetrics.map((m, i) => (
                <tr key={i} style={i % 2 === 0 ? {} : styles.trAlt}>
                  <td style={styles.td}>{m.template_name}</td>
                  <td style={{ ...styles.td, fontFamily: 'monospace', fontSize: '12px' }}>
                    {m.metric_name}
                  </td>
                  <td style={styles.td}>
                    <ScoreBar score={m.avg_score} />
                  </td>
                  <td style={{ ...styles.td, color: '#94a3b8' }}>
                    {(m.min_score * 100).toFixed(1)}%
                  </td>
                  <td style={{ ...styles.td, color: '#94a3b8' }}>
                    {(m.max_score * 100).toFixed(1)}%
                  </td>
                  <td style={{ ...styles.td, color: '#64748b' }}>{m.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function ScoreBar({ score }) {
  const pct = Math.round(score * 100);
  const color = pct >= 80 ? '#10b981' : pct >= 60 ? '#f59e0b' : '#ef4444';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <div style={{ flex: 1, background: '#334155', borderRadius: '4px', height: '6px', minWidth: '60px' }}>
        <div style={{ width: `${pct}%`, background: color, borderRadius: '4px', height: '100%' }} />
      </div>
      <span style={{ fontSize: '12px', color, fontWeight: '600', minWidth: '38px' }}>{pct}%</span>
    </div>
  );
}

function buildChartData(series) {
  if (!series || series.length === 0) return [];

  const timeSet = new Set();
  series.forEach(s => s.points.forEach(p => timeSet.add(p.timestamp)));
  const times = [...timeSet].sort();

  return times.map(time => {
    const row = { time };
    series.forEach(s => {
      const pt = s.points.find(p => p.timestamp === time);
      const key = `${s.metric_name}__${s.template_name}`;
      row[key] = pt ? pt.value : null;
    });
    return row;
  });
}

const styles = {
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '20px',
  },
  title: { fontSize: '24px', fontWeight: '700', color: '#f1f5f9' },
  refreshBtn: {
    background: '#334155',
    border: '1px solid #475569',
    color: '#94a3b8',
    borderRadius: '8px',
    padding: '8px 14px',
    cursor: 'pointer',
    fontSize: '13px',
  },
  filters: {
    display: 'flex',
    gap: '12px',
    marginBottom: '20px',
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  select: {
    background: '#1e293b',
    border: '1px solid #334155',
    color: '#e2e8f0',
    borderRadius: '8px',
    padding: '8px 12px',
    fontSize: '13px',
    cursor: 'pointer',
  },
  timeButtons: { display: 'flex', gap: '4px' },
  timeBtn: {
    background: '#1e293b',
    border: '1px solid #334155',
    color: '#64748b',
    borderRadius: '6px',
    padding: '6px 10px',
    fontSize: '12px',
    cursor: 'pointer',
  },
  timeBtnActive: {
    background: '#6366f1',
    border: '1px solid #6366f1',
    color: '#fff',
  },
  chartCard: {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: '12px',
    padding: '20px',
    marginBottom: '20px',
  },
  cardTitle: {
    fontSize: '14px',
    fontWeight: '600',
    color: '#94a3b8',
    marginBottom: '16px',
  },
  loading: { color: '#64748b', padding: '20px', textAlign: 'center' },
  empty: {
    color: '#64748b',
    padding: '32px',
    textAlign: 'center',
    fontSize: '14px',
  },
  errorBox: {
    background: '#1e293b',
    border: '1px solid #ef4444',
    borderRadius: '8px',
    padding: '12px 16px',
    color: '#f87171',
    marginBottom: '16px',
    fontSize: '13px',
  },
  table: { width: '100%', borderCollapse: 'collapse' },
  th: {
    textAlign: 'left',
    color: '#64748b',
    fontSize: '11px',
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    padding: '8px 12px',
    borderBottom: '1px solid #334155',
  },
  td: {
    padding: '10px 12px',
    fontSize: '13px',
    color: '#e2e8f0',
    borderBottom: '1px solid #1e293b',
  },
  trAlt: { background: '#0f172a22' },
};