// ============================================================================
// DOSSIER MANAGER - MAIN CONTAINER COMPONENT
// ============================================================================
// Elite modular architecture - transforms Session Log into Dossier Manager
// Features: hierarchical navigation, optimistic updates, error recovery
// ============================================================================

import React, { useState, useCallback, useMemo, useEffect } from 'react';
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
  onViewRequest
}) => {
  // ============================================================================
  // DEBUG LOGGING
  // ============================================================================

  console.log('🎯 DossierManager rendering');

  // ============================================================================
  // STATE MANAGEMENT
  // ============================================================================

  const {
    state,
    filteredDossiers,
    isLoading,
    hasError,
    loadDossiers,
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
    bulkDelete
  } = useDossierManager();

  console.log('📊 DossierManager state:', {
    isLoading,
    hasError,
    dossierCount: filteredDossiers.length,
    error: state.errorStates.dossiers
  });

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

  // Refresh dossiers when processing completes
  useEffect(() => {
    if (onProcessingComplete) {
      console.log('🔄 Processing completed - refreshing dossiers');
      loadDossiers();
    }
  }, [onProcessingComplete, loadDossiers]);

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
    console.log('📊 Calculating stats - state.dossiers:', state.dossiers);
    console.log('📊 Calculating stats - state.dossiers type:', typeof state.dossiers);
    const dossiers = state.dossiers || [];
    console.log('📊 Calculating stats - dossiers array length:', dossiers.length);

    const result = {
      totalDossiers: dossiers.length,
      totalSegments: dossiers.reduce((sum, d) => sum + (d.segments?.length || 0), 0),
      totalRuns: dossiers.reduce((sum, d) =>
        sum + (d.segments || []).reduce((segSum, s) => segSum + (s.runs?.length || 0), 0), 0),
      totalDrafts: dossiers.reduce((sum, d) =>
        sum + (d.segments || []).reduce((segSum, s) =>
          segSum + (s.runs || []).reduce((runSum, r) => runSum + (r.drafts?.length || 0), 0), 0), 0)
    };

    console.log('📊 Stats calculation result:', result);
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
        onCreateDossier={async () => {
          await createDossier({ title: `Dossier ${new Date().toLocaleDateString()}` });
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
