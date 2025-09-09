// ============================================================================
// DOSSIER MANAGER HOOK - ELITE STATE MANAGEMENT
// ============================================================================
// Comprehensive state management for the Dossier System
// Features: optimistic updates, error recovery, caching, offline support
// ============================================================================

import { useReducer, useCallback, useEffect, useMemo, useState } from 'react';
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
  const [state, dispatch] = useReducer(dossierReducer, initialState);

  // ============================================================================
  // OPTIMISTIC UPDATE UTILITIES
  // ============================================================================

  const executeOptimistically = useCallback(async <T>(
    optimisticAction: DossierAction,
    apiCall: () => Promise<T>,
    rollbackAction?: DossierAction
  ): Promise<T> => {
    // Apply optimistic update
    dispatch(optimisticAction);
    const previousState = state;

    try {
      const result = await apiCall();

      // Update was successful, clear any errors
      if (optimisticAction.type === 'UPDATE_DOSSIERS') {
        dispatch({ type: 'SET_ERROR', payload: { key: 'dossiers', error: null } });
      }

      return result;
    } catch (error) {
      // Revert optimistic update
      if (rollbackAction) {
        dispatch(rollbackAction);
      } else {
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
      console.log('✅ Loaded dossiers:', dossiers);
      console.log('📊 Dossiers array length:', dossiers.length);
      dispatch({ type: 'UPDATE_DOSSIERS', payload: dossiers });
    } catch (error) {
      console.error('❌ Failed to load dossiers:', error);
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
      name: data.title,
      description: data.description,
      createdAt: new Date(),
      updatedAt: new Date(),
      segments: [],
      metadata: {
        totalSegments: 0,
        totalRuns: 0,
        totalDrafts: 0,
        totalSizeBytes: 0,
        lastActivity: new Date()
      }
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
    const currentDossier = state.dossiers.find(d => d.id === dossierId);
    if (!currentDossier) return;

    const updatedDossier = { ...currentDossier, ...data, updatedAt: new Date() };

    return executeOptimistically(
      { type: 'UPDATE_DOSSIER', payload: updatedDossier },
      () => dossierApi.updateDossier(dossierId, data),
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
    console.log('🔍 Calculating filteredDossiers - state.dossiers:', state.dossiers);
    console.log('🔍 Calculating filteredDossiers - state.dossiers type:', typeof state.dossiers);
    let filtered = state.dossiers || [];
    console.log('🔍 filteredDossiers - initial filtered length:', filtered.length);

    // Apply search filter
    if (state.searchQuery) {
      const query = state.searchQuery.toLowerCase();
      filtered = filtered.filter(dossier =>
        dossier.name.toLowerCase().includes(query) ||
        dossier.description?.toLowerCase().includes(query)
      );
    }

    // Apply sorting
    filtered.sort((a, b) => {
      switch (state.sortBy) {
        case 'name':
          return a.name.localeCompare(b.name);
        case 'date':
          return b.updatedAt.getTime() - a.updatedAt.getTime();
        case 'size':
          return b.metadata.totalSizeBytes - a.metadata.totalSizeBytes;
        case 'activity':
          return b.metadata.lastActivity.getTime() - a.metadata.lastActivity.getTime();
        default:
          return 0;
      }
    });

    console.log('🔍 filteredDossiers - final result length:', filtered.length);
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
  }, [loadDossiers]);

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
