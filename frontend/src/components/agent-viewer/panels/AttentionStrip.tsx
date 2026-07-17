import React from 'react';
import type { AttentionItem } from '../model/attentionModel';
import type { ViewerSelection } from '../selection/selectionTypes';

type AttentionStripProps = {
  items: AttentionItem[];
  selection: ViewerSelection | null;
  onSelectRef: (ref: string, label: string) => void;
};

export function AttentionStrip({ items, selection, onSelectRef }: AttentionStripProps) {
  if (!items.length) return null;

  return (
    <section className="av-attention-strip">
      <div className="av-attention-label">Attention</div>
      <div className="av-attention-items">
        {items.map((item) => {
          const selected = selection?.ref === item.ref;
          return (
            <button
              key={item.ref}
              type="button"
              className={`av-attention-chip ${selected ? 'is-selected' : ''}`}
              onClick={() => onSelectRef(item.ref, item.label)}
              title={item.reason}
            >
              {item.label}
            </button>
          );
        })}
      </div>
    </section>
  );
}
