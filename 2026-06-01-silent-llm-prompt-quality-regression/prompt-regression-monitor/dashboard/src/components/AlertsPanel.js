import React, { useState, useEffect, useCallback } from 'react';
import { format } from 'date-fns';
import { api } from '../api';

const SEVERITY_COLOR = {
  critical: '#ef4444',
  error: '#f97316',
  warning: '#f59e0b',
};

export default function AlertsPanel({ onAcknowledge }) {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [filterAck, setFilterAck] = useState(false);
  const [expanded, setExpanded] = useState(null);

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = { hours: 48 };
      if (filterAck !== null && filterAck !== '') {
        params.acknowledged = filterAck;
      }
      const data = await api.getAlerts(params);
      setAlerts(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [filterAck]);

  useEffect(() => { fetchAlerts(); }, [fetchAlerts]);

  const handleAcknowledge = async (alertId) => {
    try {
      await api.acknowledgeAlert(alertId);
      await fetchAlerts();
      if (onAcknowledge) onAcknowledge();
    } catch (e) {
      alert('Failed to acknowledge: ' + e.message);
    }
  };

  const unacked = alerts.filter(a => !a.acknowledged);
  const acked = alerts.filter(a => a.acknowledged);

  return (
    <div>
      <div style={styles.header}>
        <h1 style={styles.title}>
          Drift Alerts
          {unacked.length > 0 && (
            <span style={styles.countBadge}>{unacked.length} active</span>
          )}
        </h1>
        <button style={styles.refreshBtn} onClick={fetchAlerts}>↻ Refresh</button>
      </div>

      {error && <div style={styles.errorBox}>{error}</div>}

      {loading ? (
        <div style={styles.loading}>Loading…</div>
      ) : alerts.length === 0 ? (
        <div style={styles.empty}>
          <div style={{ fontSize: '32px', marginBottom: '12px' }}>✅</div>
          No alerts in the last 48 hours. Quality looks good!
        </div>
      ) : (
        <div>
          {/* Active alerts */}
          {unacked.length > 0 && (
            <section style={styles.section}>
              <h2 style={styles.sectionTitle}>Active ({unacked.length})</h2>
              <div style={styles.alertList}>
                {unacked.map(alert => (
                  <AlertCard
                    key={alert.id}
                    alert={alert}
                    expanded={expanded === alert.id}
                    onToggle={() => setExpanded(expanded === alert.id ? null : alert.id)}
                    onAcknowledge={() => handleAcknowledge(alert.id)}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Acknowledged */}
          {acked.length > 0 && (
            <section style={styles.section}>
              <h2 style={{ ...styles.sectionTitle, color: '#64748b' }}>
                Acknowledged ({acked.length})
              </h2>
              <div style={styles.alertList}>
                {acked.map(alert => (
                  <AlertCard
                    key={alert.id}
                    alert={alert}
                    expanded={expanded === alert.id}
                    onToggle={() => setExpanded(expanded === alert.id ? null : alert.id)}
                    dimmed
                  />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}

function AlertCard({ alert, expanded, onToggle, onAcknowledge, dimmed }) {
  const color = SEVERITY_COLOR[alert.severity] || '#f59e0b';
  const baseline = alert.baseline_mean;
  const current = alert.current_mean;
  const deltaPct = baseline ? ((current - baseline) / baseline * 100) : null;

  return (
    <div
      style={{
        ...styles.alertCard,
        opacity: dimmed ? 0.6 : 1,
        borderLeft: `4px solid ${color}`,
      }}
    >
      {/* Header row */}
      <div style={styles.alertHeader} onClick={onToggle}>
        <div style={styles.alertHeaderLeft}>
          <span
            style={{
              ...styles.severityBadge,
              background: color + '22',
              color,
              border: `1px solid ${color}55`,
            }}
          >
            {alert.severity.toUpperCase()}
          </span>
          <div>
            <span style={styles.templateName}>{alert.template_name || 'unknown'}</span>
            <span style={{ color: '#475569', margin: '0 8px' }}>›</span>
            <span style={styles.metricName}>{alert.metric_name}</span>
          </div>
        </div>
        <div style={styles.alertHeaderRight}>
          {deltaPct !== null && (
            <span style={{ color: '#ef4444', fontWeight: '600', fontSize: '14px' }}>
              {deltaPct.toFixed(1)}%
            </span>
          )}
          <span style={styles.timeStamp}>
            {format(new Date(alert.created_at), 'MMM d, HH:mm')}
          </span>
          <span style={{ color: '#475569', fontSize: '12px' }}>{expanded ? '▲' : '▼'}</span>
        </div>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div style={styles.alertDetails}>
          <div style={styles.statsGrid}>
            <Stat label="Baseline Mean" value={baseline?.toFixed(4)} />
            <Stat label="Current Mean" value={current?.toFixed(4)} />
            <Stat
              label="Change"
              value={deltaPct != null ? `${deltaPct.toFixed(1)}%` : 'N/A'}
              valueColor={deltaPct < 0 ? '#ef4444' : '#10b981'}
            />
            <Stat label="P-value" value={alert.p_value?.toFixed(4)} />
            <Stat label="CUSUM stat" value={alert.cusum_stat?.toFixed(4)} />
            <Stat label="Detector" value={alert.detector_type} />
          </div>

          {alert.evidence && (
            <div style={styles.evidenceBox}>
              <div style={styles.evidenceTitle}>Evidence</div>
              <pre style={styles.evidencePre}>
                {JSON.stringify(alert.evidence, null, 2)}
              </pre>
            </div>
          )}

          {!alert.acknowledged && onAcknowledge && (
            <button style={styles.ackBtn} onClick={onAcknowledge}>
              ✓ Acknowledge Alert
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, valueColor }) {
  return (
    <div style={styles.stat}>
      <div style={styles.statLabel}>{label}</div>
      <div style={{ ...styles.statValue, color: valueColor || '#f1f5f9' }}>
        {value ?? 'N/A'}
      </div>
    </div>
  );
}

const styles = {
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '20px',
  },
  title: {
    fontSize: '24px',
    fontWeight: '700',
    color: '#f1f5f9',
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  countBadge: {
    background: '#ef444422',
    color: '#ef4444',
    border: '1px solid #ef444455',
    borderRadius: '10px',
    padding: '2px 10px',
    fontSize: '13px',
    fontWeight: '600',
  },
  refreshBtn: {
    background: '#334155',
    border: '1px solid #475569',
    color: '#94a3b8',
    borderRadius: '8px',
    padding: '8px 14px',
    cursor: 'pointer',
    fontSize: '13px',
  },
  section: { marginBottom: '24px' },
  sectionTitle: {
    fontSize: '14px',
    fontWeight: '600',
    color: '#94a3b8',
    marginBottom: '10px',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  alertList: { display: 'flex', flexDirection: 'column', gap: '8px' },
  alertCard: {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: '10px',
    overflow: 'hidden',
  },
  alertHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '14px 16px',
    cursor: 'pointer',
    gap: '12px',
  },
  alertHeaderLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    flex: 1,
  },
  alertHeaderRight: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  severityBadge: {
    fontSize: '11px',
    fontWeight: '700',
    padding: '3px 8px',
    borderRadius: '6px',
    whiteSpace: 'nowrap',
  },
  templateName: { fontWeight: '600', color: '#f1f5f9', fontSize: '14px' },
  metricName: { color: '#94a3b8', fontSize: '13px', fontFamily: 'monospace' },
  timeStamp: { fontSize: '12px', color: '#64748b' },
  alertDetails: {
    borderTop: '1px solid #334155',
    padding: '16px',
  },
  statsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
    gap: '12px',
    marginBottom: '16px',
  },
  stat: {
    background: '#0f172a',
    borderRadius: '8px',
    padding: '10px 14px',
  },
  statLabel: { fontSize: '11px', color: '#64748b', marginBottom: '4px' },
  statValue: { fontSize: '16px', fontWeight: '600' },
  evidenceBox: {
    background: '#0f172a',
    borderRadius: '8px',
    padding: '12px',
    marginBottom: '16px',
  },
  evidenceTitle: { fontSize: '11px', color: '#64748b', marginBottom: '8px', fontWeight: '600' },
  evidencePre: {
    fontSize: '11px',
    color: '#94a3b8',
    overflow: 'auto',
    maxHeight: '200px',
    fontFamily: 'monospace',
    lineHeight: '1.5',
  },
  ackBtn: {
    background: '#10b981',
    border: 'none',
    color: '#fff',
    borderRadius: '8px',
    padding: '9px 18px',
    cursor: 'pointer',
    fontSize: '13px',
    fontWeight: '600',
  },
  loading: { color: '#64748b', padding: '20px' },
  empty: {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: '12px',
    padding: '48px',
    textAlign: 'center',
    color: '#64748b',
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
};