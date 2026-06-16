import React, { useEffect, useState, useCallback } from 'react';
import { fetchPricing } from '../api';
import styles from './Dashboard.module.css';
import axios from 'axios';

const API_BASE = process.env.REACT_APP_API_URL
  ? `${process.env.REACT_APP_API_URL}/api/v1`
  : '/api/v1';

const PROVIDER_COLORS = {
  openai: '#74aa9c',
  anthropic: '#d4845a',
  google: '#4285f4',
  bedrock: '#ff9900',
};

export default function PricingCatalog() {
  const [pricing, setPricing] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({
    provider: '',
    model: '',
    prompt_cost_per_1k_tokens: '',
    completion_cost_per_1k_tokens: '',
  });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = await fetchPricing();
      setPricing(p);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleChange = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setMsg('');
    try {
      await axios.post(`${API_BASE}/pricing`, {
        ...form,
        prompt_cost_per_1k_tokens: parseFloat(form.prompt_cost_per_1k_tokens),
        completion_cost_per_1k_tokens: parseFloat(form.completion_cost_per_1k_tokens),
      });
      setMsg('✅ Pricing entry saved');
      setForm({ provider: '', model: '', prompt_cost_per_1k_tokens: '', completion_cost_per_1k_tokens: '' });
      load();
    } catch (err) {
      setMsg(`❌ ${err?.response?.data?.detail || 'Error saving pricing'}`);
    } finally {
      setSaving(false);
    }
  };

  const byProvider = pricing.reduce((acc, p) => {
    if (!acc[p.provider]) acc[p.provider] = [];
    acc[p.provider].push(p);
    return acc;
  }, {});

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Pricing Catalog</h1>
          <p className={styles.pageSubtitle}>LLM model pricing rates used for cost computation</p>
        </div>
        <button className={styles.refreshBtn} onClick={load}>↻ Refresh</button>
      </div>

      <div className={styles.twoCol}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {loading && <div className={styles.loading}>Loading…</div>}
          {!loading && Object.entries(byProvider).map(([provider, models]) => (
            <div key={provider} className={styles.panel}>
              <div className={styles.panelTitle} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{
                  width: 10, height: 10, borderRadius: '50%',
                  background: PROVIDER_COLORS[provider] || '#94a3b8',
                  display: 'inline-block'
                }} />
                {provider.toUpperCase()}
              </div>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>Prompt / 1K</th>
                    <th>Completion / 1K</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {models.map((m, i) => (
                    <tr key={i}>
                      <td>
                        <span style={{ fontSize: 12, fontFamily: 'monospace', color: '#c4b5fd' }}>
                          {m.model}
                        </span>
                      </td>
                      <td>${m.prompt_cost_per_1k_tokens.toFixed(5)}</td>
                      <td>${m.completion_cost_per_1k_tokens.toFixed(5)}</td>
                      <td style={{ fontSize: 11, color: '#64748b' }}>
                        {m.effective_from?.slice(0, 10)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>

        <div className={styles.panel}>
          <div className={styles.panelTitle}>Add / Update Pricing Entry</div>
          <p style={{ fontSize: 12, color: '#64748b', marginBottom: 16, lineHeight: 1.6 }}>
            Update pricing when providers change rates. Adding a new entry for an existing model
            will expire the old one automatically.
          </p>
          <form className={styles.form} onSubmit={handleSubmit}>
            <div className={styles.formRow}>
              <div className={styles.formGroup}>
                <label className={styles.label}>Provider *</label>
                <input
                  className={styles.input}
                  required
                  value={form.provider}
                  onChange={e => handleChange('provider', e.target.value)}
                  placeholder="openai"
                />
              </div>
              <div className={styles.formGroup}>
                <label className={styles.label}>Model *</label>
                <input
                  className={styles.input}
                  required
                  value={form.model}
                  onChange={e => handleChange('model', e.target.value)}
                  placeholder="gpt-4o"
                />
              </div>
            </div>
            <div className={styles.formRow}>
              <div className={styles.formGroup}>
                <label className={styles.label}>Prompt Cost / 1K tokens ($) *</label>
                <input
                  className={styles.input}
                  type="number"
                  step="0.000001"
                  min="0"
                  required
                  value={form.prompt_cost_per_1k_tokens}
                  onChange={e => handleChange('prompt_cost_per_1k_tokens', e.target.value)}
                  placeholder="0.005"
                />
              </div>
              <div className={styles.formGroup}>
                <label className={styles.label}>Completion Cost / 1K tokens ($) *</label>
                <input
                  className={styles.input}
                  type="number"
                  step="0.000001"
                  min="0"
                  required
                  value={form.completion_cost_per_1k_tokens}
                  onChange={e => handleChange('completion_cost_per_1k_tokens', e.target.value)}
                  placeholder="0.015"
                />
              </div>
            </div>

            {msg && (
              <div style={{
                fontSize: 13,
                color: msg.startsWith('✅') ? '#6ee7b7' : '#fca5a5',
              }}>
                {msg}
              </div>
            )}

            <button type="submit" className={styles.submitBtn} disabled={saving}>
              {saving ? 'Saving…' : 'Save Pricing Entry'}
            </button>
          </form>

          <div style={{ marginTop: 24, padding: '12px', background: '#0f172a', borderRadius: 8 }}>
            <div style={{ fontSize: 11, color: '#64748b', marginBottom: 8, fontWeight: 600, textTransform: 'uppercase' }}>
              Reference Pricing (USD per 1K tokens)
            </div>
            <div style={{ fontSize: 11, color: '#94a3b8', lineHeight: 2, fontFamily: 'monospace' }}>
              <div>gpt-4o        prompt: $0.005   completion: $0.015</div>
              <div>gpt-4o-mini   prompt: $0.00015 completion: $0.0006</div>
              <div>claude-3-5-sonnet prompt: $0.003 completion: $0.015</div>
              <div>claude-3-haiku prompt: $0.00025 completion: $0.00125</div>
              <div>gemini-1.5-flash prompt: $0.000075 completion: $0.0003</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}