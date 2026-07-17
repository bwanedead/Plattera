import React from 'react';
import { JsonTreeView } from '../renderers/generic/JsonTreeView';
import type { ViewerSelection } from '../selection/selectionTypes';

type RawInspectorProps = {
  selection: ViewerSelection | null;
};

export function RawInspector({ selection }: RawInspectorProps) {
  if (!selection) return null;
  const payload = selection.payload?.raw ?? selection.payload?.event ?? selection.payload ?? null;

  return (
    <section className="av-raw-inspector is-open">
      <div className="av-raw-meta">
        <span>{selection.kind}</span>
        <span>{selection.id}</span>
        {selection.ref ? <span>{selection.ref}</span> : null}
      </div>
      <JsonTreeView value={payload} maxDepth={8} />
    </section>
  );
}
