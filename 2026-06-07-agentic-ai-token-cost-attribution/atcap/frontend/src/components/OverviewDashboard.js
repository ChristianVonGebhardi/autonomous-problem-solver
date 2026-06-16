import React, { useEffect, useState, useCallback } from 'react';
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts';
import MetricCard from './MetricCard';
import {
  fetchCostSummary, fetchCostsByTeam, fetchTimeSeries, fetchBudgets, evaluateBudgets
} from '../api';
import styles from './Dashboard.module.css';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];

function fmt(n) {
  if (n === undefined || n === null) return '$0.00';
  if (n >= 1000) return `$${(n / 1000).toFixed(1)}k`;
  if (n >= 1) return `$${n.toFixed(2)}`;
  return `$${n.toFixed(4)}`;
}

function fmtTokens(n) {
  if (!n) return '0';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

export default function OverviewDashboard() {
  const [summary, setSummary] = useState(null);
  const [teamCosts, setTeamCosts] = useState([]);
  const [timeSeries, setTimeSeries] = useState([]);
  const [budgets, setBudgets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState('30d');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, t, ts, b] = await Promise.all([
        fetchCostSummary(period),
        fetchCostsByTeam(period),
        fetchTimeSeries(period === '30d' ? '7d' : period, period === '1h' ? '1h' : '1d'),
        fetchBudgets(),
      ]);
      setSummary(s);
      setTeamCosts(t);
      setTimeSeries(ts.map(p => ({
        ...p,
        label: p.timestamp.slice(0, 16).replace('T', ' '),
      })));
      setBudgets(b);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => { load(); }, [load]);

  const handleEvaluate = async () => {
    await evaluateBudgets();
    load();
  };

  const criticalBudgets = budgets.filter(b => b.spend_pct >= b.critical_threshold_pct);
  const warnBudgets = budgets.filter(b => b.spend_pct >= b.warn_threshold_pct && b.spend_pct < b.critical_threshold_pct);

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Overview</h1>
          <p className={styles.pageSubtitle}>AI token cost attribution across all teams and features</p>
        </div>
        <div className={styles.headerActions}>
          <select
            className={styles.periodSelect}
            value={period}
            onChange={e => setPeriod(e.target.value)}
          >
            <option value="1h">Last 1 hour</option>
            <option value="24h">Last 24 hours</option>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
            <option value="mtd">Month to date</option>
          </select>
          <button className={styles.actionBtn} onClick={handleEvaluate}>
            Evaluate Budgets
          </button>
          <button className={styles.refreshBtn} onClick={load}>↻ Refresh</button>
        </div>
      </div>

      {loading && <div className={styles.loading}>Loading data…</div>}

      {(criticalBudgets.length > 0 || warnBudgets.length > 0) && (
        <div className={styles.alertBanner}>
          {criticalBudgets.map(b => (
            <div key={b.id} className={styles.alertCritical}>
              🚨 <strong>{b.name}</strong> is at {b.spend_pct.toFixed(0)}% of budget (${b.current_spend_usd.toFixed(2)} / ${b.budget_usd.toFixed(0)})
            </div>
          ))}
          {warnBudgets.map(b => (
            <div key={b.id} className={styles.alertWarn}>
              ⚠️ <strong>{b.name}</strong> is at {b.spend_pct.toFixed(0)}% of budget
            </div>
          ))}
        </div>
      )}

      {summary && (
        <div className={styles.metricsGrid}>
          <MetricCard
            title="Total Cost"
            value={fmt(summary.total_cost_usd)}
            subtitle={`${summary.call_count.toLocaleString()} LLM calls`}
            color="blue"
            icon="💸"
          />
          <MetricCard
            title="Total Tokens"
            value={fmtTokens(summary.total_tokens)}
            subtitle={`${fmtTokens(summary.prompt_tokens)} prompt + ${fmtTokens(summary.completion_tokens)} completion`}
            color="purple"
            icon="🔤"
          />
          <MetricCard
            title="Avg Cost / Call"
            value={`$${(summary.avg_cost_per_call || 0).toFixed(5)}`}
            subtitle="per LLM invocation"
            color="green"
            icon="📉"
          />
          <MetricCard
            title="Active Budgets"
            value={budgets.length}
            subtitle={`${criticalBudgets.length} critical · ${warnBudgets.length} warning`}
            color={criticalBudgets.length > 0 ? 'red' : warnBudgets.length > 0 ? 'orange' : 'green'}
            icon="🎯"
          />
        </div>
      )}

      <div className={styles.chartsRow}>
        <div className={styles.chartCard}>
          <h3 className={styles.chartTitle}>Cost Over Time</h3>
          {timeSeries.length === 0 ? (
            <div className={styles.empty}>No data for selected period</div>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={timeSeries}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="label" tick={{ fill: '#94a3b8', fontSize: 10 }} interval="preserveStartEnd" />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={v => `$${v.toFixed(2)}`} />
                <Tooltip
                  contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                  labelStyle={{ color: '#94a3b8' }}
                  formatter={v => [`$${Number(v).toFixed(4)}`, 'Cost']}
                />
                <Line type="monotone" dataKey="cost_usd" stroke="#3b82f6" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className={styles.chartCard}>
          <h3 className={styles.chartTitle}>Cost by Team</h3>
          {teamCosts.length === 0 ? (
            <div className={styles.empty}>No data</div>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie
                  data={teamCosts.slice(0, 6)}
                  dataKey="total_cost_usd"
                  nameKey="dimension"
                  cx="50%"
                  cy="50%"
                  outerRadius={90}
                  label={({ dimension, pct_of_total }) => `${dimension} (${pct_of_total}%)`}
                  labelLine={false}
                >
                  {teamCosts.slice(0, 6).map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                  formatter={v => [`$${Number(v).toFixed(4)}`, 'Cost']}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div className={styles.chartCard}>
        <h3 className={styles.chartTitle}>Cost by Team — Bar Chart</h3>
        {teamCosts.length === 0 ? (
          <div className={styles.empty}>No data</div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={teamCosts.slice(0, 8)} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={v => `$${v.toFixed(2)}`} />
              <YAxis type="category" dataKey="dimension" tick={{ fill: '#94a3b8', fontSize: 11 }} width={120} />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                formatter={v => [`$${Number(v).toFixed(4)}`, 'Cost']}
              />
              <Bar dataKey="total_cost_usd" fill="#3b82f6" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {budgets.length > 0 && (
        <div className={styles.chartCard}>
          <h3 className={styles.chartTitle}>Budget Utilisation</h3>
          <div className={styles.budgetList}>
            {budgets.map(b => {
              const pct = Math.min(b.spend_pct, 100);
              const color = pct >= b.critical_threshold_pct ? '#ef4444'
                : pct >= b.warn_threshold_pct ? '#f59e0b' : '#10b981';
              return (
                <div key={b.id} className={styles.budgetRow}>
                  <div className={styles.budgetMeta}>
                    <span className={styles.budgetName}>{b.name}</span>
                    <span className={styles.budgetPct} style={{ color }}>
                      {b.spend_pct.toFixed(1)}%
                    </span>
                  </div>
                  <div className={styles.budgetBarBg}>
                    <div
                      className={styles.budgetBar}
                      style={{ width: `${pct}%`, background: color }}
                    />
                  </div>
                  <div className={styles.budgetAmounts}>
                    <span>${b.current_spend_usd.toFixed(2)}</span>
                    <span className={styles.budgetTotal}>/ ${b.budget_usd.toFixed(0)} {b.period}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}