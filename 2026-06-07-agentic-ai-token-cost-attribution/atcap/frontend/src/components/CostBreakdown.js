import React, { useEffect, useState, useCallback } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, LineChart, Line
} from 'recharts';
import {
  fetchCostsByTeam, fetchCostsByFeature, fetchCostsByModel,
  fetchTimeSeries, fetchTopEvents
} from '../api';
import styles from './Dashboard.module.css';

const TABS = ['by-team', 'by-feature', 'by-model', 'timeseries', 'top-events'];
const TAB_LABELS = {
  'by-team': 'By Team',
  'by-feature': 'By Feature',
  'by-model': 'By Model',
  'timeseries': 'Time Series',
  'top-events': 'Top Events',
};

export default function CostBreakdown() {
  const [tab, setTab] = useState('by-team');
  const [period, setPeriod] = useState('30d');
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [teamFilter, setTeamFilter] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      let d;
      if (tab === 'by-team') d = await fetchCostsByTeam(period);
      else if (tab === 'by-feature') d = await fetchCostsByFeature(period, teamFilter || null);
      else if (tab === 'by-model') d = await fetchCostsByModel(period);
      else if (tab === 'timeseries') {
        const gran = period === '1h' ? '1h' : period === '24h' ? '1h' : '1d';
        d = await fetchTimeSeries(period, gran);
        d = d.map(p => ({ ...p, label: p.timestamp.slice(0, 10) }));
      }
      else if (tab === 'top-events') d = await fetchTopEvents(period, 30);
      setData(d || []);
    } catch (e) {
      console.error(e);
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [tab, period, teamFilter]);

  useEffect(() => { load(); }, [load]);

  const isTimeSeries = tab === 'timeseries';
  const isTopEvents = tab === 'top-events';
  const isDimensional = ['by-team', 'by-feature', 'by-model'].includes(tab);

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Cost Breakdown</h1>
          <p className={styles.pageSubtitle}>Drill into cost by team, feature, model, or workflow</p>
        </div>
        <div className={styles.headerActions}>
          {tab === 'by-feature' && (
            <input
              className={styles.input}
              placeholder="Filter by team..."
              value={teamFilter}
              onChange={e => setTeamFilter(e.target.value)}
              style={{ width: 160 }}
            />
          )}
          <select
            className={styles.periodSelect}
            value={period}
            onChange={e => setPeriod(e.target.value)}
          >
            <option value="1h">Last 1 hour</option>
            <option value="24h">Last 24 hours</option>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
          </select>
          <button className={styles.refreshBtn} onClick={load}>↻ Refresh</button>
        </div>
      </div>

      <div className={styles.panel}>
        <div style={{ display: 'flex', gap: 4, marginBottom: 20, flexWrap: 'wrap' }}>
          {TABS.map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              style={{
                padding: '6px 14px',
                borderRadius: 6,
                border: 'none',
                fontSize: 13,
                cursor: 'pointer',
                background: tab === t ? '#1d4ed8' : '#334155',
                color: tab === t ? '#fff' : '#94a3b8',
                fontWeight: tab === t ? 600 : 400,
              }}
            >
              {TAB_LABELS[t]}
            </button>
          ))}
        </div>

        {loading && <div className={styles.loading}>Loading…</div>}
        {!loading && data.length === 0 && <div className={styles.empty}>No data for this period</div>}

        {!loading && isDimensional && data.length > 0 && (
          <>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={data.slice(0, 10)} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={v => `$${v.toFixed(3)}`} />
                <YAxis type="category" dataKey="dimension" tick={{ fill: '#94a3b8', fontSize: 11 }} width={160} />
                <Tooltip
                  contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                  formatter={v => [`$${Number(v).toFixed(4)}`, 'Cost']}
                />
                <Bar dataKey="total_cost_usd" fill="#3b82f6" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>

            <div style={{ marginTop: 20 }} className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>{tab.replace('by-', '').toUpperCase()}</th>
                    <th>Total Cost</th>
                    <th>Tokens</th>
                    <th>Calls</th>
                    <th>% of Total</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((row, i) => (
                    <tr key={i}>
                      <td>{row.dimension}</td>
                      <td>${row.total_cost_usd.toFixed(4)}</td>
                      <td>{row.total_tokens.toLocaleString()}</td>
                      <td>{row.call_count.toLocaleString()}</td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div style={{
                            background: '#334155', borderRadius: 3, height: 6,
                            width: 60, overflow: 'hidden', flexShrink: 0
                          }}>
                            <div style={{
                              width: `${row.pct_of_total}%`, height: '100%',
                              background: '#3b82f6', borderRadius: 3
                            }} />
                          </div>
                          {row.pct_of_total.toFixed(1)}%
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {!loading && isTimeSeries && data.length > 0 && (
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="label" tick={{ fill: '#94a3b8', fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={v => `$${v.toFixed(2)}`} />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                formatter={v => [`$${Number(v).toFixed(4)}`, 'Cost']}
              />
              <Line type="monotone" dataKey="cost_usd" stroke="#3b82f6" dot={false} strokeWidth={2} name="Cost" />
            </LineChart>
          </ResponsiveContainer>
        )}

        {!loading && isTopEvents && data.length > 0 && (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Team</th>
                  <th>Feature</th>
                  <th>Model</th>
                  <th>Cost</th>
                  <th>Tokens</th>
                  <th>Latency</th>
                  <th>Entity</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {data.map((e, i) => (
                  <tr key={i}>
                    <td>{e.team}</td>
                    <td>{e.feature}</td>
                    <td style={{ fontSize: 11, color: '#94a3b8' }}>{e.model}</td>
                    <td style={{ color: '#fbbf24', fontWeight: 600 }}>${(e.total_cost_usd || 0).toFixed(4)}</td>
                    <td>{(e.total_tokens || 0).toLocaleString()}</td>
                    <td>{e.latency_ms ? `${e.latency_ms}ms` : '—'}</td>
                    <td style={{ fontSize: 11 }}>{e.business_entity_id || '—'}</td>
                    <td style={{ fontSize: 11, color: '#64748b' }}>{e.timestamp?.slice(0, 16).replace('T', ' ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}