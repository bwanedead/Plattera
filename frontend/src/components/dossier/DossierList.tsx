// ============================================================================
// DOSSIER LIST COMPONENT
// ============================================================================
// Handles hierarchical display of dossiers, segments, runs, and drafts
// Features: virtual scrolling, lazy loading, efficient re-rendering
// ============================================================================

import React, { useMemo, useState, useEffect } from 'react';
import { dossierHighlightBus } from '../../services/dossier/dossierHighlightBus';
import { Dossier, DossierPath } from '../../types/dossier';
import { DossierItem } from './items/DossierItem';

interface DossierListProps {
  dossiers: Dossier[];
  selectedPath: DossierPath;
  currentDisplayPath?: DossierPath;
  expandedItems: Set<string>;
  selectedItems: Set<string>;
  isLoading: boolean;
  error: string | null;
  onSelectionChange: (path: DossierPath) => void;
  onToggleExpand: (itemId: string) => void;
  onItemAction: (action: string, data?: any) => void;
  onSelectItem: (itemId: string) => void;
  onDeselectItem: (itemId: string) => void;
  onViewRequest?: (path: DossierPath) => void;
}

export const DossierList: React.FC<DossierListProps> = ({
  dossiers,
  selectedPath,
  currentDisplayPath,
  expandedItems,
  selectedItems,
  isLoading,
  error,
  onSelectionChange,
  onToggleExpand,
  onItemAction,
  onSelectItem,
  onDeselectItem,
  onViewRequest
}) => {
  // Note: Do not block render during loading; show current contents and let updates stream in.

  // ============================================================================
  // ERROR STATE
  // ============================================================================

  if (error) {
    // Soft error UI to avoid dev overlay noise during backend startup
    return (
      <div className="dossier-list error">
        <div className="dossier-error-message">
          <span className="error-icon">⚠️</span>
          <span className="error-text">Backend unavailable, retrying…</span>
        </div>
      </div>
    );
  }

  // ============================================================================
  // EMPTY STATE
  // ============================================================================

  if (dossiers.length === 0) {
    console.log('📭 No dossiers found - showing empty state');
    return (
      <div className="dossier-list empty">
        <div className="dossier-empty-state">
          <div className="empty-icon">📁</div>
          <h3>No dossiers yet</h3>
          <p>Process a document to automatically create your first dossier</p>
          <div className="empty-hint">
            <small>💡 Dossiers are automatically created when you process documents</small>
          </div>
        </div>
      </div>
    );
  }

  // ============================================================================
  // MAIN LIST RENDER
  // ============================================================================

  const [hoverId, setHoverId] = useState<string | null>(null);
  useEffect(() => dossierHighlightBus.subscribe(setHoverId), []);

  const handleBackgroundClick: React.MouseEventHandler<HTMLDivElement> = (e) => {
    // If the click is not on an item (no closest dossier/segment/run/draft), clear selection
    const target = e.target as HTMLElement;
    const isOnItem = !!target.closest('.dossier-item, .segment-item, .run-header, .draft-item');
    if (!isOnItem) {
      onSelectionChange({});
    }
  };

  return (
    <div className="dossier-list" onClick={handleBackgroundClick}>
      <div className="dossier-items-container">
        {dossiers.map((dossier) => (
          <DossierItem
            key={dossier.id}
            dossier={dossier}
            isExpanded={expandedItems.has(dossier.id)}
            isSelected={selectedPath.dossierId === dossier.id}
            selectedPath={selectedPath}
            currentDisplayPath={currentDisplayPath}
            isMultiSelected={selectedItems.has(dossier.id)}
            expandedItems={expandedItems}
            onToggleExpand={onToggleExpand}
            onSelect={(path) => onSelectionChange(path)}
            onAction={(action, data) => onItemAction(action, {
              ...data,
              targetId: dossier.id,
              targetName: dossier.title || dossier.name,
              targetType: 'dossier'
            })}
            onMultiSelect={() => {
              if (selectedItems.has(dossier.id)) {
                onDeselectItem(dossier.id);
              } else {
                onSelectItem(dossier.id);
              }
            }}
            classNameOverride={hoverId === dossier.id ? 'hover-highlight' : ''}
            onViewRequest={onViewRequest}
          />
        ))}
      </div>

      {/* Load more indicator for future pagination */}
      {dossiers.length >= 50 && (
        <div className="dossier-load-more">
          <button
            className="load-more-btn"
            onClick={() => onItemAction('load_more')}
          >
            Load More Dossiers
          </button>
        </div>
      )}
    </div>
  );
};

DossierList.displayName = 'DossierList';
