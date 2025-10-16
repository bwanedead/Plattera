import React from 'react';
import { finalizedApi } from '../src/services/dossier/finalizedApi';

export default function TextSchemaPage() {
  const [list, setList] = React.useState<any[]>([]);
  const [selected, setSelected] = React.useState<string>('');
  const [snapshot, setSnapshot] = React.useState<any | null>(null);
  const [mode, setMode] = React.useState<'stitched' | 'sections'>('stitched');
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    (async () => {
      try { setList(await finalizedApi.listFinalized()); } catch (e:any) { setError(e?.message || 'Failed to load list'); }
    })();
  }, []);

  const load = async (id: string) => {
    setSelected(id);
    setError(null);
    try { setSnapshot(await finalizedApi.getFinal(id)); } catch (e:any) { setError(e?.message || 'Failed to load snapshot'); }
  };

  return (
    <div style={{ padding: 16 }}>
      <h2>Text → Schema</h2>
      <div style={{ marginBottom: 12 }}>
        <label style={{ marginRight: 8 }}>Finalized dossier:</label>
        <select value={selected} onChange={(e) => load(e.target.value)}>
          <option value="">Select…</option>
          {list.map((d) => (
            <option key={d.dossier_id} value={d.dossier_id}>{d.title || d.dossier_id}</option>
          ))}
        </select>
      </div>

      {snapshot && (
        <>
          <div style={{ marginBottom: 12 }}>
            <label>
              <input type="radio" checked={mode==='stitched'} onChange={() => setMode('stitched')} />
              <span style={{ marginLeft: 6 }}>Process stitched text</span>
            </label>
            <label style={{ marginLeft: 16 }}>
              <input type="radio" checked={mode==='sections'} onChange={() => setMode('sections')} />
              <span style={{ marginLeft: 6 }}>Process per-section</span>
            </label>
          </div>

          {mode === 'stitched' ? (
            <textarea readOnly value={snapshot?.stitched_text || ''} style={{ width: '100%', height: 300, fontFamily: 'monospace' }} />
          ) : (
            <div style={{ border: '1px solid #ddd', borderRadius: 6, padding: 8, maxHeight: 320, overflow: 'auto' }}>
              {(snapshot?.sections || []).map((s: any, i: number) => (
                <div key={`${s.segment_id}_${i}`} style={{ marginBottom: 16 }}>
                  <div style={{ fontWeight: 600, fontSize: 12, opacity: 0.8 }}>
                    Segment {i+1} • {s.segment_id} • {s.transcription_id} • {s.draft_id_used}
                  </div>
                  <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>{s.text || ''}</pre>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {error && <div style={{ color: 'crimson', marginTop: 12 }}>{error}</div>}
    </div>
  );
}




