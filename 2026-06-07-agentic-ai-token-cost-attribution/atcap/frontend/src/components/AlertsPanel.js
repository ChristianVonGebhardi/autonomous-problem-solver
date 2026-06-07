import React, { useEffect, useState, useCallback } from 'react';
import { fetchAlerts, acknowledgeAlert, sendTestAlert, evaluateBudgets } from '../api';
import styles from './Dashboard.module.css';

export default function AlertsPanel() {
  const [alerts, setAlerts] = useState([]);
  const [showAll, setShowAll] = useState(false);
  const [loading, setLoading] = useState(true);
  const [testMsg, setTestMsg] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const a = await fetchAlerts(!showAll);
      setAlerts(a);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [showAll]);

  useEffect(() => { load(); }, [load]);

  const handleAck = async (id) => {
    await acknowledgeAlert(id);
    load();
  };

  const handleTest = async () => {
    const result = await sendTestAlert();
    setTestMsg(
      result.webhook_configured
        ? '✅ Test alert sent to Slack!'
        : '⚠️ No SLACK_WEBHOOK_URL configured — alert logged to console only'
    );
    setTimeout(() => setTestMsg(''), 5000);
  };

  const handleEvaluate = async () => {
    await evaluateBudgets();
    load();
  };

  const critical = alerts.filter(a => a.alert_level === 'critical');
  const warn = alerts.filter(a => a.alert_level === 'warn');

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Alerts</h1>
          <p className={styles.pageSubtitle}>Budget breach notifications and policy violations</p>
        </div>
        <div className={styles.headerActions}>
          <button className={styles.actionBtn} onClick={handleEvaluate}>
            Evaluate Policies
          </button>
          <button className={styles.refreshBtn} onClick={handleTest}>
            Send Test Alert
          </button>
          <button
            className={styles.refreshBtn}
            onClick={() => setShowAll(s => !s)}
          >
            {showAll ? 'Show Unacked' : 'Show All'}
          </button>
          <button className={styles.refreshBtn} onClick={load}>↻ Refresh</button>
        </div>
      </div>

      {testMsg && (
        <div style={{
          padding: '10px 16px',
          borderRadius: 8,
          background: testMsg.startsWith('✅') ? 'rgba(16,185,129,0.15)' : 'rgba(245,158,11,0.15)',
          border: `1px solid ${testMsg.startsWith('✅') ? 'rgba(16,185,129,0.4)' : 'rgba(245,158,11,0.4)'}`,
          color: testMsg.startsWith('✅') ? '#6ee7b7' : '#fcd34d',
          fontSize: 13,
        }}>
          {testMsg}
        </div>
      )}

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <div style={{
          background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)',
          borderRadius: 10, padding: '14px 20px', minWidth: 140
        }}>
          <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', marginBottom: 4 }}>Critical</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: '#fca5a5' }}>{critical.length}</div>
        </div>
        <div style={{
          background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.3)',
          borderRadius: 10, padding: '14px 20px', minWidth: 140
        }}>
          <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', marginBottom: 4 }}>Warning</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: '#fcd34d' }}>{warn.length}</div>
        </div>
        <div style={{
          background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.3)',
          borderRadius: 10, padding: '14px 20px', minWidth: 140
        }}>
          <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', marginBottom: 4 }}>Total</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: '#93c5fd' }}>{alerts.length}</div>
        </div>
      </div>

      <div className={styles.panel}>
        <div className={styles.panelTitle}>
          {showAll ? 'All Alerts' : 'Unacknowledged Alerts'}
        </div>
        {loading && <div className={styles.loading}>Loading…</div>}
        {!loading && alerts.length === 0 && (
          <div className={styles.empty}>
            {showAll ? 'No alerts on record' : 'No unacknowledged alerts 🎉'}
          </div>
        )}
        {!loading && alerts.length > 0 && (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Level</th>
                  <th>Policy</th>
                  <th>Spend</th>
                  <th>Budget</th>
                  <th>%</th>
                  <th>Notified</th>
                  <th>Time</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {alerts.map(a => (
                  <tr key={a.id}>
                    <td>
                      <span className={`${styles.badge} ${a.alert_level === 'critical' ? styles.critical : styles.warn}`}>
                        {a.alert_level === 'critical' ? '🚨 CRITICAL' : '⚠️ WARN'}
                      </span>
                    </td>
                    <td>
                      <div style={{ fontWeight: 500 }}>{a.policy_name}</div>
                      {a.message && <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{a.message}</div>}
                    </td>
                    <td style={{ color: '#fbbf24', fontWeight: 600 }}>
                      ${a.current_spend_usd.toFixed(2)}
                    </td>
                    <td>${a.budget_usd.toFixed(0)}</td>
                    <td>
                      <span style={{ color: a.alert_level === 'critical' ? '#fca5a5' : '#fcd34d', fontWeight: 700 }}>
                        {a.spend_pct.toFixed(1)}%
                      </span>
                    </td>
                    <td>
                      {a.notified_slack
                        ? <span style={{ color: '#6ee7b7' }}>✅ Slack</span>
                        : <span style={{ color: '#475569' }}>—</span>
                      }
                    </td>
                    <td style={{ fontSize: 11, color: '#64748b' }}>
                      {a.triggered_at?.slice(0, 16).replace('T', ' ')}
                    </td>
                    <td>
                      {!a.acknowledged && (
                        <button className={styles.ackBtn} onClick={() => handleAck(a.id)}>
                          Acknowledge
                        </button>
                      )}
                      {a.acknowledged && (
                        <span style={{ fontSize: 11, color: '#475569' }}>Acked</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className={styles.panel}>
        <div className={styles.panelTitle}>Slack Integration</div>
        <div style={{ fontSize: 13, color: '#94a3b8', lineHeight: 1.7 }}>
          <p>Set <code style={{ background: '#0f172a', padding: '1px 4px', borderRadius: 3 }}>SLACK_WEBHOOK_URL</code> in <code style={{ background: '#0f172a', padding: '1px 4px', borderRadius: 3 }}>backend/.env</code> to enable real-time Slack alerts.</p>
          <p style={{ marginTop: 8 }}>Alerts fire when spend exceeds warn or critical thresholds. Budget evaluation runs every 60 seconds in the background, or click "Evaluate Policies" above.</p>
          <p style={{ marginTop: 8 }}>Each alert fires at most once per hour per policy to prevent notification spam.</p>
        </div>
      </div>
    </div>
  );
}