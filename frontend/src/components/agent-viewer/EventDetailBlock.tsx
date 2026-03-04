import React from 'react';
import type { AgentViewerEvent } from '../../services/agentViewerApi';

const SEVERITY_COLORS: Record<string, string> = {
  error: '#ff6b6b',
  warning: '#d4a83f',
  info: '#8ec5ff',
};

export function EventDetailBlock({ evt }: { evt: AgentViewerEvent }) {
  const phase = String(evt.payload?.phase || '').toLowerCase();
  const detail = evt.payload?.detail as Record<string, any> | undefined;
  if (!detail) return null;

  if (phase === 'audit_result' && Array.isArray(detail.top_findings)) {
    return (
      <div style={{ padding: '6px 0', fontSize: 11, lineHeight: 1.4 }}>
        {(detail.top_findings as any[]).slice(0, 5).map((f: any, i: number) => (
          <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'baseline', marginBottom: 3 }}>
            <span style={{ fontSize: 10, padding: '1px 5px', borderRadius: 4, background: SEVERITY_COLORS[f.severity] || '#555', color: '#fff', flexShrink: 0 }}>
              {String(f.severity || 'info').toUpperCase()}
            </span>
            <span style={{ opacity: 0.88 }}>{String(f.message || '').slice(0, 140)}</span>
          </div>
        ))}
      </div>
    );
  }

  if (phase === 'open_spans_result' && Array.isArray(detail.spans)) {
    return (
      <div style={{ padding: '6px 0', fontSize: 11, lineHeight: 1.4 }}>
        {(detail.spans as any[]).slice(0, 4).map((s: any, i: number) => (
          <div key={i} style={{ marginBottom: 4, fontFamily: 'monospace', fontSize: 10, opacity: 0.82, background: 'rgba(255,255,255,0.03)', padding: '3px 6px', borderRadius: 4 }}>
            {String(s.text || '').slice(0, 100)}
          </div>
        ))}
      </div>
    );
  }

  if (phase === 'image_verify_result' && Array.isArray(detail.results)) {
    return (
      <div style={{ padding: '6px 0', fontSize: 11, lineHeight: 1.4 }}>
        {(detail.results as any[]).slice(0, 5).map((r: any, i: number) => {
          const st = String(r.status || '').toLowerCase();
          const isOk = st === 'confirmed' || st === 'match';
          return (
            <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'baseline', marginBottom: 3 }}>
              <span style={{ fontSize: 10, padding: '1px 5px', borderRadius: 4, background: isOk ? '#2ac477' : '#ff6b6b', color: '#fff', flexShrink: 0 }}>
                {isOk ? 'OK' : 'FAIL'}
              </span>
              <span style={{ opacity: 0.82 }}>{String(r.check_id || '')} — {String(r.observed_text || '').slice(0, 80)}</span>
            </div>
          );
        })}
      </div>
    );
  }

  if ((phase === 'plan_result' || phase === 'apply_result') && Array.isArray(detail.ops_preview || detail.ops)) {
    const ops = (detail.ops_preview || detail.ops || []) as any[];
    return (
      <div style={{ padding: '6px 0', fontSize: 11, lineHeight: 1.4 }}>
        {ops.slice(0, 4).map((op: any, i: number) => (
          <div key={i} style={{ marginBottom: 4 }}>
            <div style={{ fontSize: 10, opacity: 0.6 }}>{String(op.reason || '').slice(0, 80)}</div>
            <div>
              <span style={{ textDecoration: 'line-through', opacity: 0.5 }}>{String(op.original_text || '')}</span>
              {' -> '}
              <span style={{ color: '#2ac477' }}>{String(op.replacement_text || '')}</span>
            </div>
          </div>
        ))}
      </div>
    );
  }

  return null;
}
