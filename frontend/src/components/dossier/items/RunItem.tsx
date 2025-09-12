// ============================================================================
// RUN ITEM COMPONENT
// ============================================================================
// Displays processing runs with expandable drafts
// ============================================================================

import React, { useState, useCallback } from 'react';
import { Run, DossierPath } from '../../../types/dossier';
import { DraftItem } from './DraftItem';

interface RunItemProps {
  run: Run;
  segment: { id: string; name: string };
  dossier: { id: string; title?: string; name?: string };
  isExpanded: boolean;
  isSelected: boolean;
  onToggleExpand?: (id: string) => void;
  onItemAction: (action: string, data: any) => void;
  onItemSelect: (path: DossierPath) => void;
  onViewRequest?: (path: DossierPath) => void;
}

export const RunItem: React.FC<RunItemProps> = ({
  run,
  segment,
  dossier,
  isExpanded,
  isSelected,
  onToggleExpand,
  onItemAction,
  onItemSelect,
  onViewRequest
}) => {
  // Early return for safety
  if (!run) return null;

  // ============================================================================
  // STATE
  // ============================================================================

  const [isDragging] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  // ============================================================================
  // COMPUTED VALUES
  // ============================================================================

  const stats = {
    drafts: run.drafts?.length || 0,
    totalSize: (run.drafts || []).reduce((sum, draft) => sum + (draft.metadata?.sizeBytes || 0), 0)
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  };

  const formatDate = (dateInput: Date | string): string => {
    try {
      // Handle both Date objects and ISO date strings from backend
      const date = typeof dateInput === 'string' ? new Date(dateInput) : dateInput;
      
      // Safety check for invalid dates
      if (isNaN(date.getTime())) {
        console.warn('Invalid date received:', dateInput);
        return 'Unknown Date';
      }
      
      return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch (error) {
      console.warn('Error formatting date:', dateInput, error);
      return 'Invalid Date';
    }
  };

  const bestDraft = (run.drafts || []).find(draft => draft.isBest);

  // ============================================================================
  // EVENT HANDLERS
  // ============================================================================

  const handleClick = useCallback(() => {
    // Single-click only selects, does not view
    if (!dossier?.id || !segment?.id || !run?.id) {
      console.warn('RunItem click ignored due to missing ids', { dossier, segment, run });
      return;
    }
    // Do not persist selection for sub-items; rely on hover styles
  }, [dossier?.id, segment?.id, run?.id, onItemSelect]);

  const handleDoubleClick = useCallback(() => {
    if (!dossier?.id || !segment?.id || !run?.id) return;
    onViewRequest?.({ dossierId: dossier.id, segmentId: segment.id, runId: run.id });
  }, [onViewRequest, dossier?.id, segment?.id, run?.id]);

  const handleExpandClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (!run?.id) return;
    if (typeof onToggleExpand !== 'function') {
      console.warn('RunItem: onToggleExpand is not a function', { onToggleExpand });
      return;
    }
    onToggleExpand(run.id);
  }, [run?.id, onToggleExpand]);

  const handleDraftSelect = useCallback((draftId: string) => {
    if (!dossier?.id || !segment?.id || !run?.id || !draftId) {
      console.warn('Draft select ignored due to missing ids', { dossier, segment, run, draftId });
      return;
    }
    const path: DossierPath = {
      dossierId: dossier.id,
      segmentId: segment.id,
      runId: run.id,
      draftId
    };
    onItemSelect(path);
  }, [dossier?.id, segment?.id, run?.id, onItemSelect]);

  // ============================================================================
  // RENDER
  // ============================================================================

  return (
    <div className={`run-item ${isDragging ? 'dragging' : ''}`}>
      {/* Header */}
      <div
        className="run-header"
        onClick={(e) => { handleClick(); if (typeof onToggleExpand === 'function') { onToggleExpand(run.id); } }}
        onDoubleClick={handleDoubleClick}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        role="button"
        tabIndex={0}
      >
        <div className="run-expand-section">
          <button
            className={`run-expand-button ${isExpanded ? 'expanded' : ''}`}
            onClick={handleExpandClick}
            disabled={(run.drafts?.length || 0) === 0}
            aria-label={isExpanded ? 'Collapse run' : 'Expand run'}
          >
            {(run.drafts?.length || 0) > 0 ? (isExpanded ? '▼' : '▶') : '○'}
          </button>
        </div>

        <div className="run-info">
          <div className="run-name">
            Run {run.position + 1}
          </div>
          <div className="run-details">
            <span className="run-date">
              {formatDate(run.metadata?.createdAt || new Date().toISOString())}
            </span>
            <span className="run-stats">
              {stats.drafts} drafts • {formatSize(stats.totalSize)}
            </span>
            {bestDraft && (
              <span className="run-best-indicator">Best</span>
            )}
          </div>
          {(isHovered || isSelected) && (
            <div className="run-actions">
              <button
                className="dossier-action-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  if (!dossier?.id || !segment?.id || !run?.id) return;
                  console.log('👁️ Run view button', { dossierId: dossier.id, segmentId: segment.id, runId: run.id });
                  onViewRequest?.({ dossierId: dossier.id, segmentId: segment.id, runId: run.id });
                }}
                title="View run"
              >
                View
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="run-content" onClick={(e) => e.stopPropagation()}>
          {(run.drafts?.length || 0) === 0 ? (
            <div className="run-empty">No drafts available</div>
          ) : (
            <div className="run-drafts">
              {(run.drafts || []).map((draft, index) => (
                <DraftItem
                  key={draft.id || `draft-${index}`}
                  draft={draft}
                  run={run}
                  segment={segment}
                  dossier={dossier}
                  onItemAction={onItemAction}
                  onItemSelect={() => handleDraftSelect(draft.id)}
                  onViewRequest={onViewRequest}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
