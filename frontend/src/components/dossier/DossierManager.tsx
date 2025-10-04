// ============================================================================
// DOSSIER MANAGER - MAIN CONTAINER COMPONENT
// ============================================================================
// Elite modular architecture - transforms Session Log into Dossier Manager
// Features: hierarchical navigation, optimistic updates, error recovery
// ============================================================================

import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { dossierHighlightBus } from '../../services/dossier/dossierHighlightBus';
import { DossierManagerProps, DossierPath } from '../../types/dossier';
import { useDossierManager, useDossierKeyboardNavigation } from '../../hooks/useDossierManager';
import { DossierList } from './DossierList';
import { DossierHeader } from './DossierHeader';
import { DossierFooter } from './DossierFooter';
import { DossierSearch } from './DossierSearch';
import { DossierContextMenu } from './DossierContextMenu';
import { ConfirmDeleteModal } from './modals/ConfirmDeleteModal';
import { dossierApi } from '../../services/dossier/dossierApi';

// ============================================================================
// MAIN DOSSIER MANAGER COMPONENT
// ============================================================================

export const DossierManager: React.FC<DossierManagerProps> = ({
  onSelectionChange,
  initialSelection,
  onProcessingComplete,
  className = '',
  onViewRequest,
  currentDisplayPath
}) => {
  // ============================================================================
  // DEBUG LOGGING
  // ============================================================================

  // Suppress frequent render log

  // ============================================================================
  // STATE MANAGEMENT
  // ============================================================================

  const {
    state,
    filteredDossiers,
    isLoading,
    hasError,
    loadDossiers,
    loadMoreDossiers,
    hasMore,
    createDossier,
    updateDossier,
    deleteDossier,
    selectPath,
    expandItem,
    collapseItem,
    toggleExpand,
    setSearchQuery,
    setSortBy,
    selectItem,
    deselectItem,
    clearSelection,
    bulkDelete,
    refreshDossiersSoft,
    refreshDossierById
  } = useDossierManager();

  // Reduce state spam; keep actionable logs elsewhere

  // Local UI state
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string; type: string } | null>(null);
  const [searchFocused, setSearchFocused] = useState(false);
  const [hoverHighlightId, setHoverHighlightId] = useState<string | null>(null);

  // Subscribe to hover highlight bus
  useEffect(() => {
    const unsubscribe = dossierHighlightBus.subscribe(setHoverHighlightId);
    return unsubscribe;
  }, []);

  // Listen for global dossier refresh events (soft merge) and persist scroll
  useEffect(() => {
    // Try to find the scrollable container (prefer .dossier-list; fall back to items container)
    let listEl = document.querySelector('.dossier-list') as HTMLDivElement | null;
    if (!listEl) {
      listEl = document.querySelector('.dossier-items-container') as HTMLDivElement | null;
    }
    const SCROLL_KEY = 'dossierManager.scrollTop';
    try {
      const saved = window.sessionStorage.getItem(SCROLL_KEY);
      if (saved && listEl) listEl.scrollTop = parseInt(saved, 10) || 0;
    } catch {}

    const saveScroll = () => {
      try {
        const n = listEl?.scrollTop || 0;
        window.sessionStorage.setItem(SCROLL_KEY, String(n));
      } catch {}
    };
    listEl?.addEventListener('scroll', saveScroll);

    // Debounced soft refresh helper
    const debounceRef = { current: null as number | null };
    const safeSoftRefresh = () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
      debounceRef.current = window.setTimeout(() => {
        try { refreshDossiersSoft(); } catch (e) { console.warn('⚠️ DossierManager: soft refresh failed', e); }
      }, 250);
    };

    // Fallback polling (2.5s) for up to 60s
    const pollState = { timer: null as number | null, ticks: 0 };
    const startFallbackPoll = () => {
      if (pollState.timer) return;
      pollState.ticks = 0;
      pollState.timer = window.setInterval(() => {
        pollState.ticks += 1;
        try { refreshDossiersSoft(); } catch {}
        if (pollState.ticks >= 24) {
          if (pollState.timer) window.clearInterval(pollState.timer);
          pollState.timer = null;
        }
      }, 2500);
    };

    const handler = () => {
      try { safeSoftRefresh(); } catch (e) { console.warn('⚠️ DossierManager: failed soft refresh on event', e); }
    };
    document.addEventListener('dossiers:refresh', handler);

    // Targeted single dossier refresh support
    const singleHandler = (ev: Event) => {
      try {
        const d: any = (ev as CustomEvent)?.detail;
        if (d?.dossierId) {
          // Soft refresh for list, plus targeted fetch to immediately merge updated versions
          safeSoftRefresh();
          try { (async () => { await refreshDossierById(d.dossierId); })(); } catch {}
        }
      } catch (e) { console.warn('⚠️ DossierManager: failed single dossier refresh', e); }
    };
    document.addEventListener('dossier:refreshOne', singleHandler as any);

    let es: EventSource | null = null;
    let reconnectTimer: number | null = null;
    const connect = () => {
      try {
        es = new EventSource('http://localhost:8000/api/dossier/events');
        es.onmessage = (ev) => {
          try {
            const data = JSON.parse(ev.data || '{}');
            if (data && data.type === 'dossier:update') {
              safeSoftRefresh();
            }
          } catch {}
        };
        es.onerror = () => {
          try { es && es.close(); } catch {}
          es = null;
          startFallbackPoll();
          if (reconnectTimer) window.clearTimeout(reconnectTimer);
          reconnectTimer = window.setTimeout(() => { if (!es) connect(); }, 2000);
        };
      } catch {
        startFallbackPoll();
        if (reconnectTimer) window.clearTimeout(reconnectTimer);
        reconnectTimer = window.setTimeout(() => connect(), 2000);
      }
    };
    connect();

    return () => {
      document.removeEventListener('dossiers:refresh', handler);
      document.removeEventListener('dossier:refreshOne', singleHandler as any);
      try { es && es.close(); } catch {}
      es = null;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      if (pollState.timer) window.clearInterval(pollState.timer);
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
      listEl?.removeEventListener('scroll', saveScroll);
    };
  }, [refreshDossiersSoft]);

  // ============================================================================
  // SELECTION HANDLING
  // ============================================================================

  const handleSelectionChange = useCallback((path: DossierPath) => {
    selectPath(path);
    onSelectionChange?.(path);
  }, [selectPath, onSelectionChange]);

  // ============================================================================
  // ACTION HANDLERS
  // ============================================================================

  const handleItemAction = useCallback(async (action: string, data?: any) => {
    try {
      switch (action) {
        case 'create_dossier':
          // Create a new dossier directly with a default title
          await createDossier({ title: `Dossier ${new Date().toLocaleDateString()}` });
          break;

        case 'rename_dossier':
          if (data?.targetId && data?.newName) {
            // Handle inline renaming from DossierItem
            console.log('📝 Renaming dossier:', data.targetId, 'to:', data.newName);
            await updateDossier(data.targetId, { title: data.newName });
            // Don't call loadDossiers() immediately - let optimistic update show the change
            // The optimistic update should make the change visible instantly
          }
          break;
        case 'add_segment':
          if (data?.targetId) {
            await dossierApi.createSegment(data.targetId, { name: `Segment ${(state.dossiers.find(d=>d.id===data.targetId)?.segments?.length||0)+1}` });
            await loadDossiers();
          }
          break;

        case 'rename_segment':
          if (data?.segmentId && data?.newName) {
            await dossierApi.updateSegment(data.segmentId, { name: data.newName });
            await loadDossiers();
          }
          break;

        case 'add_run':
          // TODO: Implement add run functionality
          console.log('📝 Add run action triggered:', data);
          // For now, just show a message that this feature is coming soon
          alert('Add run functionality coming soon!');
          break;

        case 'delete_segment':
          if (data?.segmentId) {
            await dossierApi.deleteSegment(data.segmentId);
            await loadDossiers();
          }
          break;

        case 'delete':
          if (data?.targetId && data?.targetName) {
            setDeleteTarget({
              id: data.targetId,
              name: data.targetName,
              type: data.targetType || 'item'
            });
            setShowDeleteModal(true);
          }
          break;

        case 'duplicate':
          if (data?.targetId) {
            const sourceDossier = state.dossiers.find(d => d.id === data.targetId);
            if (sourceDossier) {
              await createDossier({
                title: `${(sourceDossier as any).title || sourceDossier.name} (Copy)`,
                description: (sourceDossier as any).description
              });
            }
          }
          break;

        case 'expand_all':
          state.dossiers.forEach(dossier => {
            expandItem(dossier.id);
            dossier.segments.forEach(segment => {
              expandItem(segment.id);
            });
          });
          break;

        case 'collapse_all':
          state.dossiers.forEach(dossier => {
            collapseItem(dossier.id);
          });
          break;

        case 'focus_search':
          setSearchFocused(true);
          break;

        case 'delete_selected':
          if (state.selectedItems.size > 0) {
            const selectedArray = Array.from(state.selectedItems);
            await bulkDelete(selectedArray);
            clearSelection();
          }
          break;

        default:
          console.warn('Unknown action:', action);
      }
    } catch (error) {
      console.error('Action failed:', error);
      // Error handling is managed by the hook's optimistic updates
    }
  }, [
    state.dossiers,
    state.selectedItems,
    updateDossier,
    createDossier,
    bulkDelete,
    clearSelection,
    expandItem,
    collapseItem
  ]);

  // ============================================================================
  // EFFECTS
  // ============================================================================

  // Removed effect that reloaded dossiers on every render due to function identity changes

  // ============================================================================
  // MODAL HANDLERS
  // ============================================================================


  const handleConfirmDelete = useCallback(async () => {
    if (deleteTarget) {
      try {
        await deleteDossier(deleteTarget.id);
        setShowDeleteModal(false);
        setDeleteTarget(null);
      } catch (error) {
        console.error('Failed to delete:', error);
      }
    }
  }, [deleteTarget, deleteDossier]);

  // ============================================================================
  // KEYBOARD NAVIGATION
  // ============================================================================

  useDossierKeyboardNavigation(handleItemAction);

  // ============================================================================
  // COMPUTED VALUES
  // ============================================================================

  const selectedDossier = useMemo(() => {
    return (state.dossiers || []).find(d => d.id === state.selectedPath.dossierId);
  }, [state.dossiers, state.selectedPath.dossierId]);

  const stats = useMemo(() => {
    const dossiers = state.dossiers || [];

    const result = {
      totalDossiers: dossiers.length,
      totalSegments: dossiers.reduce((sum, d) => sum + (d.segments?.length || 0), 0),
      totalRuns: dossiers.reduce((sum, d) =>
        sum + (d.segments || []).reduce((segSum, s) => segSum + (s.runs?.length || 0), 0), 0),
      totalDrafts: dossiers.reduce((sum, d) =>
        sum + (d.segments || []).reduce((segSum, s) =>
          segSum + (s.runs || []).reduce((runSum, r) => runSum + (r.drafts?.length || 0), 0), 0), 0)
    };
    return result;
  }, [state.dossiers]);

  // ============================================================================
  // RENDER
  // ============================================================================

  return (
    <div
      className={`dossier-manager ${className}`}
      onClick={() => {
        // Clicking empty space clears persistent highlight
        selectPath({});
      }}
    >
      {/* Header with controls */}
      <DossierHeader
        selectedDossier={selectedDossier}
        onCreateDossier={() => {
          createDossier({ title: `Dossier ${new Date().toLocaleDateString()}` });
        }}
        onRefresh={loadDossiers}
        stats={stats}
      />

      {/* Search and filter controls */}
      <DossierSearch
        query={state.searchQuery}
        onQueryChange={setSearchQuery}
        sortBy={state.sortBy}
        onSortChange={setSortBy}
        isFocused={searchFocused}
        onFocusChange={setSearchFocused}
      />

      {/* Main dossier list */}
      <DossierList
        dossiers={filteredDossiers}
        selectedPath={state.selectedPath}
        currentDisplayPath={currentDisplayPath}
        expandedItems={state.expandedItems}
        selectedItems={state.selectedItems}
        isLoading={isLoading}
        error={state.errorStates.dossiers}
        onSelectionChange={handleSelectionChange}
        onToggleExpand={toggleExpand}
        onItemAction={handleItemAction}
        onSelectItem={selectItem}
        onDeselectItem={deselectItem}
        onViewRequest={onViewRequest}
        loadMoreDossiers={loadMoreDossiers}
        hasMore={hasMore}
      />

      {/* Footer with bulk actions */}
      {state.selectedItems.size > 0 && (
        <DossierFooter
          selectedCount={state.selectedItems.size}
          onBulkDelete={async () => {
            const selectedArray = Array.from(state.selectedItems);
            await bulkDelete(selectedArray);
            clearSelection();
          }}
          onClearSelection={clearSelection}
        />
      )}

      {/* Context menu */}
      <DossierContextMenu
        selectedItems={state.selectedItems}
        onAction={handleItemAction}
      />

      {/* Modals */}
      {showDeleteModal && deleteTarget && (
        <ConfirmDeleteModal
          itemName={deleteTarget.name}
          itemType={deleteTarget.type}
          onConfirm={handleConfirmDelete}
          onCancel={() => {
            setShowDeleteModal(false);
            setDeleteTarget(null);
          }}
        />
      )}

      {/* Error state */}
      {hasError && !isLoading && (
        <div className="dossier-error-state">
          <p>⚠️ Error loading dossiers</p>
          <button onClick={loadDossiers}>Retry</button>
        </div>
      )}
    </div>
  );
};

// ============================================================================
// COMPONENT EXPORTS
// ============================================================================

export default DossierManager;
