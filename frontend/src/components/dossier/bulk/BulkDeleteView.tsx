import React, { useMemo, useRef } from 'react';
import { Dossier } from '@/types/dossier';

interface BulkDeleteViewProps {
  dossiers: Dossier[];
  selectedIds: Set<string>;
  isLoading?: boolean;
  hasMore?: boolean;
  onLoadMore?: () => void;
  onToggle: (id: string) => void;
  onSelectAll: () => void;
  onClearSelection: () => void;
  onInvertSelection: () => void;
  onSelectRange: (startIdx: number, endIdx: number, replace: boolean) => void;
  onDeleteSelected: () => void;
}

export const BulkDeleteView: React.FC<BulkDeleteViewProps> = ({
  dossiers,
  selectedIds,
  isLoading = false,
  hasMore = false,
  onLoadMore,
  onToggle,
  onSelectAll,
  onClearSelection,
  onInvertSelection,
  onSelectRange,
  onDeleteSelected
}) => {
  const lastIndexRef = useRef<number | null>(null);

  const rows = useMemo(() => dossiers.map((d, i) => ({
    id: d.id,
    title: (d.title || d.name || '').trim() || `(untitled ${d.id.slice(0, 6)})`,
    index: i
  })), [dossiers]);

  const selectedCount = useMemo(() => {
    if (!selectedIds?.size) return 0;
    let count = 0;
    for (const d of dossiers) {
      if (selectedIds.has(d.id)) count++;
    }
    return count;
  }, [dossiers, selectedIds]);

  const handleRowClick = (e: React.MouseEvent, rowIndex: number, id: string) => {
    const isShift = e.shiftKey;
    const isCtrl = e.ctrlKey || e.metaKey;

    if (isShift && lastIndexRef.current != null) {
      onSelectRange(lastIndexRef.current, rowIndex, !isCtrl);
    } else {
      onToggle(id);
    }
    lastIndexRef.current = rowIndex;
  };

  const handleCheckboxClick = (e: React.MouseEvent, rowIndex: number, id: string) => {
    const isShift = e.shiftKey;
    const isCtrl = e.ctrlKey || e.metaKey;
    if (isShift && lastIndexRef.current != null) {
      onSelectRange(lastIndexRef.current, rowIndex, !isCtrl);
    } else {
      onToggle(id);
    }
    lastIndexRef.current = rowIndex;
  };

  return (
    <div className="bulk-delete-view" style={{ display: 'flex', flexDirection: 'column', gap: 8, color: '#111', height: '100%', minHeight: 0 }}>
      <div className="bulk-list" style={{ border: '1px solid #ddd', borderRadius: 6, overflow: 'hidden', background: '#fff', flex: 1, minHeight: 0, overflowY: 'auto' }}>
        {rows.map((row) => {
          const checked = selectedIds.has(row.id);
          return (
            <div
              key={row.id}
              className={`bulk-row ${checked ? 'selected' : ''}`}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 12,
                padding: '10px 14px',
                borderBottom: '1px solid #eee',
                background: checked ? '#eef3ff' : '#fff',
                cursor: 'pointer'
              }}
              onClick={(e) => handleRowClick(e, row.index, row.id)}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={() => { /* noop: we handle selection in onClick for shift support */ }}
                onClick={(e) => { e.stopPropagation(); handleCheckboxClick(e as any, row.index, row.id); }}
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#111', fontSize: 14, fontWeight: 600 }}>
                  {row.title}
                </div>
                <div style={{ marginTop: 2, opacity: 0.60, fontSize: 12, color: '#444', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {row.id}
                </div>
              </div>
            </div>
          );
        })}
        {rows.length === 0 && (
          <div style={{ padding: 16, textAlign: 'center', opacity: 0.7 }}>
            No dossiers found.
          </div>
        )}
      </div>

      <div style={{ position: 'sticky', bottom: 0, background: 'rgba(10,10,10,0.85)', padding: '10px 12px', borderRadius: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
        {(hasMore || isLoading) && (
          <button
            className="dossier-action-btn"
            onClick={onLoadMore}
            disabled={!hasMore || isLoading}
            title="Load more dossiers"
          >
            {isLoading ? 'Loading…' : 'Load more'}
          </button>
        )}
        <div style={{ flex: 1 }} />
        <div style={{ opacity: 0.85, fontSize: 12, color: '#fff' }}>{selectedCount} selected</div>
        <button
          className="dossier-action-btn danger"
          onClick={onDeleteSelected}
          disabled={selectedCount === 0}
          title={selectedCount === 0 ? 'Select dossiers to enable' : 'Delete selected dossiers'}
          style={{ marginLeft: 8 }}
        >
          Delete Selected
        </button>
      </div>
    </div>
  );
};

export default BulkDeleteView;


