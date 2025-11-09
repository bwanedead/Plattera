import { useCallback, useEffect, useMemo, useReducer, useState } from 'react';
import { schemaApi, SchemaListItem } from '../services/schema/schemaApi';

type State = {
  items: SchemaListItem[];
  loading: boolean;
  error: string | null;
  selectedSchemaId: string | null;
  searchQuery: string;
  sortBy: 'date' | 'title';
};

type Action =
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'SET_ERROR'; payload: string | null }
  | { type: 'SET_ITEMS'; payload: SchemaListItem[] }
  | { type: 'SET_SELECTED'; payload: string | null }
  | { type: 'SET_SEARCH'; payload: string }
  | { type: 'SET_SORT'; payload: 'date' | 'title' };

const initialState: State = {
  items: [],
  loading: false,
  error: null,
  selectedSchemaId: null,
  searchQuery: '',
  sortBy: 'date'
};

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'SET_LOADING': return { ...state, loading: action.payload };
    case 'SET_ERROR': return { ...state, error: action.payload };
    case 'SET_ITEMS': return { ...state, items: action.payload };
    case 'SET_SELECTED': return { ...state, selectedSchemaId: action.payload };
    case 'SET_SEARCH': return { ...state, searchQuery: action.payload };
    case 'SET_SORT': return { ...state, sortBy: action.payload };
    default: return state;
  }
}

export function useSchemaManager(dossierId: string | null) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [version, setVersion] = useState(0); // manual invalidation
  const [metaById, setMetaById] = useState<Record<string, { version_label?: string; parent_schema_id?: string }>>({});

  const prefetchMeta = useCallback(async (items: SchemaListItem[]) => {
    const pairs = await Promise.all(items.map(async it => {
      try {
        const art = await schemaApi.getSchema(it.dossier_id, it.schema_id);
        const version_label = art?.metadata?.version_label || (art?.structured_data?.metadata?.version_label);
        const parent_schema_id = art?.metadata?.parent_schema_id || (art?.structured_data?.metadata?.parent_schema_id);
        return [it.schema_id, { version_label, parent_schema_id }] as const;
      } catch {
        return [it.schema_id, {}] as const;
      }
    }));
    const map: Record<string, { version_label?: string }> = {};
    pairs.forEach(([id, m]) => { map[id] = m; });
    setMetaById(map);
  }, []);

  const loadSchemas = useCallback(async () => {
    dispatch({ type: 'SET_LOADING', payload: true });
    dispatch({ type: 'SET_ERROR', payload: null });
    try {
      // Always show all schemas across dossiers, independent of dossier selection
      const items = await schemaApi.listAllSchemas();
      dispatch({ type: 'SET_ITEMS', payload: items });
      prefetchMeta(items);
    } catch (e: any) {
      dispatch({ type: 'SET_ERROR', payload: e?.message || 'Failed to load schemas' });
    } finally {
      dispatch({ type: 'SET_LOADING', payload: false });
    }
  }, [prefetchMeta]);

  useEffect(() => { loadSchemas(); }, [loadSchemas, version]);

  const refresh = useCallback(() => setVersion(v => v + 1), []);

  const setSearchQuery = useCallback((q: string) => dispatch({ type: 'SET_SEARCH', payload: q }), []);
  const setSortBy = useCallback((s: 'date' | 'title') => dispatch({ type: 'SET_SORT', payload: s }), []);
  const selectSchema = useCallback((id: string | null) => dispatch({ type: 'SET_SELECTED', payload: id }), []);

  const filtered = useMemo(() => {
    const q = state.searchQuery.trim().toLowerCase();
    let items = state.items || [];
    if (q) {
      items = items.filter(it => {
        const title = (it.dossier_title_snapshot || '').toLowerCase();
        return title.includes(q) || (it.schema_id || '').toLowerCase().includes(q);
      });
    }
    if (state.sortBy === 'date') {
      return [...items].sort((a, b) => String(b.saved_at || '').localeCompare(String(a.saved_at || '')));
    }
    return [...items].sort((a, b) => String(a.dossier_title_snapshot || '').localeCompare(String(b.dossier_title_snapshot || '')));
  }, [state.items, state.searchQuery, state.sortBy]);

  const deleteSchema = useCallback(async (schemaId: string) => {
    if (!dossierId) return false;
    await schemaApi.deleteSchema(dossierId, schemaId);
    refresh();
    if (state.selectedSchemaId === schemaId) {
      dispatch({ type: 'SET_SELECTED', payload: null });
    }
    return true;
  }, [dossierId, refresh, state.selectedSchemaId]);

  return {
    state,
    filteredSchemas: filtered,
    metaById,
    loadSchemas,
    refresh,
    setSearchQuery,
    setSortBy,
    selectSchema,
    deleteSchema
  };
}



