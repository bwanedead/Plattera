import React from 'react';
import type { AgentViewerInventorySection } from '../model/snapshotInventory';
import type { ViewerPrimitiveKind } from '../registry/viewerRegistry';
import type { ViewerSelection, ViewerSelectionKind } from '../selection/selectionTypes';

type ResolutionInspectorProps = {
  sections: AgentViewerInventorySection[];
  selection: ViewerSelection | null;
  onSelect: (selection: ViewerSelection) => void;
};

const SECTION_PREVIEW_LIMIT = 8;

export function ResolutionInspector({ sections, selection, onSelect }: ResolutionInspectorProps) {
  const visibleSections = sections.filter((section) => section.count > 0 || section.items.length > 0);

  return (
    <div className="av-resolution-inspector">
      {visibleSections.length === 0 ? <div className="av-empty-inline">No inventory yet</div> : null}
      {visibleSections.map((section) => (
        <InspectorSection
          key={section.id}
          section={section}
          selection={selection}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}

type InspectorSectionProps = {
  section: AgentViewerInventorySection;
  selection: ViewerSelection | null;
  onSelect: (selection: ViewerSelection) => void;
};

function InspectorSection({ section, selection, onSelect }: InspectorSectionProps) {
  const kind = primitiveToSelectionKind(section.id);

  return (
    <section className="av-inspector-section">
      <div className="av-inspector-section-header">
        <span>{section.title}</span>
        <span className="av-count">{section.count}</span>
      </div>
      <div className="av-inspector-list">
        {section.items.length === 0 ? <div className="av-empty-inline">None yet</div> : null}
        {section.items.slice(0, SECTION_PREVIEW_LIMIT).map((item) => {
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

function primitiveToSelectionKind(primitive: ViewerPrimitiveKind): ViewerSelectionKind {
  if (primitive === 'hitl_prompt') return 'hitl';
  return primitive;
}
