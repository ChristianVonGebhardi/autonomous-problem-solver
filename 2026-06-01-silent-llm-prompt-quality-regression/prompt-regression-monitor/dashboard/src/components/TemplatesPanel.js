import React, { useState, useEffect, useCallback } from 'react';
import { format } from 'date-fns';
import { api } from '../api';

export default function TemplatesPanel() {
  const [templates, setTemplates] = useState([]);
  const [goldenRefs, setGoldenRefs] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // New template form
  const [showNewTemplate, setShowNewTemplate] = useState(false);
  const [newTemplateName, setNewTemplateName] = useState('');
  const [newTemplateDesc, setNewTemplateDesc] = useState('');

  // New golden reference form
  const [showNewRef, setShowNewRef] = useState(false);
  const [newRefInput, setNewRefInput] = useState('');
  const [newRefOutput, setNewRefOutput] = useState('');
  const [saving, setSaving] = useState(false);

  const fetchTemplates = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getTemplates();
      setTemplates(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchGoldenRefs = useCallback(async (templateId) => {
    try {
      const data = await api.getGoldenReferences(templateId);
      setGoldenRefs(data);
    } catch (e) {
      // ignore
    }
  }, []);

  useEffect(() => { fetchTemplates(); }, [fetchTemplates]);

  useEffect(() => {
    if (selectedTemplate) {
      fetchGoldenRefs(selectedTemplate.id);
    }
  }, [selectedTemplate, fetchGoldenRefs]);

  const handleCreateTemplate = async (e) => {
    e.preventDefault();
    if (!newTemplateName.trim()) return;
    setSaving(true);
    try {
      await api.createTemplate({ name: newTemplateName.trim(), description: newTemplateDesc.trim() });
      setNewTemplateName('');
      setNewTemplateDesc('');
      setShowNewTemplate(false);
      await fetchTemplates();
    } catch (e) {
      alert('Error: ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleCreateGoldenRef = async (e) => {
    e.preventDefault();
    if (!newRefInput.trim() || !newRefOutput.trim() || !selectedTemplate) return;
    setSaving(true);
    try {
      await api.createGoldenReference({
        template_id: selectedTemplate.id,
        input_messages: [{ role: 'user', content: newRefInput.trim() }],
        expected_output: newRefOutput.trim(),
      });
      setNewRefInput('');
      setNewRefOutput('');
      setShowNewRef(false);
      await fetchGoldenRefs(selectedTemplate.id);
    } catch (e) {
      alert('Error: ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <div style={styles.header}>
        <h1 style={styles.title}>Templates & Golden References</h1>
        <button
          style={styles.addBtn}
          onClick={() => setShowNewTemplate(v => !v)}
        >
          + New Template
        </button>
      </div>

      {error && <div style={styles.errorBox}>{error}</div>}

      {/* New template form */}
      {showNewTemplate && (
        <div style={styles.formCard}>
          <h3 style={styles.formTitle}>New Prompt Template</h3>
          <form onSubmit={handleCreateTemplate}>
            <div style={styles.formRow}>
              <label style={styles.label}>Template Name *</label>
              <input
                style={styles.input}
                value={newTemplateName}
                onChange={e => setNewTemplateName(e.target.value)}
                placeholder="e.g. customer-support-v2"
                required
              />
            </div>
            <div style={styles.formRow}>
              <label style={styles.label}>Description</label>
              <input
                style={styles.input}
                value={newTemplateDesc}
                onChange={e => setNewTemplateDesc(e.target.value)}
                placeholder="Optional description"
              />
            </div>
            <div style={styles.formActions}>
              <button type="submit" style={styles.saveBtn} disabled={saving}>
                {saving ? 'Saving…' : 'Create Template'}
              </button>
              <button
                type="button"
                style={styles.cancelBtn}
                onClick={() => setShowNewTemplate(false)}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Main layout */}
      <div style={styles.splitView}>
        {/* Template list */}
        <div style={styles.templateList}>
          <div style={styles.listHeader}>Templates</div>
          {loading ? (
            <div style={styles.loading}>Loading…</div>
          ) : templates.length === 0 ? (
            <div style={styles.emptyList}>No templates yet.</div>
          ) : (
            templates.map(t => (
              <div
                key={t.id}
                style={{
                  ...styles.templateRow,
                  ...(selectedTemplate?.id === t.id ? styles.templateRowSelected : {}),
                }}
                onClick={() => setSelectedTemplate(t)}
              >
                <div style={styles.templateName}>{t.name}</div>
                {t.description && (
                  <div style={styles.templateDesc}>{t.description}</div>
                )}
                <div style={styles.templateTime}>
                  {format(new Date(t.created_at), 'MMM d, yyyy')}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Golden references for selected template */}
        <div style={styles.refPane}>
          {!selectedTemplate ? (
            <div style={styles.refEmpty}>Select a template to manage golden references</div>
          ) : (
            <div>
              <div style={styles.refPaneHeader}>
                <div>
                  <span style={styles.refPaneTitle}>{selectedTemplate.name}</span>
                  <span style={styles.refPaneSubtitle}> — Golden References</span>
                </div>
                <button
                  style={styles.addRefBtn}
                  onClick={() => setShowNewRef(v => !v)}
                >
                  + Add Reference
                </button>
              </div>

              {/* New reference form */}
              {showNewRef && (
                <div style={styles.formCard}>
                  <h3 style={styles.formTitle}>Add Golden Reference</h3>
                  <p style={styles.formHint}>
                    Golden references are known-good input/output pairs used to score new outputs
                    via embedding similarity and ROUGE metrics.
                  </p>
                  <form onSubmit={handleCreateGoldenRef}>
                    <div style={styles.formRow}>
                      <label style={styles.label}>Example User Input *</label>
                      <textarea
                        style={{ ...styles.input, minHeight: '72px', resize: 'vertical' }}
                        value={newRefInput}
                        onChange={e => setNewRefInput(e.target.value)}
                        placeholder="What is the capital of France?"
                        required
                      />
                    </div>
                    <div style={styles.formRow}>
                      <label style={styles.label}>Expected Output *</label>
                      <textarea
                        style={{ ...styles.input, minHeight: '100px', resize: 'vertical' }}
                        value={newRefOutput}
                        onChange={e => setNewRefOutput(e.target.value)}
                        placeholder="The capital of France is Paris, which has been the country's capital since..."
                        required
                      />
                    </div>
                    <div style={styles.formActions}>
                      <button type="submit" style={styles.saveBtn} disabled={saving}>
                        {saving ? 'Saving…' : 'Save Reference'}
                      </button>
                      <button
                        type="button"
                        style={styles.cancelBtn}
                        onClick={() => setShowNewRef(false)}
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {/* Reference list */}
              {goldenRefs.length === 0 ? (
                <div style={styles.refListEmpty}>
                  No golden references yet. Add one above to enable embedding and ROUGE scoring.
                </div>
              ) : (
                <div style={styles.refList}>
                  {goldenRefs.map(ref => (
                    <div key={ref.id} style={styles.refCard}>
                      <div style={styles.refOutput}>{ref.expected_output}</div>
                      <div style={styles.refMeta}>
                        Added {format(new Date(ref.created_at), 'MMM d, yyyy HH:mm')}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
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
  title: { fontSize: '24px', fontWeight: '700', color: '#f1f5f9' },
  addBtn: {
    background: '#6366f1',
    border: 'none',
    color: '#fff',
    borderRadius: '8px',
    padding: '9px 16px',
    cursor: 'pointer',
    fontSize: '13px',
    fontWeight: '600',
  },
  formCard: {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: '12px',
    padding: '20px',
    marginBottom: '20px',
  },
  formTitle: { fontSize: '15px', fontWeight: '700', color: '#f1f5f9', marginBottom: '16px' },
  formHint: { fontSize: '13px', color: '#64748b', marginBottom: '16px', lineHeight: '1.5' },
  formRow: { marginBottom: '14px' },
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
  formActions: { display: 'flex', gap: '10px', marginTop: '4px' },
  saveBtn: {
    background: '#6366f1',
    border: 'none',
    color: '#fff',
    borderRadius: '8px',
    padding: '9px 18px',
    cursor: 'pointer',
    fontSize: '13px',
    fontWeight: '600',
  },
  cancelBtn: {
    background: 'transparent',
    border: '1px solid #334155',
    color: '#94a3b8',
    borderRadius: '8px',
    padding: '9px 18px',
    cursor: 'pointer',
    fontSize: '13px',
  },
  splitView: {
    display: 'grid',
    gridTemplateColumns: '280px 1fr',
    gap: '16px',
    minHeight: '400px',
  },
  templateList: {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: '12px',
    overflow: 'hidden',
  },
  listHeader: {
    padding: '12px 16px',
    fontSize: '11px',
    fontWeight: '700',
    color: '#64748b',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    borderBottom: '1px solid #334155',
  },
  templateRow: {
    padding: '12px 16px',
    borderBottom: '1px solid #334155',
    cursor: 'pointer',
  },
  templateRowSelected: { background: '#334155' },
  templateName: { fontWeight: '600', fontSize: '13px', color: '#f1f5f9', marginBottom: '2px' },
  templateDesc: { fontSize: '12px', color: '#64748b', marginBottom: '2px' },
  templateTime: { fontSize: '11px', color: '#475569' },
  refPane: {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: '12px',
    padding: '20px',
    overflow: 'auto',
  },
  refEmpty: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '200px',
    color: '#475569',
    fontSize: '14px',
  },
  refPaneHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '16px',
  },
  refPaneTitle: { fontWeight: '700', color: '#f1f5f9', fontSize: '15px' },
  refPaneSubtitle: { color: '#64748b', fontSize: '14px' },
  addRefBtn: {
    background: '#10b981',
    border: 'none',
    color: '#fff',
    borderRadius: '8px',
    padding: '7px 14px',
    cursor: 'pointer',
    fontSize: '12px',
    fontWeight: '600',
  },
  refListEmpty: {
    padding: '32px',
    textAlign: 'center',
    color: '#64748b',
    fontSize: '14px',
    background: '#0f172a',
    borderRadius: '8px',
  },
  refList: { display: 'flex', flexDirection: 'column', gap: '10px' },
  refCard: {
    background: '#0f172a',
    borderRadius: '8px',
    padding: '14px',
    border: '1px solid #334155',
  },
  refOutput: { fontSize: '13px', color: '#94a3b8', marginBottom: '8px', lineHeight: '1.5' },
  refMeta: { fontSize: '11px', color: '#475569' },
  loading: { padding: '20px', color: '#64748b', textAlign: 'center' },
  emptyList: { padding: '20px', color: '#64748b', textAlign: 'center', fontSize: '13px' },
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