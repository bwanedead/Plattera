import React from 'react';
import { JsonTreeView } from './JsonTreeView';

type UnknownKindRendererProps = {
  title?: string | null;
  kind?: string | null;
  refId?: string | null;
  payload?: unknown;
  reason?: string | null;
};

export function UnknownKindRenderer({ title, kind, refId, payload, reason }: UnknownKindRendererProps) {
  return (
    <div className="av-unknown-renderer">
      <div className="av-unknown-header">
        <div className="av-unknown-title">{title || refId || 'Unknown object'}</div>
        {kind ? <span className="av-badge">{kind}</span> : null}
      </div>
      {reason ? <div className="av-unknown-reason">{reason}</div> : null}
      {refId ? <div className="av-unknown-ref">{refId}</div> : null}
      {payload !== undefined ? <JsonTreeView value={payload} maxDepth={5} /> : null}
    </div>
  );
}
