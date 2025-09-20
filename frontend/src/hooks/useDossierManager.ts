// ============================================================================
// DOSSIER MANAGER HOOK - ELITE STATE MANAGEMENT
// ============================================================================
// Comprehensive state management for the Dossier System
// Features: optimistic updates, error recovery, caching, offline support
// ============================================================================

import { useReducer, useCallback, useEffect, useMemo, useState } from 'react';
import { useProcessingPoller } from './useProcessingPoller';
import { Dossier, DossierPath, DossierManagerState, DossierAction, SortOption } from '../types/dossier';
import { dossierApi, DossierApiError } from '../services/dossier/dossierApi';

// ============================================================================
// INITIAL STATE
// ============================================================================

const initialState: DossierManagerState = {
  dossiers: [],
  selectedPath: {},
  expandedItems: new Set(),
  loadingStates: {
    dossiers: false,
    segments: {},
    runs: {},
    drafts: {}
  },
  errorStates: {
    dossiers: null,
    segments: {},
    runs: {},
    drafts: {}
  },
  searchQuery: '',
  sortBy: 'date',
  selectedItems: new Set()
};

// ============================================================================
// SESSION STORAGE PERSISTENCE
// ============================================================================

const SESSION_KEYS = {
  expanded: 'dossierManager.expandedItems',
  selectedPath: 'dossierManager.selectedPath'
} as const;

function loadExpandedFromSession(): Set<string> {
  if (typeof window === 'undefined') return new Set();
  try {
    const raw = window.sessionStorage.getItem(SESSION_KEYS.expanded);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return new Set(parsed.filter((x) => typeof x === 'string'));
    return new Set();
  } catch {
    return new Set();
  }
}

function loadSelectedPathFromSession(): DossierPath {
  if (typeof window === 'undefined') return {};
  try {
    const raw = window.sessionStorage.getItem(SESSION_KEYS.selectedPath);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    // Only allow known keys
    const path: DossierPath = {
      dossierId: typeof parsed?.dossierId === 'string' ? parsed.dossierId : undefined,
      segmentId: typeof parsed?.segmentId === 'string' ? parsed.segmentId : undefined,
      runId: typeof parsed?.runId === 'string' ? parsed.runId : undefined,
      draftId: typeof parsed?.draftId === 'string' ? parsed.draftId : undefined
    };
    return path;
  } catch {
    return {};
  }
}

function saveExpandedToSession(expanded: Set<string>) {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(SESSION_KEYS.expanded, JSON.stringify(Array.from(expanded)));
  } catch {}
}

function saveSelectedPathToSession(path: DossierPath) {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(SESSION_KEYS.selectedPath, JSON.stringify(path || {}));
  } catch {}
}

// ============================================================================
// REDUCER - PURE STATE TRANSITIONS
// ============================================================================

function dossierReducer(state: DossierManagerState, action: DossierAction): DossierManagerState {
  switch (action.type) {
    case 'SELECT_PATH':
      return {
        ...state,
        selectedPath: action.payload
      };

    case 'EXPAND_ITEM':
      return {
        ...state,
        expandedItems: new Set([...state.expandedItems, action.payload])
      };

    case 'COLLAPSE_ITEM':
      const newExpanded = new Set(state.expandedItems);
      newExpanded.delete(action.payload);
      return {
        ...state,
        expandedItems: newExpanded
      };

    case 'TOGGLE_EXPAND':
      const toggled = new Set(state.expandedItems);
      if (toggled.has(action.payload)) {
        toggled.delete(action.payload);
      } else {
        toggled.add(action.payload);
      }
      return {
        ...state,
        expandedItems: toggled
      };

    case 'SET_LOADING':
      return {
        ...state,
        loadingStates: {
          ...state.loadingStates,
          [action.payload.key]: action.payload.loading
        }
      };

    case 'SET_ERROR':
      return {
        ...state,
        errorStates: {
          ...state.errorStates,
          [action.payload.key]: action.payload.error
        }
      };

    case 'UPDATE_DOSSIERS':
      return {
        ...state,
        dossiers: action.payload,
        loadingStates: {
          ...state.loadingStates,
          dossiers: false
        },
        errorStates: {
          ...state.errorStates,
          dossiers: null
        }
      };

    case 'ADD_DOSSIER':
      return {
        ...state,
        dossiers: [...state.dossiers, action.payload]
      };

    case 'UPDATE_DOSSIER':
      return {
        ...state,
        dossiers: state.dossiers.map(d =>
          d.id === action.payload.id ? action.payload : d
        )
      };

    case 'DELETE_DOSSIER':
      return {
        ...state,
        dossiers: state.dossiers.filter(d => d.id !== action.payload),
        selectedPath: state.selectedPath.dossierId === action.payload
          ? {}
          : state.selectedPath
      };

    case 'REMOVE_DOSSIER':
      return {
        ...state,
        dossiers: state.dossiers.filter(d => d.id !== action.payload)
      };

    case 'SET_SEARCH':
      return {
        ...state,
        searchQuery: action.payload
      };

    case 'SET_SORT':
      return {
        ...state,
        sortBy: action.payload
      };

    case 'SELECT_ITEM':
      return {
        ...state,
        selectedItems: new Set([...state.selectedItems, action.payload])
      };

    case 'DESELECT_ITEM':
      const deselected = new Set(state.selectedItems);
      deselected.delete(action.payload);
      return {
        ...state,
        selectedItems: deselected
      };

    case 'CLEAR_SELECTION':
      return {
        ...state,
        selectedItems: new Set()
      };

    default:
      return state;
  }
}

// ============================================================================
// MAIN HOOK - BUSINESS LOGIC & OPTIMISTIC UPDATES
// ============================================================================

export function useDossierManager() {
  // Initialize with session state (lazy initializer to play nicely with Fast Refresh)
  const [state, dispatch] = useReducer(
    dossierReducer,
    initialState,
    (base) => ({
      ...base,
      expandedItems: loadExpandedFromSession(),
      selectedPath: loadSelectedPathFromSession()
    })
  );

  // ============================================================================
  // OPTIMISTIC UPDATE UTILITIES
  // ============================================================================

  const executeOptimistically = useCallback(async <T>(
    optimisticAction: DossierAction,
    apiCall: () => Promise<T>,
    rollbackAction?: DossierAction
  ): Promise<T> => {
    console.log('🔄 executeOptimistically: Starting optimistic update with action:', optimisticAction.type);
    // Apply optimistic update
    dispatch(optimisticAction);
    const previousState = state;

    // Debug: Check if the optimistic update was applied
    console.log('🔄 executeOptimistically: Optimistic update applied, checking state...');
    if (optimisticAction.type === 'UPDATE_DOSSIER') {
      const updatedDossier = state.dossiers.find(d => d.id === optimisticAction.payload.id);
      console.log('🔄 executeOptimistically: Updated dossier in state:', updatedDossier?.title || updatedDossier?.name);
    }

    try {
      console.log('🔄 executeOptimistically: Calling API...');
      const result = await apiCall();
      console.log('✅ executeOptimistically: API call successful, result:', result);

      // For successful updates, ensure the change is visible by dispatching a fresh update
      if (optimisticAction.type === 'UPDATE_DOSSIER') {
        console.log('🔄 executeOptimistically: Ensuring UPDATE_DOSSIER change is visible');
        // Force a re-render by dispatching a fresh update with the result data
        if (result && typeof result === 'object' && result !== null && 'id' in result && 'title' in result) {
          dispatch({ type: 'UPDATE_DOSSIER', payload: result as unknown as Dossier });
        }
      } else if (optimisticAction.type === 'ADD_DOSSIER') {
        console.log('🔄 executeOptimistically: Ensuring ADD_DOSSIER change is visible');
        // Replace the temporary dossier with the real one from the API
        if (result && typeof result === 'object' && result !== null && 'id' in result && 'title' in result) {
          const realDossier = result as unknown as Dossier;
          // Remove the temporary dossier and add the real one
          dispatch({ type: 'REMOVE_DOSSIER', payload: optimisticAction.payload.id });
          dispatch({ type: 'ADD_DOSSIER', payload: realDossier });
        }
      }

      // Update was successful, clear any errors
      if (optimisticAction.type === 'UPDATE_DOSSIERS') {
        dispatch({ type: 'SET_ERROR', payload: { key: 'dossiers', error: null } });
      }

      return result;
    } catch (error) {
      console.error('❌ executeOptimistically: API call failed:', error);
      // Revert optimistic update
      if (rollbackAction) {
        console.log('🔄 executeOptimistically: Applying rollback action');
        dispatch(rollbackAction);
      } else {
        console.log('🔄 executeOptimistically: No rollback action, reloading dossiers');
        // Fallback: reload data
        loadDossiers();
      }

      throw error;
    }
  }, [state]);

  // ============================================================================
  // DATA LOADING
  // ============================================================================

  const loadDossiers = useCallback(async () => {
    console.log('🔄 Loading dossiers...');
    dispatch({ type: 'SET_LOADING', payload: { key: 'dossiers', loading: true } });
    dispatch({ type: 'SET_ERROR', payload: { key: 'dossiers', error: null } });

    try {
      console.log('🔄 Calling dossierApi.getDossiers()...');
      const dossiers = await dossierApi.getDossiers();
      console.log('✅ Loaded dossiers:', dossiers.length, 'dossiers');
      // Reduce noise: remove verbose per-dossier summary logging

      // Heuristic auto-reconcile: if all drafts appear completed but run status isn't, ask backend to reconcile
      try {
        const candidates = dossiers.filter(d => {
          const runs = (d.segments || []).flatMap(s => (s.runs || []));
          return runs.some(r => {
            const totalDrafts = (r.drafts || []).length || 0;
            if (totalDrafts <= 0) return false;
            const completedDrafts = (r.drafts || []).filter(dr => dr?.metadata?.status === 'completed').length;
            const status = r.metadata?.status;
            return completedDrafts >= totalDrafts && status !== 'completed';
          });
        });
        if (candidates.length > 0) {
          console.log(`🩺 Reconcile check: ${candidates.length} dossier(s) appear stale; reconciling...`);
          for (const d of candidates) {
            try {
              const res = await dossierApi.reconcileRuns(d.id);
              console.log(`🩺 Reconcile dossier ${d.id} ->`, res);
            } catch (e) {
              console.warn(`⚠️ Reconcile failed for dossier ${d.id}`, e);
            }
          }
          // Reload after reconciliation
          try {
            const refreshed = await dossierApi.getDossiers();
            console.log('✅ Reloaded dossiers after reconcile:', refreshed.length);
            dispatch({ type: 'UPDATE_DOSSIERS', payload: refreshed });
          } catch (e) {
            console.warn('⚠️ Reload after reconcile failed', e);
          }
        }
      } catch {}
      dispatch({ type: 'UPDATE_DOSSIERS', payload: dossiers });
    } catch (error) {
      // Downgrade to warn to avoid dev overlay during transient startup failures
      console.warn('⚠️ Failed to load dossiers (will show soft retry UI):', error);
      const errorMessage = error instanceof DossierApiError
        ? error.message
        : 'Failed to load dossiers';
      dispatch({ type: 'SET_ERROR', payload: { key: 'dossiers', error: errorMessage } });
      dispatch({ type: 'SET_LOADING', payload: { key: 'dossiers', loading: false } });
    }
  }, []);

  // ============================================================================
  // CRUD OPERATIONS
  // ============================================================================

  const createDossier = useCallback(async (data: { title: string; description?: string }) => {
    const tempId = `temp-${Date.now()}`;
    const tempDossier: Dossier = {
      id: tempId,
      title: data.title,
      description: data.description,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      segments: []
    };

    return executeOptimistically(
      { type: 'ADD_DOSSIER', payload: tempDossier },
      async () => {
        const realDossier = await dossierApi.createDossier(data);
        // Replace temp dossier with real one
        dispatch({ type: 'UPDATE_DOSSIER', payload: realDossier });
        dispatch({ type: 'DELETE_DOSSIER', payload: tempId });
        return realDossier;
      },
      { type: 'DELETE_DOSSIER', payload: tempId }
    );
  }, [executeOptimistically]);

  const updateDossier = useCallback(async (dossierId: string, data: Partial<Dossier>) => {
    console.log('📝 updateDossier: Starting update for dossier:', dossierId, 'with data:', data);
    const currentDossier = state.dossiers.find(d => d.id === dossierId);
    if (!currentDossier) {
      console.warn('⚠️ updateDossier: Dossier not found:', dossierId);
      return;
    }
    console.log('📝 updateDossier: Found current dossier:', currentDossier.title || currentDossier.name);

    const updatedDossier = {
      ...currentDossier,
      ...data,
      updated_at: new Date().toISOString(),
      // Ensure we create a new object reference for React to detect the change
      title: data.title || currentDossier.title || currentDossier.name
    };
    console.log('📝 updateDossier: Created updated dossier:', updatedDossier.title || updatedDossier.name);

    return executeOptimistically(
      { type: 'UPDATE_DOSSIER', payload: updatedDossier },
      () => {
        console.log('📝 updateDossier: Calling dossierApi.updateDossier with data:', data);
        return dossierApi.updateDossier(dossierId, data);
      },
      { type: 'UPDATE_DOSSIER', payload: currentDossier }
    );
  }, [state.dossiers, executeOptimistically]);

  const deleteDossier = useCallback(async (dossierId: string) => {
    const dossierToDelete = state.dossiers.find(d => d.id === dossierId);
    if (!dossierToDelete) return;

    return executeOptimistically(
      { type: 'DELETE_DOSSIER', payload: dossierId },
      () => dossierApi.deleteDossier(dossierId),
      { type: 'ADD_DOSSIER', payload: dossierToDelete }
    );
  }, [state.dossiers, executeOptimistically]);

  // ============================================================================
  // NAVIGATION & SELECTION
  // ============================================================================

  const selectPath = useCallback((path: DossierPath) => {
    dispatch({ type: 'SELECT_PATH', payload: path });
    saveSelectedPathToSession(path);
  }, []);

  const expandItem = useCallback((itemId: string) => {
    console.log('📂 Expanding item:', itemId);
    dispatch({ type: 'EXPAND_ITEM', payload: itemId });
  }, []);

  const collapseItem = useCallback((itemId: string) => {
    console.log('📂 Collapsing item:', itemId);
    dispatch({ type: 'COLLAPSE_ITEM', payload: itemId });
  }, []);

  const toggleExpand = useCallback((itemId: string) => {
    console.log('📂 Toggling expand for item:', itemId);
    dispatch({ type: 'TOGGLE_EXPAND', payload: itemId });
  }, []);

  // Persist expandedItems whenever it changes
  useEffect(() => {
    saveExpandedToSession(state.expandedItems);
  }, [state.expandedItems]);

  // ============================================================================
  // SEARCH & FILTERING
  // ============================================================================

  const setSearchQuery = useCallback((query: string) => {
    dispatch({ type: 'SET_SEARCH', payload: query });
  }, []);

  const setSortBy = useCallback((sortBy: SortOption) => {
    dispatch({ type: 'SET_SORT', payload: sortBy });
  }, []);

  // ============================================================================
  // BULK OPERATIONS
  // ============================================================================

  const selectItem = useCallback((itemId: string) => {
    dispatch({ type: 'SELECT_ITEM', payload: itemId });
  }, []);

  const deselectItem = useCallback((itemId: string) => {
    dispatch({ type: 'DESELECT_ITEM', payload: itemId });
  }, []);

  const clearSelection = useCallback(() => {
    dispatch({ type: 'CLEAR_SELECTION' });
  }, []);

  const bulkDelete = useCallback(async (itemIds: string[]) => {
    // Optimistically remove items
    const itemsToRestore: Dossier[] = [];
    itemIds.forEach(id => {
      const dossier = state.dossiers.find(d => d.id === id);
      if (dossier) {
        itemsToRestore.push(dossier);
        dispatch({ type: 'DELETE_DOSSIER', payload: id });
      }
    });

    try {
      await dossierApi.bulkAction({
        type: 'delete',
        targetIds: itemIds
      });
    } catch (error) {
      // Restore items on failure
      itemsToRestore.forEach(dossier => {
        dispatch({ type: 'ADD_DOSSIER', payload: dossier });
      });
      throw error;
    }
  }, [state.dossiers]);

  // ============================================================================
  // COMPUTED VALUES
  // ============================================================================

  const filteredDossiers = useMemo(() => {
    let filtered = state.dossiers || [];

    // Apply search filter
    if (state.searchQuery) {
      const query = state.searchQuery.toLowerCase();
      filtered = filtered.filter(dossier =>
        (dossier.title || dossier.name || '').toLowerCase().includes(query) ||
        (dossier.description || '').toLowerCase().includes(query)
      );
    }

    // Apply sorting
    filtered.sort((a, b) => {
      switch (state.sortBy) {
        case 'name':
          // Backend sends 'title', frontend expects 'name'
          return (a.title || a.name || '').localeCompare(b.title || b.name || '');
        case 'date':
          // Backend sends 'updated_at'
          const aDateStr = a.updated_at;
          const bDateStr = b.updated_at;
          const aDate = aDateStr ? new Date(aDateStr).getTime() : 0;
          const bDate = bDateStr ? new Date(bDateStr).getTime() : 0;
          return bDate - aDate;
        case 'size':
          // Backend doesn't send metadata yet, use fallback
          return 0; // Equal for now
        case 'activity':
          // Backend doesn't send metadata yet, use fallback
          return 0; // Equal for now
        default:
          return 0;
      }
    });

    return filtered;
  }, [state.dossiers, state.searchQuery, state.sortBy]);

  const isLoading = useMemo(() => {
    return state.loadingStates.dossiers ||
           Object.values(state.loadingStates.segments).some(Boolean) ||
           Object.values(state.loadingStates.runs).some(Boolean) ||
           Object.values(state.loadingStates.drafts).some(Boolean);
  }, [state.loadingStates]);

  const hasError = useMemo(() => {
    return state.errorStates.dossiers !== null ||
           Object.values(state.errorStates.segments).some(Boolean) ||
           Object.values(state.errorStates.runs).some(Boolean) ||
           Object.values(state.errorStates.drafts).some(Boolean);
  }, [state.errorStates]);

  // ============================================================================
  // EFFECTS
  // ============================================================================

  // Load dossiers on mount
  useEffect(() => {
    loadDossiers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // loadDossiers is stable due to useCallback with empty deps

  // Progressive refresh while processing is ongoing
  const isProcessingActive = useMemo(() => {
    return (state.dossiers || []).some(d =>
      (d.segments || []).some(s =>
        (s.runs || []).some(r =>
          r?.metadata?.status === 'processing' ||
          (r.drafts || []).some(dr => dr?.metadata?.status === 'processing')
        )
      )
    );
  }, [state.dossiers]);

  useProcessingPoller(state.dossiers, loadDossiers, 2000, isProcessingActive);

  // ============================================================================
  // RETURN INTERFACE
  // ============================================================================

  return {
    // State
    state,
    filteredDossiers,
    isLoading,
    hasError,

    // Actions
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
    bulkDelete,

    // Utilities
    executeOptimistically
  };
}

// ============================================================================
// ADDITIONAL HOOKS FOR SPECIFIC FUNCTIONALITY
// ============================================================================

// Hook for keyboard navigation
export function useDossierKeyboardNavigation(onAction: (action: string, data?: any) => void) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Prevent default browser behavior for our shortcuts
      if (event.ctrlKey || event.metaKey || event.altKey) {
        switch (event.key) {
          case 'n':
            if (event.ctrlKey || event.metaKey) {
              event.preventDefault();
              onAction('create_dossier');
            }
            break;
          case 'f':
            if (event.ctrlKey || event.metaKey) {
              event.preventDefault();
              onAction('focus_search');
            }
            break;
          case 'Delete':
          case 'Backspace':
            event.preventDefault();
            onAction('delete_selected');
            break;
          case 'F2':
            event.preventDefault();
            onAction('rename_selected');
            break;
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onAction]);
}

// Hook for context menu handling
export function useDossierContextMenu(
  onAction: (action: string, data?: any) => void,
  selectedItems: Set<string>
) {
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    targetId: string;
    targetType: string;
  } | null>(null);

  const showContextMenu = useCallback((event: MouseEvent, targetId: string, targetType: string) => {
    event.preventDefault();
    setContextMenu({
      x: event.clientX,
      y: event.clientY,
      targetId,
      targetType
    });
  }, []);

  const hideContextMenu = useCallback(() => {
    setContextMenu(null);
  }, []);

  const handleContextAction = useCallback((action: string) => {
    if (contextMenu) {
      onAction(action, { targetId: contextMenu.targetId, targetType: contextMenu.targetType });
      hideContextMenu();
    }
  }, [contextMenu, onAction, hideContextMenu]);

  return {
    contextMenu,
    showContextMenu,
    hideContextMenu,
    handleContextAction
  };
}
