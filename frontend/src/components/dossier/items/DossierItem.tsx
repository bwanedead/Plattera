// ============================================================================
// DOSSIER ITEM COMPONENT
// ============================================================================
// Displays individual dossier with expandable segments, runs, and drafts
// Features: inline editing, context menus, drag & drop preparation
// ============================================================================

import React, { useState, useCallback } from 'react';
import { Dossier, DossierPath } from '../../../types/dossier';
import { SegmentItem } from './SegmentItem';

interface DossierItemProps {
  dossier: Dossier;
  isExpanded: boolean;
  isSelected: boolean;
  selectedPath: DossierPath;
  isMultiSelected?: boolean;
  expandedItems: Set<string>;
  onToggleExpand: (id: string) => void;
  onSelect: (path: DossierPath) => void;
  onAction: (action: string, data?: any) => void;
  onMultiSelect?: () => void;
}

export const DossierItem: React.FC<DossierItemProps> = ({
  dossier,
  isExpanded,
  isSelected,
  selectedPath,
  isMultiSelected = false,
  expandedItems,
  onToggleExpand,
  onSelect,
  onAction,
  onMultiSelect
}) => {
  // ============================================================================
  // EARLY RETURN FOR INVALID DATA
  // ============================================================================

  if (!dossier) {
    console.warn('🚨 DossierItem: No dossier provided');
    return null;
  }

  // ============================================================================
  // LOCAL STATE
  // ============================================================================

  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(dossier?.name || '');
  const [isHovered, setIsHovered] = useState(false);

  // ============================================================================
  // COMPUTED VALUES
  // ============================================================================

  const stats = dossier ? {
    segments: dossier.segments?.length || 0,
    runs: (dossier.segments || []).reduce((sum, segment) => sum + (segment.runs?.length || 0), 0),
    drafts: (dossier.segments || []).reduce((sum, segment) =>
      sum + (segment.runs || []).reduce((runSum, run) => runSum + (run.drafts?.length || 0), 0), 0),
    totalSize: dossier.metadata?.totalSizeBytes || 0
  } : {
    segments: 0,
    runs: 0,
    drafts: 0,
    totalSize: 0
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  };

  // ============================================================================
  // EVENT HANDLERS
  // ============================================================================

  const handleClick = useCallback((event: React.MouseEvent) => {
    if (event.ctrlKey || event.metaKey) {
      onMultiSelect?.();
    } else {
      onSelect({ dossierId: dossier.id });
    }
  }, [dossier.id, onSelect, onMultiSelect]);

  const handleDoubleClick = useCallback(() => {
    setIsEditing(true);
  }, []);

  const handleEditSubmit = useCallback(() => {
    const trimmedValue = editValue.trim();
    const currentName = dossier.title || dossier.name;
    if (trimmedValue && trimmedValue !== currentName) {
      onAction('rename', { newName: trimmedValue });
    }
    setIsEditing(false);
    setEditValue(currentName);
  }, [editValue, dossier.title, dossier.name, onAction]);

  const handleEditCancel = useCallback(() => {
    setIsEditing(false);
    setEditValue(dossier.title || dossier.name);
  }, [dossier.title, dossier.name]);

  const handleKeyDown = useCallback((event: React.KeyboardEvent) => {
    if (event.key === 'Enter') {
      handleEditSubmit();
    } else if (event.key === 'Escape') {
      handleEditCancel();
    }
  }, [handleEditSubmit, handleEditCancel]);

  const handleContextMenu = useCallback((event: React.MouseEvent) => {
    event.preventDefault();
    onAction('show_context_menu', {
      x: event.clientX,
      y: event.clientY,
      targetId: dossier.id,
      targetType: 'dossier'
    });
  }, [dossier.id, onAction]);

  // ============================================================================
  // RENDER
  // ============================================================================

  return (
    <div className="dossier-item-container">
      {/* Main dossier row */}
      <div
        className={`dossier-item ${isSelected ? 'selected' : ''} ${isMultiSelected ? 'multi-selected' : ''}`}
        onClick={(e) => {
          // Clicking the header selects and toggles expand/collapse for responsiveness
          handleClick(e);
          onToggleExpand(dossier.id);
        }}
        onDoubleClick={handleDoubleClick}
        onContextMenu={handleContextMenu}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        {/* Expand/collapse button */}
        <button
          className="dossier-expand-btn"
          onClick={(e) => {
            console.log('🔘 Dossier expand button clicked for:', dossier.id);
            e.stopPropagation();
            onToggleExpand(dossier.id);
          }}
          aria-label={isExpanded ? 'Collapse dossier' : 'Expand dossier'}
        >
          {isExpanded ? '▼' : '▶'}
        </button>

        {/* Dossier icon removed for minimal aesthetic */}

        {/* Dossier name (editable) */}
        <div className="dossier-name-section">
          {isEditing ? (
            <input
              type="text"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onBlur={handleEditSubmit}
              onKeyDown={handleKeyDown}
              className="dossier-name-input"
              autoFocus
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <span className="dossier-name">
              {dossier.title || dossier.name}
            </span>
          )}
        </div>

        {/* Statistics */}
        <div className="dossier-stats">
          <span className="stat-segments">{stats.segments} segments</span>
          <span className="stat-runs">{stats.runs} runs</span>
          <span className="stat-drafts">{stats.drafts} drafts</span>
          <span className="stat-size">{formatSize(stats.totalSize)}</span>
        </div>

        {/* Action buttons (visible on hover) */}
        {(isHovered || isSelected) && (
          <div className="dossier-actions">
            <button
              className="dossier-action-btn"
              onClick={(e) => {
                e.stopPropagation();
                onAction('add_segment');
              }}
              title="Add segment"
            >
              Add
            </button>
            <button
              className="dossier-action-btn"
              onClick={(e) => {
                e.stopPropagation();
                onAction('duplicate');
              }}
              title="Duplicate dossier"
            >
              Duplicate
            </button>
            <button
              className="dossier-action-btn danger"
              onClick={(e) => {
                e.stopPropagation();
                onAction('delete');
              }}
              title="Delete dossier"
            >
              Delete
            </button>
          </div>
        )}
      </div>

      {/* Expanded content */}
      {isExpanded && (
        <div className="dossier-expanded-content">
          {/* Segments list */}
          <div className="dossier-segments">
            {(dossier.segments || []).length === 0 ? (
              <div className="no-segments">
                <span className="no-segments-text">No segments yet</span>
                <button
                  className="add-first-segment-btn"
                  onClick={() => onAction('add_segment')}
                >
                  Add Segment
                </button>
              </div>
            ) : (
              (dossier.segments || []).map((segment) => (
                <SegmentItem
                  key={segment.id}
                  segment={segment}
                  dossierId={dossier.id}
                  isExpanded={expandedItems.has(segment.id)}
                  isSelected={selectedPath.segmentId === segment.id}
                  selectedPath={selectedPath}
                  expandedItems={expandedItems}
                  onToggleExpand={onToggleExpand}
                  onSelect={(path) => onSelect(path)}
                  onAction={(action, data) => onAction(action, {
                    ...data,
                    segmentId: segment.id,
                    segmentName: segment.name
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
