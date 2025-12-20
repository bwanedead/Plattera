// ============================================================================
// DOSSIER ITEM COMPONENT
// ============================================================================
// Displays individual dossier with expandable segments, runs, and drafts
// Features: inline editing, context menus, drag & drop preparation
// ============================================================================

import React, { useState, useCallback, useEffect } from 'react';
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
  isFinalized?: boolean;
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
  onViewRequest,
  isFinalized
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

  // ==========================================================================
  // CONTEXT MENU STATE
  // ==========================================================================

  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPos, setMenuPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

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
    setMenuPos({ x: event.clientX, y: event.clientY });
    setMenuOpen(true);
  }, []);

  // Close context menu on outside click / escape / second contextmenu
  useEffect(() => {
    if (!menuOpen) return;
    const onClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest?.('.dossier-context-menu')) {
        setMenuOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuOpen(false);
    };
    const onCtx = () => setMenuOpen(false);
    document.addEventListener('click', onClick, true);
    document.addEventListener('keydown', onKey, true);
    document.addEventListener('contextmenu', onCtx, true);
    return () => {
      document.removeEventListener('click', onClick, true);
      document.removeEventListener('keydown', onKey, true);
      document.removeEventListener('contextmenu', onCtx, true);
    };
  }, [menuOpen]);

  const doRename = () => {
    setMenuOpen(false);
    const currentName = dossier.title || dossier.name || '';
    setEditValue(currentName);
    setIsEditing(true);
  };

  const doDelete = () => {
    setMenuOpen(false);
    onAction('delete', { dossierId: dossier.id, dossierName: dossier.title || dossier.name });
  };

  const doFinalize = () => {
    setMenuOpen(false);
    onAction('finalize_dossier', { targetId: dossier.id });
  };

  const doUnfinalize = () => {
    setMenuOpen(false);
    onAction('unfinalize_dossier', { targetId: dossier.id });
  };

  // ============================================================================
  // RENDER
  // ============================================================================

  return (
    <div className="dossier-item-container">
      {/* Main dossier row */}
      <div
        className={`dossier-item ${(isSelected || currentDisplayPath?.dossierId === dossier.id) ? 'selected' : ''} ${isMultiSelected ? 'multi-selected' : ''} ${classNameOverride || ''}`}
        data-finalized={isFinalized ? true : undefined}
        style={isFinalized ? { border: '1px solid #d4af37', boxShadow: '0 0 0 1px rgba(212,175,55,0.25) inset' } : undefined}
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

        {/* Finalized badge (non-intrusive) */}
        {isFinalized && (
          <span className="dossier-badges" style={{ marginLeft: 8, display: 'inline-flex', gap: 6 }}>
            <span style={{
              fontSize: 11,
              padding: '2px 6px',
              borderRadius: 10,
              background: 'rgba(212,175,55,0.12)',
              color: '#e7c65c',
              border: '1px solid rgba(212,175,55,0.35)'
            }}>Finalized</span>
          </span>
        )}

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

      {/* Per-item right-click menu */}
      {menuOpen && (
        <div
          className="dossier-context-menu"
          role="menu"
          style={{
            position: 'fixed',
            top: menuPos.y,
            left: menuPos.x,
            zIndex: 10000,
            display: 'inline-block',
            background: '#1f1f1f',
            border: '1px solid #333',
            boxShadow: '0 4px 18px rgba(0,0,0,0.35)',
            borderRadius: 4,
            padding: '4px 0',
            color: '#eee',
            fontSize: 12,
            lineHeight: 1.3,
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            role="menuitem"
            className="ctx-item"
            onClick={doRename}
            style={{
              width: '100%',
              textAlign: 'left',
              padding: '6px 12px',
              border: 'none',
              color: 'inherit',
              cursor: 'pointer',
            }}
          >
            Rename
          </button>
          <button
            role="menuitem"
            className="ctx-item"
            onClick={doDelete}
            style={{
              width: '100%',
              textAlign: 'left',
              padding: '6px 12px',
              border: 'none',
              color: '#ffb3b3',
              cursor: 'pointer',
            }}
          >
            Delete
          </button>
          {!isFinalized && (
          <button
            role="menuitem"
            className="ctx-item"
            onClick={doFinalize}
            style={{
              width: '100%',
              textAlign: 'left',
              padding: '6px 12px',
              border: 'none',
              color: '#b3e5ff',
              cursor: 'pointer',
            }}
          >
            Finalize
          </button>
          )}
          {isFinalized && <div style={{ height: 1, background: '#2a2a2a', margin: '6px 0' }} />}
          {isFinalized && (
          <button
            role="menuitem"
            className="ctx-item"
            onClick={doUnfinalize}
            style={{
              width: '100%',
              textAlign: 'left',
              padding: '6px 12px',
              border: 'none',
              color: '#ffd6a5',
              cursor: 'pointer',
            }}
          >
            Unfinalize
          </button>
          )}
        </div>
      )}

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
