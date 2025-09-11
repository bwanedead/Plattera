// ============================================================================
// CONFIRM DELETE MODAL COMPONENT
// ============================================================================
// Modal for confirming deletion of dossiers, segments, runs, or drafts
// ============================================================================

import React, { useState } from 'react';

interface ConfirmDeleteModalProps {
  itemName: string;
  itemType: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export const ConfirmDeleteModal: React.FC<ConfirmDeleteModalProps> = ({
  itemName,
  itemType,
  onConfirm,
  onCancel
}) => {
  // ============================================================================
  // LOCAL STATE
  // ============================================================================

  const [isDeleting, setIsDeleting] = useState(false);

  const getWarningMessage = () => {
    switch (itemType) {
      case 'dossier':
        return 'This will permanently delete the dossier and all its segments, runs, and drafts. This action cannot be undone.';
      case 'segment':
        return 'This will permanently delete the segment and all its runs and drafts. Other segments in the dossier will remain.';
      case 'run':
        return 'This will permanently delete the run and all its drafts. Other runs in the segment will remain.';
      case 'draft':
        return 'This will permanently delete this draft. Other drafts in the run will remain.';
      default:
        return 'This action cannot be undone.';
    }
  };

  const getItemIcon = () => {
    switch (itemType) {
      case 'dossier': return '📁';
      case 'segment': return '📝';
      case 'run': return '▶️';
      case 'draft': return '📄';
      default: return '🗑️';
    }
  };

  // ============================================================================
  // EVENT HANDLERS
  // ============================================================================

  const handleConfirm = async () => {
    setIsDeleting(true);
    try {
      await onConfirm();
    } catch (error) {
      console.error('Delete failed:', error);
      setIsDeleting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleConfirm();
    } else if (e.key === 'Escape') {
      onCancel();
    }
  };

  // ============================================================================
  // RENDER
  // ============================================================================

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content delete-modal" onClick={(e) => e.stopPropagation()}>
        {/* Modal header */}
        <div className="modal-header">
          <div className="modal-title-with-icon">
            <span className="delete-icon">{getItemIcon()}</span>
            <h2 className="modal-title">Delete {itemType}</h2>
          </div>
          <button
            className="modal-close-btn"
            onClick={onCancel}
            disabled={isDeleting}
            title="Close"
          >
            ✕
          </button>
        </div>

        {/* Modal body */}
        <div className="modal-body" onKeyDown={handleKeyDown}>
          <div className="delete-confirmation">
            <div className="delete-icon-large">{getItemIcon()}</div>
            <h3>Delete {itemType}?</h3>
            <p className="delete-item-name">{itemName}</p>
            <p className="delete-warning-text">This action cannot be undone.</p>
          </div>
        </div>

        {/* Modal footer */}
        <div className="modal-footer-simple">
          <button
            type="button"
            className="btn-secondary-simple"
            onClick={onCancel}
            disabled={isDeleting}
          >
            Cancel
          </button>

          <button
            type="button"
            className="btn-danger-simple"
            onClick={handleConfirm}
            disabled={isDeleting}
          >
            {isDeleting ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  );
};
