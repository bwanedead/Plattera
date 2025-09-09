// ============================================================================
// DOSSIER FOOTER COMPONENT
// ============================================================================
// Provides bulk actions and additional controls for selected items
// ============================================================================

import React from 'react';

interface DossierFooterProps {
  selectedCount: number;
  onBulkDelete: () => void;
  onClearSelection: () => void;
}

export const DossierFooter: React.FC<DossierFooterProps> = ({
  selectedCount,
  onBulkDelete,
  onClearSelection
}) => {
  return (
    <div className="dossier-footer">
      <div className="footer-content">
        {/* Selection info */}
        <div className="selection-info">
          <span className="selection-count">
            {selectedCount} item{selectedCount !== 1 ? 's' : ''} selected
          </span>
        </div>

        {/* Bulk actions */}
        <div className="bulk-actions">
          <button
            className="bulk-action-btn"
            onClick={() => {/* TODO: Implement bulk move */}}
            title="Move selected items"
          >
            📦 Move
          </button>

          <button
            className="bulk-action-btn"
            onClick={() => {/* TODO: Implement bulk tag */}}
            title="Tag selected items"
          >
            🏷️ Tag
          </button>

          <button
            className="bulk-action-btn"
            onClick={() => {/* TODO: Implement bulk export */}}
            title="Export selected items"
          >
            📤 Export
          </button>

          <button
            className="bulk-action-btn danger"
            onClick={onBulkDelete}
            title="Delete selected items"
          >
            🗑️ Delete All
          </button>
        </div>

        {/* Clear selection */}
        <div className="footer-actions">
          <button
            className="clear-selection-btn"
            onClick={onClearSelection}
            title="Clear selection"
          >
            ✕ Clear
          </button>
        </div>
      </div>
    </div>
  );
};
