import React from 'react';
import type { WorkItemView } from '../model/viewTypes';
import type { ViewerSelection } from '../selection/selectionTypes';
import { summarizeWorkItems } from '../model/normalizeWorkItems';

type WorkItemInspectorProps = {
  items: WorkItemView[];
  selection: ViewerSelection | null;
  onSelect: (selection: ViewerSelection) => void;
};

export function WorkItemInspector({ items, selection, onSelect }: WorkItemInspectorProps) {
  const summary = summarizeWorkItems(items);
  const groups = items.filter((item) => item.level === 'group');
  const units = items.filter((item) => item.level === 'unit');

  return (
    <div className="av-work-item-inspector">
      <div className="av-work-summary">
        <span>{summary.open} open</span>
        <span>{summary.blocked} blocked</span>
        <span>{summary.closed} closed</span>
      </div>

      <InspectorList
        title="Groups"
        rows={groups.slice(0, 8)}
        selection={selection}
        onSelect={onSelect}
      />
      <InspectorList
        title="Units"
        rows={units.slice(0, 12)}
        selection={selection}
        onSelect={onSelect}
      />
    </div>
  );
}

type InspectorListProps = {
  title: string;
  rows: WorkItemView[];
  selection: ViewerSelection | null;
  onSelect: (selection: ViewerSelection) => void;
};

function InspectorList({ title, rows, selection, onSelect }: InspectorListProps) {
  return (
    <section className="av-inspector-section">
      <div className="av-inspector-section-header">
        <span>{title}</span>
        <span className="av-count">{rows.length}</span>
      </div>
      <div className="av-inspector-list">
        {!rows.length ? <div className="av-empty-inline">None</div> : null}
        {rows.map((item) => {
          const selected = selection?.kind === 'work_item' && selection.id === item.id;
          return (
            <button
              key={item.id}
              type="button"
              className={`av-inspector-row ${selected ? 'is-selected' : ''}`}
              onClick={() =>
                onSelect({
                  kind: 'work_item',
                  id: item.id,
                  label: item.title,
                  payload: { raw: item.raw, view: item },
                })
              }
            >
              <div className="av-inspector-row-title">{item.title}</div>
              <div className="av-inspector-row-sub">
                {item.determinedValue != null ? String(item.determinedValue) : 'Undetermined'}
              </div>
              <span className="av-inspector-status">{item.status}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
