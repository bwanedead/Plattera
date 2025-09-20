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
  currentDisplayPath?: DossierPath;
  isMultiSelected?: boolean;
  expandedItems: Set<string>;
  onToggleExpand: (id: string) => void;
  onSelect: (path: DossierPath) => void;
  onAction: (action: string, data?: any) => void;
  onMultiSelect?: () => void;
  classNameOverride?: string;
  onViewRequest?: (path: DossierPath) => void;
}

export const DossierItem: React.FC<DossierItemProps> = ({
  dossier,
  isExpanded,
  isSelected,
  selectedPath,
  currentDisplayPath,
  isMultiSelected = false,
  expandedItems,
  onToggleExpand,
  onSelect,
  onAction,
  onMultiSelect,
  classNameOverride,
  onViewRequest
}) => {
  // ============================================================================
  // DEBUGGING
  // ============================================================================

  // Render log removed to reduce console noise

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
  const [editValue, setEditValue] = useState(dossier?.title || dossier?.name || '');
  const [isHovered, setIsHovered] = useState(false);

  // ============================================================================
  // COMPUTED VALUES
  // ============================================================================



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


  const handleExpandWithAutoExpansion = useCallback(() => {
    // First, toggle the dossier expansion
    onToggleExpand(dossier.id);

    // Check for auto-expansion: if dossier has exactly 1 segment with exactly 1 run,
    // auto-expand all the way down to drafts
    const segments = dossier.segments || [];
    if (segments.length === 1) {
      const segment = segments[0];
      const runs = segment.runs || [];
      if (runs.length === 1) {
        // Auto-expand: dossier -> segment -> run (which shows drafts)
        setTimeout(() => {
          onToggleExpand(segment.id);
          onToggleExpand(runs[0].id);
        }, 0);
      }
    }
  }, [dossier.id, dossier.segments, onToggleExpand]);

  const handleDoubleClick = useCallback(() => {
    // Double-click now triggers viewing the dossier in ResultsViewer
    onViewRequest?.({ dossierId: dossier.id });
  }, [dossier.id, onViewRequest]);

  const handleEditSubmit = useCallback(() => {
    const trimmedValue = editValue.trim();
    const currentName = dossier.title || dossier.name;
    if (trimmedValue && trimmedValue !== currentName) {
      console.log('📝 DossierItem: Submitting rename for dossier:', dossier.id, 'from:', currentName, 'to:', trimmedValue);
      onAction('rename_dossier', { targetId: dossier.id, newName: trimmedValue, currentName });
    }
    setIsEditing(false);
    setEditValue(dossier.title || dossier.name || '');
  }, [editValue, dossier.title, dossier.name, dossier.id, onAction]);

  const handleEditCancel = useCallback(() => {
    setIsEditing(false);
    setEditValue(dossier.title || dossier.name || '');
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
    // Show context menu with options
    const choice = window.prompt(`Choose action for "${dossier.title || dossier.name}":\n1. Rename\n2. Delete\n\nEnter 1 or 2:`);

    if (choice === '1') {
      // Rename mode
      const currentName = dossier.title || dossier.name || '';
      setEditValue(currentName);
      setIsEditing(true);
    } else if (choice === '2') {
      // Delete with confirmation
      if (window.confirm(`Delete dossier "${dossier.title || dossier.name}"? This will permanently remove all associated data.`)) {
        onAction('delete', { dossierId: dossier.id, dossierName: dossier.title || dossier.name });
      }
    }
  }, [dossier.title, dossier.name, dossier.id, onAction]);

  // ============================================================================
  // RENDER
  // ============================================================================

  return (
    <div className="dossier-item-container">
      {/* Main dossier row */}
      <div
        className={`dossier-item ${(isSelected || currentDisplayPath?.dossierId === dossier.id) ? 'selected' : ''} ${isMultiSelected ? 'multi-selected' : ''} ${classNameOverride || ''}`}
        onClick={(e) => {
          // Clicking the header selects and toggles expand/collapse for responsiveness
          handleClick(e);
          handleExpandWithAutoExpansion();
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
            handleExpandWithAutoExpansion();
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

        {/* Action buttons (visible on hover) */}
        {(isHovered || isSelected) && (
          <div className="dossier-actions">
            <button
              className="dossier-action-btn"
              onClick={(e) => {
                e.stopPropagation();
                onViewRequest?.({ dossierId: dossier.id });
              }}
              title="View dossier"
            >
              View
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
                  currentDisplayPath={currentDisplayPath}
                  expandedItems={expandedItems}
                  onToggleExpand={onToggleExpand}
                  onSelect={(path) => onSelect(path)}
                  onAction={(action, data) => onAction(action, {
                    ...data,
                    segmentId: segment.id,
                    segmentName: segment.name
                  })}
                  onViewRequest={onViewRequest}
                />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};
