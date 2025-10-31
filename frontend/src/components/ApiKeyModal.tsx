import React, { useState } from 'react';

type ApiKeyModalProps = {
  open: boolean;
  onClose: () => void;
  onSaved?: () => void;
};

export const ApiKeyModal: React.FC<ApiKeyModalProps> = ({ open, onClose, onSaved }) => {
  const [apiKey, setApiKey] = useState('');
  const [saving, setSaving] = useState(false);

  if (!open) return null;

  const save = async () => {
    if (!apiKey) return;
    setSaving(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/config/key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ apiKey })
      });
      if (!res.ok) {
        const txt = await res.text().catch(() => '');
        throw new Error(txt || `HTTP ${res.status}`);
      }
      onClose();
      if (onSaved) onSaved();
    } catch (e: any) {
      alert(`Failed to save API key: ${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
      <div style={{ background: '#1e1e1e', color: '#fff', padding: 24, borderRadius: 8, width: 420, boxShadow: '0 10px 20px rgba(0,0,0,0.4)' }}>
        <h3 style={{ margin: 0 }}>Set / Update API Key</h3>
        <p style={{ color: '#aaa', marginTop: 8 }}>Stored securely in Windows Credential Manager.</p>
        <input
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="sk-..."
          style={{ width: '100%', padding: 10, marginTop: 12, borderRadius: 4, border: '1px solid #333', background: '#111', color: '#fff' }}
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
          <button onClick={onClose} disabled={saving} style={{ padding: '8px 14px' }}>Cancel</button>
          <button onClick={save} disabled={!apiKey || saving} style={{ padding: '8px 14px', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 4 }}>
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
};


