import React, { useEffect, useState, useCallback } from 'react';
import { fetchBudgets, createBudget, deleteBudget, evaluateBudgets } from '../api';
import styles from './Dashboard.module.css';

const DIMENSION_TYPES = ['global', 'team', 'model', 'feature'];
const PERIODS = ['daily', 'weekly', 'monthly'];

const DEFAULT_FORM = {
  name: '',
  description: '',
  dimension_type: 'team',
  dimension_value: '',
  budget_usd: '',
  period: 'monthly',
  warn_threshold_pct: 80,
  critical_threshold_pct: 95,
};

export default function BudgetManager() {
  const [budgets, setBudgets] = useState([]);
  const [form, setForm] = useState(DEFAULT_FORM);
  const [saving, setSaving] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [msg, setMsg] = useState('');

  const load = useCallback(async () => {
    const b = await fetchBudgets();
    setBudgets(b);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleChange = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setMsg('');
    try {
      await createBudget({
        ...form,
        budget_usd: parseFloat(form.budget_usd),
        warn_threshold_pct: parseFloat(form.warn_threshold_pct),
        critical_threshold_pct: parseFloat(form.critical_threshold_pct),
        dimension_value: form.dimension_type === 'global' ? null : form.dimension_value || null,
      });
      setMsg('✅ Budget policy created');
      setForm(DEFAULT_FORM);
      load();
    } catch (err) {
      setMsg(`❌ ${err?.response?.data?.detail || 'Error creating policy'}`);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this budget policy?')) return;
    await deleteBudget(id);
    load();
  };

  const handleEvaluate = async () => {
    setEvaluating(true);
    await evaluateBudgets();
    await load();
    setMsg('✅ Budget policies evaluated');
    setEvaluating(false);
  };

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Budget Policies</h1>
          <p className={styles.pageSubtitle}>Manage spend thresholds and alert rules</p>
        </div>
        <div className={styles.headerActions}>
          <button className={styles.actionBtn} onClick={handleEvaluate} disabled={evaluating}>
            {evaluating ? 'Evaluating…' : 'Evaluate Now'}
          </button>
          <button className={styles.refreshBtn} onClick={load}>↻ Refresh</button>
        </div>
      </div>

      <div className={styles.twoCol}>
        <div className={styles.panel}>
          <div className={styles.panelTitle}>Active Budget Policies</div>
          {budgets.length === 0 ? (
            <div className={styles.empty}>No budgets configured</div>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Scope</th>
                    <th>Spend</th>
                    <th>Budget</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {budgets.map(b => {
                    const pct = b.spend_pct;
                    const level = pct >= b.critical_threshold_pct ? 'critical'
                      : pct >= b.warn_threshold_pct ? 'warn' : 'good';
                    const levelLabel = pct >= b.critical_threshold_pct ? 'CRITICAL'
                      : pct >= b.warn_threshold_pct ? 'WARNING' : 'OK';
                    return (
                      <tr key={b.id}>
                        <td>
                          <div style={{ fontWeight: 500 }}>{b.name}</div>
                          {b.description && <div style={{ fontSize: 11, color: '#64748b' }}>{b.description}</div>}
                        </td>
                        <td>
                          <span style={{ fontSize: 11, color: '#94a3b8' }}>
                            {b.dimension_type}{b.dimension_value ? `: ${b.dimension_value}` : ''}
                          </span>
                        </td>
                        <td>
                          <div>${b.current_spend_usd.toFixed(2)}</div>
                          <div style={{ fontSize: 11, color: '#64748b' }}>{pct.toFixed(1)}%</div>
                        </td>
                        <td>
                          <div>${b.budget_usd.toFixed(0)}</div>
                          <div style={{ fontSize: 11, color: '#64748b' }}>{b.period}</div>
                        </td>
                        <td>
                          <span className={`${styles.badge} ${styles[level]}`}>{levelLabel}</span>
                        </td>
                        <td>
                          <button className={styles.deleteBtn} onClick={() => handleDelete(b.id)}>
                            Remove
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className={styles.panel}>
          <div className={styles.panelTitle}>Create Budget Policy</div>
          <form className={styles.form} onSubmit={handleSubmit}>
            <div className={styles.formGroup}>
              <label className={styles.label}>Policy Name *</label>
              <input
                className={styles.input}
                required
                value={form.name}
                onChange={e => handleChange('name', e.target.value)}
                placeholder="e.g. Search Team Monthly"
              />
            </div>

            <div className={styles.formRow}>
              <div className={styles.formGroup}>
                <label className={styles.label}>Dimension Type *</label>
                <select
                  className={styles.select}
                  value={form.dimension_type}
                  onChange={e => handleChange('dimension_type', e.target.value)}
                >
                  {DIMENSION_TYPES.map(d => (
                    <option key={d} value={d}>{d}</option>
                  ))}
                </select>
              </div>
              <div className={styles.formGroup}>
                <label className={styles.label}>Dimension Value</label>
                <input
                  className={styles.input}
                  value={form.dimension_value}
                  onChange={e => handleChange('dimension_value', e.target.value)}
                  placeholder={form.dimension_type === 'global' ? 'n/a (global)' : 'e.g. search'}
                  disabled={form.dimension_type === 'global'}
                />
              </div>
            </div>

            <div className={styles.formRow}>
              <div className={styles.formGroup}>
                <label className={styles.label}>Budget (USD) *</label>
                <input
                  className={styles.input}
                  type="number"
                  required
                  min="0.01"
                  step="0.01"
                  value={form.budget_usd}
                  onChange={e => handleChange('budget_usd', e.target.value)}
                  placeholder="1000.00"
                />
              </div>
              <div className={styles.formGroup}>
                <label className={styles.label}>Period *</label>
                <select
                  className={styles.select}
                  value={form.period}
                  onChange={e => handleChange('period', e.target.value)}
                >
                  {PERIODS.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
            </div>

            <div className={styles.formRow}>
              <div className={styles.formGroup}>
                <label className={styles.label}>Warn Threshold %</label>
                <input
                  className={styles.input}
                  type="number"
                  min="0"
                  max="100"
                  value={form.warn_threshold_pct}
                  onChange={e => handleChange('warn_threshold_pct', e.target.value)}
                />
              </div>
              <div className={styles.formGroup}>
                <label className={styles.label}>Critical Threshold %</label>
                <input
                  className={styles.input}
                  type="number"
                  min="0"
                  max="100"
                  value={form.critical_threshold_pct}
                  onChange={e => handleChange('critical_threshold_pct', e.target.value)}
                />
              </div>
            </div>

            {msg && (
              <div style={{
                fontSize: 13,
                color: msg.startsWith('✅') ? '#6ee7b7' : '#fca5a5',
                padding: '8px 0'
              }}>
                {msg}
              </div>
            )}

            <button type="submit" className={styles.submitBtn} disabled={saving}>
              {saving ? 'Creating…' : 'Create Budget Policy'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}