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
  segmentId: string;
  dossierId: string;
  isExpanded: boolean;
  isSelected: boolean;
  selectedPath: DossierPath;
  onToggle: () => void;
  onSelect: (path: DossierPath) => void;
  onAction: (action: string, data?: any) => void;
}

export const RunItem: React.FC<RunItemProps> = ({
  run,
  segmentId,
  dossierId,
  isExpanded,
  isSelected,
  selectedPath,
  onToggle,
  onSelect,
  onAction
}) => {
  // ============================================================================
  // EARLY RETURN FOR INVALID DATA
  // ============================================================================

  if (!run) {
    console.warn('🚨 RunItem: No run provided');
    return null;
  }

  // ============================================================================
  // LOCAL STATE
  // ============================================================================

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

  const formatDate = (date: Date): string => {
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const bestDraft = run.drafts.find(draft => draft.isBest);

  // ============================================================================
  // EVENT HANDLERS
  // ============================================================================

  const handleClick = useCallback(() => {
    onSelect({
      dossierId,
      segmentId,
      runId: run.id
    });
  }, [dossierId, segmentId, run.id, onSelect]);

  // ============================================================================
  // RENDER
  // ============================================================================

  return (
    <div className="run-item-container">
      {/* Main run row */}
      <div
        className={`run-item ${isSelected ? 'selected' : ''}`}
        onClick={handleClick}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        {/* Expand/collapse button */}
        <div className="run-indent">
          <button
            className="run-expand-btn"
            onClick={(e) => {
              e.stopPropagation();
              onToggle();
            }}
            aria-label={isExpanded ? 'Collapse run' : 'Expand run'}
          >
            {isExpanded ? '▼' : '▶'}
          </button>
        </div>

        {/* Run icon */}
        <div className="run-icon">
          ▶️
        </div>

        {/* Run info */}
        <div className="run-info">
          <div className="run-name">
            Run {run.position}
          </div>
          <div className="run-details">
            <span className="run-date">{formatDate(run.metadata?.createdAt || new Date())}</span>
            <span className="run-stats">
              {stats.drafts} drafts • {formatSize(stats.totalSize)}
            </span>
            {bestDraft && (
              <span className="run-best-indicator">⭐ Best</span>
            )}
          </div>
        </div>

        {/* Action buttons (visible on hover) */}
        {(isHovered || isSelected) && (
          <div className="run-actions">
            <button
              className="run-action-btn"
              onClick={(e) => {
                e.stopPropagation();
                onAction('add_draft');
              }}
              title="Add draft"
            >
              ➕
            </button>
            <button
              className="run-action-btn danger"
              onClick={(e) => {
                e.stopPropagation();
                onAction('delete_run');
              }}
              title="Delete run"
            >
              🗑️
            </button>
          </div>
        )}
      </div>

      {/* Expanded content */}
      {isExpanded && (
        <div className="run-expanded-content">
          {/* Drafts list */}
          <div className="run-drafts">
            {(run.drafts?.length || 0) === 0 ? (
              <div className="no-drafts">
                <span className="no-drafts-icon">📄</span>
                <span className="no-drafts-text">No drafts yet</span>
                <button
                  className="add-first-draft-btn"
                  onClick={() => onAction('add_draft')}
                >
                  Add Draft
                </button>
              </div>
            ) : (
              (run.drafts || []).map((draft) => (
                <DraftItem
                  key={draft.id}
                  draft={draft}
                  runId={run.id}
                  segmentId={segmentId}
                  dossierId={dossierId}
                  isSelected={selectedPath.draftId === draft.id}
                  selectedPath={selectedPath}
                  onSelect={(path) => onSelect(path)}
                  onAction={(action, data) => onAction(action, {
                    ...data,
                    draftId: draft.id
                  })}
                />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};
