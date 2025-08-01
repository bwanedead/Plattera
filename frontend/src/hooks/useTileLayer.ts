/**
 * Tile Layer Hook
 * Manages map tile loading and caching
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { mappingApi, TileResponse, TileRequest, GeographicBounds } from '../services/mappingApi';

export interface TileState {
  isLoading: boolean;
  error: string | null;
  tiles: Array<{
    x: number;
    y: number;
    z: number;
    url: string;
    isLoaded: boolean;
    hasError: boolean;
  }>;
  cacheStats: {
    hits: number;
    misses: number;
    totalRequests: number;
  };
}

export interface UseTileLayerOptions {
  provider?: string;
  debounceMs?: number;
  maxConcurrentLoads?: number;
}

export interface UseTileLayerReturn {
  state: TileState;
  loadTiles: (bounds: GeographicBounds, zoom: number) => Promise<void>;
  clearTiles: () => void;
  setProvider: (provider: string) => void;
  getCurrentProvider: () => string;
  retryFailedTiles: () => Promise<void>;
}

export const useTileLayer = (options: UseTileLayerOptions = {}): UseTileLayerReturn => {
  const {
    provider: initialProvider = 'usgs_topo',
    debounceMs = 300,
    maxConcurrentLoads = 6
  } = options;

  const [currentProvider, setCurrentProvider] = useState(initialProvider);
  const [state, setState] = useState<TileState>({
    isLoading: false,
    error: null,
    tiles: [],
    cacheStats: {
      hits: 0,
      misses: 0,
      totalRequests: 0
    }
  });

  // Refs for managing async operations
  const loadingTimeoutRef = useRef<NodeJS.Timeout>();
  const currentRequestRef = useRef<string>('');
  const loadingTilesRef = useRef<Set<string>>(new Set());

  // Generate request key for deduplication
  const generateRequestKey = useCallback((bounds: GeographicBounds, zoom: number, provider: string): string => {
    return `${bounds.min_lat},${bounds.max_lat},${bounds.min_lon},${bounds.max_lon},${zoom},${provider}`;
  }, []);

  // Load tiles for given bounds and zoom
  const loadTiles = useCallback(async (bounds: GeographicBounds, zoom: number) => {
    const requestKey = generateRequestKey(bounds, zoom, currentProvider);
    
    // Skip if this request is already in progress
    if (currentRequestRef.current === requestKey) {
      return;
    }

    // Clear existing timeout
    if (loadingTimeoutRef.current) {
      clearTimeout(loadingTimeoutRef.current);
    }

    // Debounce tile loading
    loadingTimeoutRef.current = setTimeout(async () => {
      try {
        currentRequestRef.current = requestKey;
        setState(prev => ({ ...prev, isLoading: true, error: null }));

        const tileRequest: TileRequest = {
          bbox: bounds,
          zoom_level: zoom,
          provider: currentProvider
        };

        const response = await mappingApi.getMapTiles(tileRequest);

        // Check if this request is still current
        if (currentRequestRef.current !== requestKey) {
          return; // Request was superseded
        }

        if (response.success && response.tiles) {
          // Convert API response to tile state
          const tiles = response.tiles.map(tile => ({
            x: tile.x,
            y: tile.y,
            z: tile.z,
            url: tile.url,
            isLoaded: false,
            hasError: false
          }));

          setState(prev => ({
            ...prev,
            isLoading: false,
            tiles,
            cacheStats: {
              hits: prev.cacheStats.hits + (response.metadata?.cache_hits || 0),
              misses: prev.cacheStats.misses + (response.metadata?.cache_misses || 0),
              totalRequests: prev.cacheStats.totalRequests + 1
            }
          }));

          // Start loading tile images
          loadTileImages(tiles);
        } else {
          setState(prev => ({
            ...prev,
            isLoading: false,
            error: response.error || 'Failed to load tiles'
          }));
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        setState(prev => ({
          ...prev,
          isLoading: false,
          error: `Tile loading error: ${errorMessage}`
        }));
      } finally {
        currentRequestRef.current = '';
      }
    }, debounceMs);
  }, [currentProvider, generateRequestKey, debounceMs]);

  // Load individual tile images
  const loadTileImages = useCallback(async (tiles: TileState['tiles']) => {
    const loadPromises: Promise<void>[] = [];
    let activeLoads = 0;

    for (const tile of tiles) {
      const tileKey = `${tile.x}-${tile.y}-${tile.z}`;
      
      // Skip if already loading
      if (loadingTilesRef.current.has(tileKey)) {
        continue;
      }

      // Limit concurrent loads
      if (activeLoads >= maxConcurrentLoads) {
        break;
      }

      activeLoads++;
      loadingTilesRef.current.add(tileKey);

      const loadPromise = new Promise<void>((resolve) => {
        const img = new Image();
        
        img.onload = () => {
          setState(prev => ({
            ...prev,
            tiles: prev.tiles.map(t => 
              t.x === tile.x && t.y === tile.y && t.z === tile.z
                ? { ...t, isLoaded: true }
                : t
            )
          }));
          loadingTilesRef.current.delete(tileKey);
          resolve();
        };

        img.onerror = () => {
          setState(prev => ({
            ...prev,
            tiles: prev.tiles.map(t => 
              t.x === tile.x && t.y === tile.y && t.z === tile.z
                ? { ...t, hasError: true }
                : t
            )
          }));
          loadingTilesRef.current.delete(tileKey);
          resolve();
        };

        img.src = tile.url;
      });

      loadPromises.push(loadPromise);
    }

    // Wait for current batch to complete, then load remaining tiles
    if (loadPromises.length > 0) {
      await Promise.all(loadPromises);
      
      // Load remaining tiles if any
      const remainingTiles = tiles.filter(tile => {
        const tileKey = `${tile.x}-${tile.y}-${tile.z}`;
        return !loadingTilesRef.current.has(tileKey) && !tile.isLoaded && !tile.hasError;
      });

      if (remainingTiles.length > 0) {
        await loadTileImages(remainingTiles);
      }
    }
  }, [maxConcurrentLoads]);

  // Clear tiles
  const clearTiles = useCallback(() => {
    // Clear timeouts and current requests
    if (loadingTimeoutRef.current) {
      clearTimeout(loadingTimeoutRef.current);
    }
    currentRequestRef.current = '';
    loadingTilesRef.current.clear();

    setState(prev => ({
      ...prev,
      tiles: [],
      error: null
    }));
  }, []);

  // Set provider
  const setProvider = useCallback((provider: string) => {
    setCurrentProvider(provider);
    clearTiles(); // Clear tiles when provider changes
  }, [clearTiles]);

  // Get current provider
  const getCurrentProvider = useCallback(() => currentProvider, [currentProvider]);

  // Retry failed tiles
  const retryFailedTiles = useCallback(async () => {
    const failedTiles = state.tiles.filter(tile => tile.hasError);
    
    if (failedTiles.length === 0) {
      return;
    }

    // Reset error state for failed tiles
    setState(prev => ({
      ...prev,
      tiles: prev.tiles.map(tile => 
        tile.hasError ? { ...tile, hasError: false } : tile
      )
    }));

    // Retry loading
    await loadTileImages(failedTiles);
  }, [state.tiles, loadTileImages]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (loadingTimeoutRef.current) {
        clearTimeout(loadingTimeoutRef.current);
      }
    };
  }, []);

  return {
    state,
    loadTiles,
    clearTiles,
    setProvider,
    getCurrentProvider,
    retryFailedTiles
  };
};