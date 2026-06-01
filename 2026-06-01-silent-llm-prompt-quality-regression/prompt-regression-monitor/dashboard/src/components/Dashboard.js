import React from 'react';
import { format } from 'date-fns';

const SEVERITY_COLOR = {
  critical: '#ef4444',
  error: '#f97316',
  warning: '#f59e0b',
};

const TREND_INFO = {
  stable: { icon: '→', color: '#10b981', label: 'Stable' },
  improving: { icon: '↑', color: '#10b981', label: 'Improving' },
  degrading: { icon: '↓', color: '#ef4444', label: 'Degrading' },
};

export default function Dashboard({ summary, error, onRefresh }) {
  if (error) {
    return (
      <div>
        <PageHeader title="Dashboard" onRefresh={onRefresh} />
        <div style={styles.errorBox}>
          <p style={{ fontWeight: '600', marginBottom: '8px' }}>⚠️ Could not connect to API</p>
          <p style={{ fontSize: '13px', color: '#94a3b8' }}>{error}</p>
          <p style={{ fontSize: '13px', color: '#64748b', marginTop: '8px' }}>
            Make sure the backend API is running at{' '}
            <code>{process.env.REACT_APP_API_URL || 'http://localhost:8001'}</code>
          </p>
        </div>
      </div>
    );
  }

  if (!summary) {
    return (
      <div>
        <PageHeader title="Dashboard" onRefresh={onRefresh} />
        <div style={styles.loading}>Loading…</div>
      </div>
    );
  }

  const trend = TREND_INFO[summary.quality_trend] || TREND_INFO.stable;

  return (
    <div>
      <PageHeader title="Dashboard" onRefresh={onRefresh} />

      {/* KPI cards */}
      <div style={styles.kpiGrid}>
        <KpiCard
          label="Inferences (24h)"
          value={summary.total_inferences.toLocaleString()}
          icon="🔁"
          color="#6366f1"
        />
        <KpiCard
          label="Templates Monitored"
          value={summary.templates_monitored}
          icon="🗂️"
          color="#8b5cf6"
        />
        <KpiCard
          label="Active Alerts"
          value={summary.active_alerts}
          icon="🚨"
          color={summary.active_alerts > 0 ? '#ef4444' : '#10b981'}
        />
        <KpiCard
          label="Avg Quality Score"
          value={summary.avg_quality_score != null
            ? `${(summary.avg_quality_score * 100).toFixed(1)}%`
            : 'N/A'}
          icon="⭐"
          color="#f59e0b"
          sub={
            <span style={{ color: trend.color, fontWeight: '600' }}>
              {trend.icon} {trend.label}
            </span>
          }
        />
      </div>

      {/* Recent Alerts */}
      <section style={styles.section}>
        <h2 style={styles.sectionTitle}>Recent Alerts</h2>
        {summary.recent_alerts.length === 0 ? (
          <div style={styles.empty}>✅ No alerts in the last 24 hours</div>
        ) : (
          <div style={styles.alertList}>
            {summary.recent_alerts.map(alert => (
              <AlertRow key={alert.id} alert={alert} />
            ))}
          </div>
        )}
      </section>

      {/* Getting started */}
      <section style={styles.section}>
        <h2 style={styles.sectionTitle}>Quick Start</h2>
        <div style={styles.quickStart}>
          <Step n="1" title="Point your OpenAI client at the proxy">
            <code style={styles.code}>
              base_url="http://localhost:8000/v1"
            </code>
          </Step>
          <Step n="2" title="Tag requests with a template name">
            <code style={styles.code}>
              headers={'{'}'"X-Prompt-Template": "my-chatbot"'{'}'} 
            </code>
          </Step>
          <Step n="3" title="Add golden references via the API or Templates panel">
            <code style={styles.code}>
              POST /api/golden-references
            </code>
          </Step>
          <Step n="4" title="Simulate a regression to see detection in action">
            Go to the <strong>Simulate</strong> tab to inject synthetic degraded scores.
          </Step>
        </div>
      </section>
    </div>
  );
}

function PageHeader({ title, onRefresh }) {
  return (
    <div style={styles.header}>
      <h1 style={styles.title}>{title}</h1>
      <button style={styles.refreshBtn} onClick={onRefresh}>↻ Refresh</button>
    </div>
  );
}

function KpiCard({ label, value, icon, color, sub }) {
  return (
    <div style={{ ...styles.kpiCard, borderTop: `3px solid ${color}` }}>
      <div style={styles.kpiIcon}>{icon}</div>
      <div>
        <div style={styles.kpiValue}>{value}</div>
        <div style={styles.kpiLabel}>{label}</div>
        {sub && <div style={{ marginTop: '4px', fontSize: '12px' }}>{sub}</div>}
      </div>
    </div>
  );
}

function AlertRow({ alert }) {
  const color = SEVERITY_COLOR[alert.severity] || '#f59e0b';
  return (
    <div style={styles.alertRow}>
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
      <div style={{ flex: 1 }}>
        <span style={{ fontWeight: '600', color: '#f1f5f9' }}>
          {alert.template_name || 'unknown'}
        </span>
        <span style={{ color: '#64748b', margin: '0 8px' }}>›</span>
        <span style={{ color: '#94a3b8' }}>{alert.metric_name}</span>
      </div>
      <span style={{ fontSize: '12px', color: '#64748b' }}>
        {format(new Date(alert.created_at), 'MMM d, HH:mm')}
      </span>
      {alert.acknowledged && (
        <span style={{ fontSize: '11px', color: '#10b981', marginLeft: '8px' }}>✓ ACK</span>
      )}
    </div>
  );
}

function Step({ n, title, children }) {
  return (
    <div style={styles.step}>
      <div style={styles.stepNum}>{n}</div>
      <div>
        <div style={{ fontWeight: '600', marginBottom: '6px', color: '#f1f5f9' }}>{title}</div>
        <div style={{ color: '#94a3b8', fontSize: '13px' }}>{children}</div>
      </div>
    </div>
  );
}

const styles = {
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '24px',
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
  kpiGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
    gap: '16px',
    marginBottom: '32px',
  },
  kpiCard: {
    background: '#1e293b',
    borderRadius: '12px',
    padding: '20px',
    display: 'flex',
    alignItems: 'flex-start',
    gap: '14px',
    border: '1px solid #334155',
  },
  kpiIcon: { fontSize: '28px', marginTop: '2px' },
  kpiValue: { fontSize: '28px', fontWeight: '700', color: '#f1f5f9', lineHeight: 1 },
  kpiLabel: { fontSize: '12px', color: '#64748b', marginTop: '4px' },
  section: { marginBottom: '32px' },
  sectionTitle: {
    fontSize: '16px',
    fontWeight: '700',
    color: '#f1f5f9',
    marginBottom: '12px',
    borderBottom: '1px solid #334155',
    paddingBottom: '8px',
  },
  empty: {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: '10px',
    padding: '20px',
    color: '#64748b',
    textAlign: 'center',
  },
  alertList: { display: 'flex', flexDirection: 'column', gap: '8px' },
  alertRow: {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: '8px',
    padding: '12px 16px',
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  severityBadge: {
    fontSize: '11px',
    fontWeight: '700',
    padding: '2px 8px',
    borderRadius: '6px',
    whiteSpace: 'nowrap',
  },
  errorBox: {
    background: '#1e293b',
    border: '1px solid #ef4444',
    borderRadius: '12px',
    padding: '24px',
    color: '#f87171',
  },
  loading: { color: '#64748b', padding: '20px' },
  quickStart: { display: 'flex', flexDirection: 'column', gap: '12px' },
  step: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '14px',
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: '10px',
    padding: '16px',
  },
  stepNum: {
    width: '28px',
    height: '28px',
    borderRadius: '50%',
    background: '#6366f1',
    color: '#fff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '14px',
    fontWeight: '700',
    flexShrink: 0,
  },
  code: {
    background: '#0f172a',
    border: '1px solid #334155',
    borderRadius: '6px',
    padding: '6px 10px',
    fontSize: '12px',
    color: '#7dd3fc',
    display: 'inline-block',
    fontFamily: 'monospace',
  },
};