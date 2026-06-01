import React, { useState, useEffect, useCallback } from 'react';
import { format } from 'date-fns';
import { api } from '../api';

const STATUS_COLOR = {
  scored: '#10b981',
  scoring: '#f59e0b',
  pending: '#64748b',
  error: '#ef4444',
};

export default function InferenceLogsPanel() {
  const [logs, setLogs] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState('');
  const [hours, setHours] = useState(24);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedLog, setSelectedLog] = useState(null);
  const [logDetail, setLogDetail] = useState(null);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = { hours, limit: 100 };
      if (selectedTemplate) params.template_id = selectedTemplate;
      const [data, tmpl] = await Promise.all([
        api.getInferenceLogs(params),
        api.getTemplates(),
      ]);
      setLogs(data);
      setTemplates(tmpl);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [selectedTemplate, hours]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  const handleSelectLog = async (log) => {
    setSelectedLog(log.id);
    try {
      const detail = await api.getInferenceLog(log.id);
      setLogDetail(detail);
    } catch (e) {
      setLogDetail(null);
    }
  };

  return (
    <div>
      <div style={styles.header}>
        <h1 style={styles.title}>Inference Logs</h1>
        <button style={styles.refreshBtn} onClick={fetchLogs}>↻ Refresh</button>
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
          value={hours}
          onChange={e => setHours(Number(e.target.value))}
        >
          <option value={6}>Last 6h</option>
          <option value={24}>Last 24h</option>
          <option value={48}>Last 48h</option>
          <option value={168}>Last 7d</option>
        </select>
      </div>

      {error && <div style={styles.errorBox}>{error}</div>}

      <div style={styles.splitView}>
        {/* Log list */}
        <div style={styles.logList}>
          {loading ? (
            <div style={styles.loading}>Loading…</div>
          ) : logs.length === 0 ? (
            <div style={styles.empty}>
              No inference logs yet. Send requests through the proxy to see them here.
            </div>
          ) : (
            logs.map(log => (
              <div
                key={log.id}
                style={{
                  ...styles.logRow,
                  ...(selectedLog === log.id ? styles.logRowSelected : {}),
                }}
                onClick={() => handleSelectLog(log)}
              >
                <div style={styles.logRowTop}>
                  <span
                    style={{
                      ...styles.statusDot,
                      background: STATUS_COLOR[log.status] || '#64748b',
                    }}
                  />
                  <span style={styles.logTemplate}>{log.template_name || 'default'}</span>
                  <span style={styles.logModel}>{log.model}</span>
                </div>
                <div style={styles.logRowBottom}>
                  <span style={styles.logTime}>
                    {format(new Date(log.created_at), 'MMM d, HH:mm:ss')}
                  </span>
                  {log.latency_ms && (
                    <span style={styles.logMeta}>{log.latency_ms.toFixed(0)}ms</span>
                  )}
                  {log.scores.length > 0 && (
                    <span style={styles.logMeta}>{log.scores.length} metrics</span>
                  )}
                </div>
                {log.scores.length > 0 && (
                  <div style={styles.scorePills}>
                    {log.scores.slice(0, 3).map(s => (
                      <ScorePill key={s.metric_name} metric={s.metric_name} score={s.score} />
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        {/* Detail pane */}
        <div style={styles.detailPane}>
          {!logDetail ? (
            <div style={styles.detailEmpty}>
              Select an inference log to view details
            </div>
          ) : (
            <LogDetail log={logDetail} />
          )}
        </div>
      </div>
    </div>
  );
}

function ScorePill({ metric, score }) {
  const pct = Math.round(score * 100);
  const color = pct >= 80 ? '#10b981' : pct >= 60 ? '#f59e0b' : '#ef4444';
  const short = metric.split('_').slice(-1)[0];
  return (
    <span style={{ ...styles.pill, color, background: color + '22', border: `1px solid ${color}44` }}>
      {short}: {pct}%
    </span>
  );
}

function LogDetail({ log }) {
  const [showRaw, setShowRaw] = useState(false);

  const outputText = log.response_payload?.choices?.[0]?.message?.content || '';
  const inputMessages = log.request_payload?.messages || [];
  const lastUserMsg = inputMessages.filter(m => m.role === 'user').slice(-1)[0]?.content || '';

  return (
    <div style={styles.detail}>
      <div style={styles.detailHeader}>
        <div>
          <span style={styles.detailTemplate}>{log.template_name || 'default'}</span>
          <span style={styles.detailModel}> · {log.model}</span>
        </div>
        <span style={{ fontSize: '12px', color: '#64748b' }}>
          {format(new Date(log.created_at), 'MMM d yyyy, HH:mm:ss')}
        </span>
      </div>

      {/* Stats */}
      <div style={styles.detailStats}>
        <MiniStat label="Latency" value={log.latency_ms ? `${log.latency_ms.toFixed(0)}ms` : 'N/A'} />
        <MiniStat label="Prompt tokens" value={log.prompt_tokens ?? 'N/A'} />
        <MiniStat label="Completion tokens" value={log.completion_tokens ?? 'N/A'} />
        <MiniStat label="Status" value={log.status} />
      </div>

      {/* Scores */}
      {log.scores.length > 0 && (
        <div style={styles.scoresSection}>
          <div style={styles.scoresSectionTitle}>Quality Scores</div>
          <div style={styles.scoresGrid}>
            {log.scores.map(s => (
              <div key={s.metric_name} style={styles.scoreItem}>
                <div style={styles.scoreItemLabel}>{s.metric_name}</div>
                <div style={styles.scoreItemBar}>
                  <div style={styles.scoreBarTrack}>
                    <div
                      style={{
                        ...styles.scoreBarFill,
                        width: `${Math.round(s.score * 100)}%`,
                        background: s.score >= 0.8 ? '#10b981' : s.score >= 0.6 ? '#f59e0b' : '#ef4444',
                      }}
                    />
                  </div>
                  <span style={{ ...styles.scoreItemValue, color: s.score >= 0.8 ? '#10b981' : s.score >= 0.6 ? '#f59e0b' : '#ef4444' }}>
                    {(s.score * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Input/Output */}
      <div style={styles.ioSection}>
        <div style={styles.ioLabel}>User Input</div>
        <div style={styles.ioText}>{lastUserMsg || '(no user message)'}</div>
      </div>
      <div style={styles.ioSection}>
        <div style={styles.ioLabel}>Model Output</div>
        <div style={styles.ioText}>{outputText || '(no output)'}</div>
      </div>

      {/* Raw JSON toggle */}
      <button
        style={styles.rawToggle}
        onClick={() => setShowRaw(v => !v)}
      >
        {showRaw ? '▲ Hide' : '▼ Show'} raw payload
      </button>
      {showRaw && (
        <pre style={styles.rawJson}>
          {JSON.stringify({ request: log.request_payload, response: log.response_payload }, null, 2)}
        </pre>
      )}
    </div>
  );
}

function MiniStat({ label, value }) {
  return (
    <div style={styles.miniStat}>
      <div style={styles.miniStatLabel}>{label}</div>
      <div style={styles.miniStatValue}>{value}</div>
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
  splitView: {
    display: 'grid',
    gridTemplateColumns: '340px 1fr',
    gap: '16px',
    minHeight: '500px',
  },
  logList: {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: '12px',
    overflow: 'auto',
    maxHeight: '70vh',
  },
  logRow: {
    padding: '12px 14px',
    borderBottom: '1px solid #334155',
    cursor: 'pointer',
    transition: 'background 0.1s',
  },
  logRowSelected: { background: '#334155' },
  logRowTop: { display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' },
  statusDot: { width: '8px', height: '8px', borderRadius: '50%', flexShrink: 0 },
  logTemplate: { fontWeight: '600', fontSize: '13px', color: '#f1f5f9', flex: 1 },
  logModel: { fontSize: '11px', color: '#64748b', fontFamily: 'monospace' },
  logRowBottom: { display: 'flex', gap: '10px', alignItems: 'center' },
  logTime: { fontSize: '11px', color: '#475569' },
  logMeta: {
    fontSize: '11px',
    color: '#64748b',
    background: '#0f172a',
    padding: '1px 6px',
    borderRadius: '4px',
  },
  scorePills: { display: 'flex', gap: '4px', marginTop: '6px', flexWrap: 'wrap' },
  pill: { fontSize: '10px', padding: '2px 6px', borderRadius: '5px', fontWeight: '600' },
  detailPane: {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: '12px',
    overflow: 'auto',
    maxHeight: '70vh',
  },
  detailEmpty: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '200px',
    color: '#475569',
    fontSize: '14px',
  },
  detail: { padding: '20px' },
  detailHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: '16px',
  },
  detailTemplate: { fontWeight: '700', fontSize: '15px', color: '#f1f5f9' },
  detailModel: { color: '#64748b', fontSize: '13px' },
  detailStats: { display: 'flex', gap: '10px', marginBottom: '16px', flexWrap: 'wrap' },
  miniStat: {
    background: '#0f172a',
    borderRadius: '8px',
    padding: '8px 12px',
  },
  miniStatLabel: { fontSize: '10px', color: '#64748b', marginBottom: '2px' },
  miniStatValue: { fontSize: '13px', fontWeight: '600', color: '#e2e8f0' },
  scoresSection: { marginBottom: '16px' },
  scoresSectionTitle: { fontSize: '12px', color: '#64748b', fontWeight: '600', marginBottom: '8px' },
  scoresGrid: { display: 'flex', flexDirection: 'column', gap: '6px' },
  scoreItem: { display: 'flex', alignItems: 'center', gap: '8px' },
  scoreItemLabel: { fontSize: '11px', color: '#94a3b8', width: '180px', flexShrink: 0, fontFamily: 'monospace' },
  scoreItemBar: { flex: 1, display: 'flex', alignItems: 'center', gap: '8px' },
  scoreBarTrack: { flex: 1, background: '#334155', borderRadius: '4px', height: '6px' },
  scoreBarFill: { height: '100%', borderRadius: '4px' },
  scoreItemValue: { fontSize: '11px', fontWeight: '700', width: '38px', textAlign: 'right' },
  ioSection: { marginBottom: '12px' },
  ioLabel: { fontSize: '11px', color: '#64748b', fontWeight: '600', marginBottom: '4px', textTransform: 'uppercase' },
  ioText: {
    background: '#0f172a',
    borderRadius: '8px',
    padding: '10px 12px',
    fontSize: '13px',
    color: '#94a3b8',
    maxHeight: '120px',
    overflow: 'auto',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  },
  rawToggle: {
    background: 'transparent',
    border: '1px solid #334155',
    color: '#64748b',
    borderRadius: '6px',
    padding: '6px 12px',
    cursor: 'pointer',
    fontSize: '12px',
    marginTop: '8px',
  },
  rawJson: {
    background: '#0f172a',
    borderRadius: '8px',
    padding: '12px',
    marginTop: '8px',
    fontSize: '11px',
    color: '#64748b',
    overflow: 'auto',
    maxHeight: '300px',
    fontFamily: 'monospace',
    lineHeight: '1.5',
  },
  loading: { color: '#64748b', padding: '20px', textAlign: 'center' },
  empty: {
    padding: '32px',
    color: '#64748b',
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
};