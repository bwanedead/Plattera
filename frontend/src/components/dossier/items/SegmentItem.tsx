// ============================================================================
// SEGMENT ITEM COMPONENT
// ============================================================================
// Displays document segments with expandable runs and drafts
// ============================================================================

import React, { useState, useCallback } from 'react';
import { Segment, DossierPath } from '../../../types/dossier';
import { RunItem } from './RunItem';

interface SegmentItemProps {
  segment: Segment;
  dossierId: string;
  isExpanded: boolean;
  isSelected: boolean;
  selectedPath: DossierPath;
  onToggle: () => void;
  onSelect: (path: DossierPath) => void;
  onAction: (action: string, data?: any) => void;
}

export const SegmentItem: React.FC<SegmentItemProps> = ({
  segment,
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

  if (!segment) {
    console.warn('🚨 SegmentItem: No segment provided');
    return null;
  }

  // ============================================================================
  // LOCAL STATE
  // ============================================================================

  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(segment.name);
  const [isHovered, setIsHovered] = useState(false);

  // ============================================================================
  // COMPUTED VALUES
  // ============================================================================

  const stats = {
    runs: segment.runs?.length || 0,
    drafts: (segment.runs || []).reduce((sum, run) => sum + (run.drafts?.length || 0), 0),
    totalSize: (segment.runs || []).reduce((sum, run) =>
      sum + (run.drafts || []).reduce((draftSum, draft) => draftSum + (draft.metadata?.sizeBytes || 0), 0), 0)
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  };

  // ============================================================================
  // EVENT HANDLERS
  // ============================================================================

  const handleClick = useCallback(() => {
    onSelect({
      dossierId,
      segmentId: segment.id
    });
  }, [dossierId, segment.id, onSelect]);

  const handleDoubleClick = useCallback(() => {
    setIsEditing(true);
  }, []);

  const handleEditSubmit = useCallback(() => {
    const trimmedValue = editValue.trim();
    if (trimmedValue && trimmedValue !== segment.name) {
      onAction('rename_segment', { newName: trimmedValue });
    }
    setIsEditing(false);
    setEditValue(segment.name);
  }, [editValue, segment.name, onAction]);

  const handleEditCancel = useCallback(() => {
    setIsEditing(false);
    setEditValue(segment.name);
  }, [segment.name]);

  const handleKeyDown = useCallback((event: React.KeyboardEvent) => {
    if (event.key === 'Enter') {
      handleEditSubmit();
    } else if (event.key === 'Escape') {
      handleEditCancel();
    }
  }, [handleEditSubmit, handleEditCancel]);

  // ============================================================================
  // RENDER
  // ============================================================================

  return (
    <div className="segment-item-container">
      {/* Main segment row */}
      <div
        className={`segment-item ${isSelected ? 'selected' : ''}`}
        onClick={handleClick}
        onDoubleClick={handleDoubleClick}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        {/* Expand/collapse button */}
        <div className="segment-indent">
          <button
            className="segment-expand-btn"
            onClick={(e) => {
              e.stopPropagation();
              onToggle();
            }}
            aria-label={isExpanded ? 'Collapse segment' : 'Expand segment'}
          >
            {isExpanded ? '▼' : '▶'}
          </button>
        </div>

        {/* Segment icon */}
        <div className="segment-icon">
          📝
        </div>

        {/* Segment name (editable) */}
        <div className="segment-name-section">
          {isEditing ? (
            <input
              type="text"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onBlur={handleEditSubmit}
              onKeyDown={handleKeyDown}
              className="segment-name-input"
              autoFocus
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <span className="segment-name">
              {segment.name}
            </span>
          )}
        </div>

        {/* Statistics */}
        <div className="segment-stats">
          <span className="stat-runs">{stats.runs} runs</span>
          <span className="stat-drafts">{stats.drafts} drafts</span>
          <span className="stat-size">{formatSize(stats.totalSize)}</span>
        </div>

        {/* Action buttons (visible on hover) */}
        {(isHovered || isSelected) && (
          <div className="segment-actions">
            <button
              className="segment-action-btn"
              onClick={(e) => {
                e.stopPropagation();
                onAction('add_run');
              }}
              title="Add run"
            >
              ➕
            </button>
            <button
              className="segment-action-btn danger"
              onClick={(e) => {
                e.stopPropagation();
                onAction('delete_segment');
              }}
              title="Delete segment"
            >
              🗑️
            </button>
          </div>
        )}
      </div>

      {/* Expanded content */}
      {isExpanded && (
        <div className="segment-expanded-content">
          {/* Runs list */}
          <div className="segment-runs">
            {(segment.runs?.length || 0) === 0 ? (
              <div className="no-runs">
                <span className="no-runs-icon">▶️</span>
                <span className="no-runs-text">No runs yet</span>
                <button
                  className="add-first-run-btn"
                  onClick={() => onAction('add_run')}
                >
                  Add Run
                </button>
              </div>
            ) : (
              segment.runs.map((run) => (
                <RunItem
                  key={run.id}
                  run={run}
                  segmentId={segment.id}
                  dossierId={dossierId}
                  isExpanded={selectedPath.runId === run.id}
                  isSelected={selectedPath.runId === run.id}
                  selectedPath={selectedPath}
                  onToggle={() => onAction('toggle_run', { runId: run.id })}
                  onSelect={(path) => onSelect(path)}
                  onAction={(action, data) => onAction(action, {
                    ...data,
                    runId: run.id
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
