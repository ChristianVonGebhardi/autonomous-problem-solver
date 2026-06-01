import React, { useState, useEffect, useCallback } from 'react';
import { api } from './api';
import Dashboard from './components/Dashboard';
import AlertsPanel from './components/AlertsPanel';
import MetricsPanel from './components/MetricsPanel';
import InferenceLogsPanel from './components/InferenceLogsPanel';
import TemplatesPanel from './components/TemplatesPanel';
import SimulationPanel from './components/SimulationPanel';

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', icon: '📊' },
  { id: 'metrics', label: 'Metrics', icon: '📈' },
  { id: 'alerts', label: 'Alerts', icon: '🚨' },
  { id: 'logs', label: 'Inference Logs', icon: '📋' },
  { id: 'templates', label: 'Templates', icon: '🗂️' },
  { id: 'simulate', label: 'Simulate', icon: '🧪' },
];

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [summary, setSummary] = useState(null);
  const [summaryError, setSummaryError] = useState(null);

  const fetchSummary = useCallback(async () => {
    try {
      const data = await api.getDashboardSummary();
      setSummary(data);
      setSummaryError(null);
    } catch (e) {
      setSummaryError(e.message);
    }
  }, []);

  useEffect(() => {
    fetchSummary();
    const interval = setInterval(fetchSummary, 30000);
    return () => clearInterval(interval);
  }, [fetchSummary]);

  return (
    <div style={styles.app}>
      {/* Sidebar */}
      <aside style={styles.sidebar}>
        <div style={styles.logo}>
          <span style={styles.logoIcon}>🔬</span>
          <div>
            <div style={styles.logoTitle}>LLM Monitor</div>
            <div style={styles.logoSub}>Quality Regression Detection</div>
          </div>
        </div>

        <nav style={styles.nav}>
          {NAV_ITEMS.map(item => (
            <button
              key={item.id}
              style={{
                ...styles.navItem,
                ...(activeTab === item.id ? styles.navItemActive : {}),
              }}
              onClick={() => setActiveTab(item.id)}
            >
              <span style={styles.navIcon}>{item.icon}</span>
              {item.label}
              {item.id === 'alerts' && summary?.active_alerts > 0 && (
                <span style={styles.badge}>{summary.active_alerts}</span>
              )}
            </button>
          ))}
        </nav>

        {/* Quick status */}
        <div style={styles.sidebarStatus}>
          {summaryError ? (
            <div style={styles.statusError}>
              <span>⚠️</span> API Offline
            </div>
          ) : summary ? (
            <div style={styles.statusOk}>
              <span
                style={{
                  ...styles.statusDot,
                  background: summary.active_alerts > 0 ? '#f59e0b' : '#10b981',
                }}
              />
              {summary.active_alerts > 0 ? `${summary.active_alerts} active alert(s)` : 'All clear'}
            </div>
          ) : (
            <div style={styles.statusLoading}>Loading…</div>
          )}
        </div>
      </aside>

      {/* Main content */}
      <main style={styles.main}>
        {activeTab === 'dashboard' && (
          <Dashboard summary={summary} error={summaryError} onRefresh={fetchSummary} />
        )}
        {activeTab === 'metrics' && <MetricsPanel />}
        {activeTab === 'alerts' && <AlertsPanel onAcknowledge={fetchSummary} />}
        {activeTab === 'logs' && <InferenceLogsPanel />}
        {activeTab === 'templates' && <TemplatesPanel />}
        {activeTab === 'simulate' && <SimulationPanel onSimulated={fetchSummary} />}
      </main>
    </div>
  );
}

const styles = {
  app: {
    display: 'flex',
    minHeight: '100vh',
    background: '#0f172a',
    color: '#e2e8f0',
  },
  sidebar: {
    width: '240px',
    background: '#1e293b',
    borderRight: '1px solid #334155',
    display: 'flex',
    flexDirection: 'column',
    padding: '0',
    flexShrink: 0,
  },
  logo: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    padding: '20px 16px',
    borderBottom: '1px solid #334155',
  },
  logoIcon: { fontSize: '28px' },
  logoTitle: { fontWeight: '700', fontSize: '15px', color: '#f1f5f9' },
  logoSub: { fontSize: '11px', color: '#64748b', marginTop: '2px' },
  nav: {
    flex: 1,
    padding: '12px 8px',
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  },
  navItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    width: '100%',
    padding: '10px 12px',
    borderRadius: '8px',
    border: 'none',
    background: 'transparent',
    color: '#94a3b8',
    cursor: 'pointer',
    fontSize: '14px',
    fontWeight: '500',
    textAlign: 'left',
    transition: 'all 0.15s',
  },
  navItemActive: {
    background: '#334155',
    color: '#f1f5f9',
  },
  navIcon: { fontSize: '16px', width: '20px', textAlign: 'center' },
  badge: {
    marginLeft: 'auto',
    background: '#ef4444',
    color: '#fff',
    borderRadius: '10px',
    padding: '1px 7px',
    fontSize: '11px',
    fontWeight: '700',
  },
  sidebarStatus: {
    padding: '16px',
    borderTop: '1px solid #334155',
    fontSize: '12px',
  },
  statusOk: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    color: '#94a3b8',
  },
  statusDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    display: 'inline-block',
  },
  statusError: { color: '#f87171' },
  statusLoading: { color: '#64748b' },
  main: {
    flex: 1,
    overflow: 'auto',
    padding: '24px',
  },
};