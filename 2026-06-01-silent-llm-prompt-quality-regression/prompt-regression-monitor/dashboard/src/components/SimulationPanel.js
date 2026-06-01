import React, { useState } from 'react';
import { api } from '../api';

export default function SimulationPanel({ onSimulated }) {
  const [templateName, setTemplateName] = useState('test-template');
  const [degradation, setDegradation] = useState(0.30);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleSimulate = async (e) => {
    e.preventDefault();
    setRunning(true);
    setResult(null);
    setError(null);
    try {
      const data = await api.simulateRegression({
        template_name: templateName,
        metric_degradation: parseFloat(degradation),
      });
      setResult(data);
      if (onSimulated) onSimulated();
    } catch (e) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  const handleTriggerDetection = async () => {
    try {
      await api.triggerDetection();
      alert('Drift detection triggered for all templates!');
    } catch (e) {
      alert('Error: ' + e.message);
    }
  };

  return (
    <div>
      <div style={styles.header}>
        <h1 style={styles.title}>Simulate Regression</h1>
      </div>

      <div style={styles.intro}>
        <div style={styles.introIcon}>🧪</div>
        <div>
          <div style={styles.introTitle}>End-to-end Regression Simulation</div>
          <div style={styles.introText}>
            Inject synthetic quality scores to test the detection pipeline without
            needing a real LLM API key. The simulation creates a "baseline" period
            of high-quality scores followed by a degraded period, then triggers
            CUSUM + Mann-Whitney drift detection.
          </div>
        </div>
      </div>

      <div style={styles.grid}>
        {/* Simulation form */}
        <div style={styles.card}>
          <h3 style={styles.cardTitle}>Simulation Parameters</h3>
          <form onSubmit={handleSimulate}>
            <div style={styles.formRow}>
              <label style={styles.label}>Template Name</label>
              <input
                style={styles.input}
                value={templateName}
                onChange={e => setTemplateName(e.target.value)}
                placeholder="test-template"
              />
              <p style={styles.hint}>A template with this name will be created if it doesn't exist.</p>
            </div>

            <div style={styles.formRow}>
              <label style={styles.label}>
                Quality Degradation: <strong style={{ color: '#ef4444' }}>{(degradation * 100).toFixed(0)}%</strong>
              </label>
              <input
                type="range"
                min="0.05"
                max="0.60"
                step="0.05"
                value={degradation}
                onChange={e => setDegradation(e.target.value)}
                style={{ width: '100%', accentColor: '#6366f1' }}
              />
              <div style={styles.rangeLabels}>
                <span>5% (subtle)</span>
                <span>60% (severe)</span>
              </div>
            </div>

            <div style={styles.previewBox}>
              <div style={styles.previewTitle}>Simulation Preview</div>
              <div style={styles.previewRows}>
                <PreviewRow
                  label="Baseline period"
                  value="24h → 4h ago · 30 samples · ~0.85 score"
                  color="#10b981"
                />
                <PreviewRow
                  label="Degraded period"
                  value={`Last 4h · 15 samples · ~${(0.85 * (1 - degradation)).toFixed(2)} score`}
                  color="#ef4444"
                />
                <PreviewRow
                  label="Metrics injected"
                  value="judge_overall, judge_relevance, embedding_max_similarity"
                  color="#6366f1"
                />
                <PreviewRow
                  label="Detection threshold"
                  value="CUSUM slack=0.5σ, MW α=0.05"
                  color="#f59e0b"
                />
              </div>
            </div>

            <button
              type="submit"
              style={{ ...styles.runBtn, opacity: running ? 0.7 : 1 }}
              disabled={running}
            >
              {running ? '⏳ Running simulation…' : '▶ Run Simulation'}
            </button>
          </form>
        </div>

        {/* Results */}
        <div style={styles.card}>
          <h3 style={styles.cardTitle}>Results</h3>

          {error && (
            <div style={styles.errorBox}>{error}</div>
          )}

          {!result && !error && (
            <div style={styles.waitingBox}>
              Run the simulation to see results here.
              Alerts will appear in the Alerts panel once drift is detected.
            </div>
          )}

          {result && (
            <div>
              <div style={styles.successBadge}>✅ Simulation Complete</div>

              <div style={styles.resultGrid}>
                <ResultItem label="Template" value={result.template_name} />
                <ResultItem label="Scores Injected" value={result.scores_injected} />
                <ResultItem label="Degradation" value={`${(result.metric_degradation * 100).toFixed(0)}%`} />
                <ResultItem
                  label="Detection Triggered"
                  value={result.detection_triggered ? 'Yes' : 'No'}
                  valueColor={result.detection_triggered ? '#10b981' : '#f59e0b'}
                />
              </div>

              <div style={styles.nextSteps}>
                <div style={styles.nextStepsTitle}>Next Steps</div>
                <ol style={styles.nextStepsList}>
                  <li>Go to <strong>Metrics</strong> to see the score drop in the time-series chart.</li>
                  <li>Go to <strong>Alerts</strong> to see detected regressions (may take a few seconds).</li>
                  <li>Click an alert to view the CUSUM statistic, p-value, and evidence.</li>
                  <li>Acknowledge the alert once reviewed.</li>
                </ol>
              </div>
            </div>
          )}

          {/* Manual trigger */}
          <div style={styles.manualSection}>
            <div style={styles.manualTitle}>Manual Drift Detection</div>
            <p style={styles.hint}>
              Drift detection runs automatically every 5 minutes. Use this to trigger it immediately.
            </p>
            <button style={styles.triggerBtn} onClick={handleTriggerDetection}>
              ⚡ Trigger Detection Now (All Templates)
            </button>
          </div>
        </div>
      </div>

      {/* Architecture explanation */}
      <div style={styles.archCard}>
        <h3 style={styles.cardTitle}>How Detection Works</h3>
        <div style={styles.archGrid}>
          <ArchStep
            icon="📥"
            title="1. Proxy Intercepts"
            desc="Every LLM request passes through the proxy. Request/response pairs are captured with sub-5ms overhead."
          />
          <ArchStep
            icon="⚙️"
            title="2. Async Scoring"
            desc="Celery workers score outputs: embedding cosine similarity vs golden refs, ROUGE metrics, LLM-as-judge, and custom rules."
          />
          <ArchStep
            icon="📊"
            title="3. CUSUM + Mann-Whitney"
            desc="Rolling windows of scores are tested statistically. CUSUM detects shifts in trend; Mann-Whitney tests distributional change."
          />
          <ArchStep
            icon="🚨"
            title="4. Alert Routing"
            desc="When both detectors agree on regression, an alert fires to Slack, PagerDuty, or webhook with full evidence packet."
          />
        </div>
      </div>
    </div>
  );
}

function PreviewRow({ label, value, color }) {
  return (
    <div style={{ display: 'flex', gap: '10px', fontSize: '12px', marginBottom: '6px' }}>
      <span style={{ width: '130px', color: '#64748b', flexShrink: 0 }}>{label}</span>
      <span style={{ color }}>{value}</span>
    </div>
  );
}

function ResultItem({ label, value, valueColor }) {
  return (
    <div style={styles.resultItem}>
      <div style={styles.resultLabel}>{label}</div>
      <div style={{ ...styles.resultValue, color: valueColor || '#f1f5f9' }}>{value}</div>
    </div>
  );
}

function ArchStep({ icon, title, desc }) {
  return (
    <div style={styles.archStep}>
      <div style={styles.archIcon}>{icon}</div>
      <div style={styles.archTitle}>{title}</div>
      <div style={styles.archDesc}>{desc}</div>
    </div>
  );
}

const styles = {
  header: { marginBottom: '20px' },
  title: { fontSize: '24px', fontWeight: '700', color: '#f1f5f9' },
  intro: {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: '12px',
    padding: '20px',
    display: 'flex',
    gap: '16px',
    marginBottom: '24px',
    alignItems: 'flex-start',
  },
  introIcon: { fontSize: '36px', flexShrink: 0 },
  introTitle: { fontWeight: '700', color: '#f1f5f9', marginBottom: '8px', fontSize: '15px' },
  introText: { color: '#94a3b8', fontSize: '13px', lineHeight: '1.6' },
  grid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '24px' },
  card: {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: '12px',
    padding: '20px',
  },
  cardTitle: { fontSize: '14px', fontWeight: '700', color: '#94a3b8', marginBottom: '16px' },
  formRow: { marginBottom: '16px' },
  label: { display: 'block', fontSize: '12px', color: '#94a3b8', marginBottom: '6px', fontWeight: '600' },
  input: {
    width: '100%',
    background: '#0f172a',
    border: '1px solid #334155',
    borderRadius: '8px',
    padding: '9px 12px',
    color: '#e2e8f0',
    fontSize: '13px',
    outline: 'none',
    boxSizing: 'border-box',
  },
  hint: { fontSize: '11px', color: '#64748b', marginTop: '4px' },
  rangeLabels: {
    display: 'flex',
    justifyContent: 'space-between',
    fontSize: '11px',
    color: '#475569',
    marginTop: '4px',
  },
  previewBox: {
    background: '#0f172a',
    borderRadius: '8px',
    padding: '14px',
    marginBottom: '16px',
  },
  previewTitle: { fontSize: '11px', color: '#64748b', fontWeight: '700', marginBottom: '10px', textTransform: 'uppercase' },
  previewRows: {},
  runBtn: {
    width: '100%',
    background: '#6366f1',
    border: 'none',
    color: '#fff',
    borderRadius: '8px',
    padding: '12px',
    cursor: 'pointer',
    fontSize: '14px',
    fontWeight: '700',
  },
  waitingBox: {
    padding: '32px 16px',
    textAlign: 'center',
    color: '#64748b',
    fontSize: '13px',
    lineHeight: '1.6',
  },
  successBadge: {
    background: '#10b98122',
    border: '1px solid #10b98155',
    color: '#10b981',
    borderRadius: '8px',
    padding: '10px 16px',
    fontSize: '14px',
    fontWeight: '600',
    marginBottom: '16px',
    textAlign: 'center',
  },
  resultGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '10px',
    marginBottom: '16px',
  },
  resultItem: {
    background: '#0f172a',
    borderRadius: '8px',
    padding: '10px 14px',
  },
  resultLabel: { fontSize: '11px', color: '#64748b', marginBottom: '4px' },
  resultValue: { fontSize: '16px', fontWeight: '700' },
  nextSteps: {
    background: '#0f172a',
    borderRadius: '8px',
    padding: '14px',
    marginBottom: '16px',
  },
  nextStepsTitle: { fontSize: '12px', color: '#94a3b8', fontWeight: '700', marginBottom: '8px' },
  nextStepsList: {
    fontSize: '12px',
    color: '#64748b',
    paddingLeft: '16px',
    lineHeight: '1.8',
  },
  manualSection: {
    borderTop: '1px solid #334155',
    paddingTop: '14px',
    marginTop: '8px',
  },
  manualTitle: { fontSize: '13px', fontWeight: '700', color: '#94a3b8', marginBottom: '6px' },
  triggerBtn: {
    background: '#334155',
    border: '1px solid #475569',
    color: '#94a3b8',
    borderRadius: '8px',
    padding: '9px 16px',
    cursor: 'pointer',
    fontSize: '13px',
    fontWeight: '600',
    marginTop: '8px',
  },
  archCard: {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: '12px',
    padding: '20px',
  },
  archGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
    gap: '16px',
  },
  archStep: {
    background: '#0f172a',
    borderRadius: '10px',
    padding: '16px',
    border: '1px solid #334155',
  },
  archIcon: { fontSize: '24px', marginBottom: '8px' },
  archTitle: { fontWeight: '700', color: '#f1f5f9', fontSize: '13px', marginBottom: '6px' },
  archDesc: { fontSize: '12px', color: '#64748b', lineHeight: '1.5' },
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