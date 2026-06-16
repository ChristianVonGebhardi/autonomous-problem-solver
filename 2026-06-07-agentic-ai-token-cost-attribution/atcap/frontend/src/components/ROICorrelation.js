import React, { useEffect, useState, useCallback } from 'react';
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, BarChart, Bar
} from 'recharts';
import { fetchROI, computeROI, fetchValueEvents } from '../api';
import styles from './Dashboard.module.css';

function roiPillClass(label) {
  if (label === 'excellent') return styles.excellent;
  if (label === 'good') return styles.good;
  if (label === 'break-even') return styles.breakeven;
  if (label === 'negative') return styles.negative;
  return styles.unknown;
}

export default function ROICorrelation() {
  const [roi, setRoi] = useState([]);
  const [valueEvents, setValueEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [computing, setComputing] = useState(false);
  const [tab, setTab] = useState('roi');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, ve] = await Promise.all([fetchROI(), fetchValueEvents('30d')]);
      setRoi(r);
      setValueEvents(ve);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCompute = async () => {
    setComputing(true);
    await computeROI();
    await load();
    setComputing(false);
  };

  // Deduplicate ROI: latest record per team
  const latestRoi = Object.values(
    roi.reduce((acc, r) => {
      if (!acc[r.team] || new Date(r.period_start) > new Date(acc[r.team].period_start)) {
        acc[r.team] = r;
      }
      return acc;
    }, {})
  );

  const scatterData = latestRoi
    .filter(r => r.total_cost_usd > 0 && r.value_points > 0)
    .map(r => ({
      x: r.total_cost_usd,
      y: r.value_points,
      team: r.team,
      roi: r.roi_ratio,
    }));

  // Value events by source
  const bySource = valueEvents.reduce((acc, e) => {
    acc[e.source] = (acc[e.source] || 0) + 1;
    return acc;
  }, {});
  const sourceChart = Object.entries(bySource).map(([k, v]) => ({ source: k, count: v }));

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>ROI Correlation</h1>
          <p className={styles.pageSubtitle}>Correlate AI token spend against business value outcomes</p>
        </div>
        <div className={styles.headerActions}>
          <button
            className={styles.actionBtn}
            onClick={handleCompute}
            disabled={computing}
          >
            {computing ? 'Computing…' : 'Compute ROI'}
          </button>
          <button className={styles.refreshBtn} onClick={load}>↻ Refresh</button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 4, marginBottom: 4 }}>
        {['roi', 'value-events'].map(t => (
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
            {t === 'roi' ? 'ROI Records' : 'Value Events'}
          </button>
        ))}
      </div>

      {loading && <div className={styles.loading}>Loading…</div>}

      {!loading && tab === 'roi' && (
        <>
          {latestRoi.length === 0 ? (
            <div className={styles.panel}>
              <div className={styles.empty}>
                No ROI data yet. Click "Compute ROI" or run the demo script to seed data.
              </div>
            </div>
          ) : (
            <>
              <div className={styles.roiGrid}>
                {latestRoi.map((r, i) => (
                  <div key={i} className={styles.roiCard}>
                    <div className={styles.roiCardHeader}>
                      <span className={styles.roiTeam}>{r.team}</span>
                      <span className={`${styles.pill} ${roiPillClass(r.roi_label)}`}>
                        {r.roi_label}
                      </span>
                    </div>
                    <div className={styles.roiStat}>
                      <span>Total Cost</span>
                      <span className={styles.roiStatVal}>${r.total_cost_usd.toFixed(2)}</span>
                    </div>
                    <div className={styles.roiStat}>
                      <span>LLM Calls</span>
                      <span className={styles.roiStatVal}>{r.call_count.toLocaleString()}</span>
                    </div>
                    <div className={styles.roiStat}>
                      <span>Value Events</span>
                      <span className={styles.roiStatVal}>{r.value_events_count}</span>
                    </div>
                    <div className={styles.roiStat}>
                      <span>Value Points</span>
                      <span className={styles.roiStatVal}>{r.value_points.toFixed(1)}</span>
                    </div>
                    {r.value_usd && (
                      <div className={styles.roiStat}>
                        <span>Value ($)</span>
                        <span className={styles.roiStatVal}>${r.value_usd.toFixed(0)}</span>
                      </div>
                    )}
                    {r.roi_ratio !== null && (
                      <div className={styles.roiStat}>
                        <span>ROI Ratio</span>
                        <span className={styles.roiStatVal} style={{ color: r.roi_ratio >= 1 ? '#6ee7b7' : '#fca5a5' }}>
                          {r.roi_ratio.toFixed(1)}x
                        </span>
                      </div>
                    )}
                    {r.cost_per_value_point !== null && (
                      <div className={styles.roiStat}>
                        <span>Cost / value pt</span>
                        <span className={styles.roiStatVal}>${r.cost_per_value_point.toFixed(3)}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {scatterData.length > 1 && (
                <div className={styles.chartCard}>
                  <h3 className={styles.chartTitle}>Cost vs Value Points (by team)</h3>
                  <ResponsiveContainer width="100%" height={260}>
                    <ScatterChart>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis dataKey="x" name="Cost (USD)" tick={{ fill: '#94a3b8', fontSize: 10 }}
                        tickFormatter={v => `$${v.toFixed(2)}`} />
                      <YAxis dataKey="y" name="Value Points" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                      <Tooltip
                        cursor={{ strokeDasharray: '3 3' }}
                        contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                        formatter={(v, n) => [n === 'x' ? `$${Number(v).toFixed(2)}` : v, n === 'x' ? 'Cost' : 'Value Pts']}
                      />
                      <Scatter data={scatterData} fill="#3b82f6" />
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>
              )}
            </>
          )}
        </>
      )}

      {!loading && tab === 'value-events' && (
        <>
          {sourceChart.length > 0 && (
            <div className={styles.chartCard}>
              <h3 className={styles.chartTitle}>Value Events by Source</h3>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={sourceChart}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="source" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                  <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} />
                  <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }} />
                  <Bar dataKey="count" fill="#10b981" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          <div className={styles.panel}>
            <div className={styles.panelTitle}>Recent Value Events</div>
            {valueEvents.length === 0 ? (
              <div className={styles.empty}>No value events. Run the demo to seed data.</div>
            ) : (
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Source</th>
                      <th>Type</th>
                      <th>Team</th>
                      <th>Entity</th>
                      <th>Value Pts</th>
                      <th>Value $</th>
                      <th>Title</th>
                      <th>Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {valueEvents.slice(0, 50).map((e, i) => (
                      <tr key={i}>
                        <td>
                          <span className={`${styles.badge} ${styles.info}`}>{e.source}</span>
                        </td>
                        <td style={{ fontSize: 11, color: '#94a3b8' }}>{e.event_type}</td>
                        <td>{e.team || '—'}</td>
                        <td style={{ fontSize: 11 }}>{e.business_entity_id || '—'}</td>
                        <td style={{ color: '#6ee7b7' }}>{e.value_points.toFixed(1)}</td>
                        <td>{e.value_usd ? `$${e.value_usd.toFixed(0)}` : '—'}</td>
                        <td style={{ fontSize: 11, color: '#94a3b8', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {e.url ? (
                            <a href={e.url} target="_blank" rel="noreferrer" style={{ color: '#60a5fa' }}>
                              {e.title || e.url}
                            </a>
                          ) : e.title || '—'}
                        </td>
                        <td style={{ fontSize: 11, color: '#64748b' }}>
                          {e.timestamp?.slice(0, 16).replace('T', ' ')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}