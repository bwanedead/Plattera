import React from 'react';
import type { AgentViewerInventorySection } from '../model/snapshotInventory';
import type { ViewerSelection } from '../selection/selectionTypes';

type ResolutionInspectorProps = {
  sections: AgentViewerInventorySection[];
  selection: ViewerSelection | null;
  onSelect: (selection: ViewerSelection) => void;
};

export function ResolutionInspector({ sections, selection, onSelect }: ResolutionInspectorProps) {
  const workItems = sections.find((section) => section.id === 'work_item');
  const artifacts = sections.find((section) => section.id === 'artifact');

  return (
    <div className="av-resolution-inspector">
      <InspectorSection
        title="Resolution"
        count={workItems?.count ?? 0}
        items={(workItems?.items ?? []).slice(0, 12)}
        selection={selection}
        kind="work_item"
        onSelect={onSelect}
      />
      <InspectorSection
        title="Artifacts"
        count={artifacts?.count ?? 0}
        items={(artifacts?.items ?? []).slice(0, 10)}
        selection={selection}
        kind="artifact"
        onSelect={onSelect}
      />
    </div>
  );
}

type InspectorSectionProps = {
  title: string;
  count: number;
  items: AgentViewerInventorySection['items'];
  selection: ViewerSelection | null;
  kind: 'work_item' | 'artifact';
  onSelect: (selection: ViewerSelection) => void;
};

function InspectorSection({ title, count, items, selection, kind, onSelect }: InspectorSectionProps) {
  return (
    <section className="av-inspector-section">
      <div className="av-inspector-section-header">
        <span>{title}</span>
        <span className="av-count">{count}</span>
      </div>
      <div className="av-inspector-list">
        {items.length === 0 ? <div className="av-empty-inline">None yet</div> : null}
        {items.map((item) => {
          const selected = selection?.kind === kind && selection.id === item.id;
          return (
            <button
              key={item.id}
              type="button"
              className={`av-inspector-row ${selected ? 'is-selected' : ''}`}
              onClick={() =>
                onSelect({
                  kind,
                  id: item.id,
                  ref: item.ref,
                  label: item.title,
                  payload: { raw: item.raw, rendererId: item.rendererId },
                })
              }
            >
              <div className="av-inspector-row-title">{item.title}</div>
              {item.subtitle ? <div className="av-inspector-row-sub">{item.subtitle}</div> : null}
              {item.status ? <span className="av-inspector-status">{item.status}</span> : null}
            </button>
          );
        })}
      </div>
    </section>
  );
}
