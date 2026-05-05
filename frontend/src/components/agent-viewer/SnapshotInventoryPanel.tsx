import React from 'react';
import type { AgentViewerInventorySection } from './model/snapshotInventory';

type Props = {
  sections: AgentViewerInventorySection[];
};

export function SnapshotInventoryPanel({ sections }: Props) {
  if (sections.length === 0) return null;
  const total = sections.reduce((sum, section) => sum + section.count, 0);
  return (
    <div style={{ padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: 10, lineHeight: 1.35 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <span style={{ opacity: 0.86 }}>Snapshot Inventory</span>
        <span style={{ marginLeft: 'auto', opacity: 0.6 }}>{total} items</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 178, overflowY: 'auto' }}>
        {sections.map((section) => (
          <div key={section.id}>
            <div style={{ opacity: 0.62, marginBottom: 3 }}>
              {section.title} ({section.count})
            </div>
            {section.items.slice(0, 3).map((item) => (
              <div key={`${section.id}:${item.id}`} style={{ display: 'flex', gap: 6, alignItems: 'baseline', padding: '2px 0' }}>
                <span style={inventoryBadgeStyle(item.status || item.badge || section.id)}>
                  {String(item.status || item.badge || section.id).slice(0, 18)}
                </span>
                <span style={{ opacity: 0.9, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {item.title}
                </span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function inventoryBadgeStyle(value: string | null | undefined): React.CSSProperties {
  const normalized = String(value || '').toLowerCase();
  const background =
    normalized.includes('block') || normalized.includes('fail')
      ? 'rgba(255,107,107,0.18)'
      : normalized.includes('done') || normalized.includes('available') || normalized.includes('complete')
      ? 'rgba(42,196,119,0.16)'
      : 'rgba(142,197,255,0.14)';
  return {
    flexShrink: 0,
    fontSize: 9,
    lineHeight: 1.1,
    padding: '1px 5px',
    borderRadius: 999,
    background,
    border: '1px solid rgba(255,255,255,0.14)',
    opacity: 0.86,
  };
}
