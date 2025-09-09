// ============================================================================
// DRAFT ITEM COMPONENT
// ============================================================================
// Displays individual draft versions with quality indicators
// ============================================================================

import React, { useState, useCallback } from 'react';
import { Draft, DossierPath } from '../../../types/dossier';

interface DraftItemProps {
  draft: Draft;
  runId: string;
  segmentId: string;
  dossierId: string;
  isSelected: boolean;
  selectedPath: DossierPath;
  onSelect: (path: DossierPath) => void;
  onAction: (action: string, data?: any) => void;
}

export const DraftItem: React.FC<DraftItemProps> = ({
  draft,
  runId,
  segmentId,
  dossierId,
  isSelected,
  selectedPath,
  onSelect,
  onAction
}) => {
  // ============================================================================
  // EARLY RETURN FOR INVALID DATA
  // ============================================================================

  if (!draft) {
    console.warn('🚨 DraftItem: No draft provided');
    return null;
  }

  // ============================================================================
  // LOCAL STATE
  // ============================================================================

  const [isHovered, setIsHovered] = useState(false);

  // ============================================================================
  // COMPUTED VALUES
  // ============================================================================

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  };

  const formatDate = (date: Date): string => {
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getQualityIcon = (quality: string): string => {
    switch (quality) {
      case 'high': return '🟢';
      case 'medium': return '🟡';
      case 'low': return '🔴';
      default: return '⚪';
    }
  };

  const getQualityLabel = (quality: string): string => {
    switch (quality) {
      case 'high': return 'High';
      case 'medium': return 'Medium';
      case 'low': return 'Low';
      default: return 'Unknown';
    }
  };

  // ============================================================================
  // EVENT HANDLERS
  // ============================================================================

  const handleClick = useCallback(() => {
    onSelect({
      dossierId,
      segmentId,
      runId,
      draftId: draft.id
    });
  }, [dossierId, segmentId, runId, draft.id, onSelect]);

  // ============================================================================
  // RENDER
  // ============================================================================

  return (
    <div className="draft-item-container">
      {/* Main draft row */}
      <div
        className={`draft-item ${isSelected ? 'selected' : ''} ${draft.isBest ? 'best-draft' : ''}`}
        onClick={handleClick}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        {/* Draft icon with quality indicator */}
        <div className="draft-icon">
          {draft.isBest ? '⭐' : '📄'}
        </div>

        {/* Draft info */}
        <div className="draft-info">
          <div className="draft-name">
            Draft {draft.position}
            {draft.isBest && <span className="best-label">(Best)</span>}
          </div>
          <div className="draft-details">
            <span className="draft-quality">
              {getQualityIcon(draft.metadata.quality)} {getQualityLabel(draft.metadata.quality)}
            </span>
            <span className="draft-confidence">
              {Math.round(draft.metadata.confidence * 100)}% confidence
            </span>
            <span className="draft-size">
              {formatSize(draft.metadata.sizeBytes)}
            </span>
            <span className="draft-date">
              {formatDate(draft.metadata.createdAt)}
            </span>
          </div>
        </div>

        {/* Word count */}
        <div className="draft-word-count">
          {draft.metadata.wordCount} words
        </div>

        {/* Action buttons (visible on hover) */}
        {(isHovered || isSelected) && (
          <div className="draft-actions">
            <button
              className="draft-action-btn"
              onClick={(e) => {
                e.stopPropagation();
                onAction('view_draft');
              }}
              title="View draft"
            >
              👁️
            </button>
            <button
              className="draft-action-btn"
              onClick={(e) => {
                e.stopPropagation();
                onAction('edit_draft');
              }}
              title="Edit draft"
            >
              ✏️
            </button>
            <button
              className="draft-action-btn"
              onClick={(e) => {
                e.stopPropagation();
                onAction('duplicate_draft');
              }}
              title="Duplicate draft"
            >
              📋
            </button>
            <button
              className="draft-action-btn danger"
              onClick={(e) => {
                e.stopPropagation();
                onAction('delete_draft');
              }}
              title="Delete draft"
            >
              🗑️
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
