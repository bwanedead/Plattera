/**
 * Tile Layer Manager Component
 * Manages and renders map tile layers with backend integration
 */
import React, { useState, useEffect, useMemo, useRef } from 'react';
import { tileService, type TileInfo } from '../../services/mapping';
import { TileUtils, lonLatToPixel, TILE_SIZE } from '../../utils/coordinateProjection';

interface TileLayerManagerProps {
  bounds: {
    min_lat: number;
    max_lat: number;
    min_lon: number;
    max_lon: number;
  };
  zoom: number;
  provider: string;
  geoToScreen: (lat: number, lon: number) => { x: number; y: number } | null;
  originPixel?: { x: number; y: number };
}

// TileInfo interface now imported from tileService

export const TileLayerManager: React.FC<TileLayerManagerProps> = ({
  bounds,
  zoom,
  provider,
  geoToScreen,
  originPixel: originPixelProp
}) => {
  const [tiles, setTiles] = useState<TileInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const debounceTimer = useRef<number | null>(null);

  // Clamp zoom to provider limits to avoid invalid requests
  const effectiveZoom = useMemo(() => {
    const cfg = tileService.getProvider(provider);
    const minZ = cfg?.min_zoom ?? 0;
    const maxZ = cfg?.max_zoom ?? 16;
    return Math.max(minZ, Math.min(maxZ, Math.round(zoom)));
  }, [provider, zoom]);

  // Pixel-space origin at the top-left of the current view bounds
  const originPixel = useMemo(() => {
    if (originPixelProp && typeof originPixelProp.x === 'number' && typeof originPixelProp.y === 'number') {
      return originPixelProp;
    }
    return lonLatToPixel(bounds.min_lon, bounds.max_lat, effectiveZoom);
  }, [originPixelProp, bounds.min_lon, bounds.max_lat, effectiveZoom]);

  // Calculate required tiles for current view using tile service
  const requiredTiles = useMemo(() => {
    const tiles = tileService.calculateTiles(bounds, effectiveZoom);
    // Debug: tile ranges and counts
    const minX = Math.min(...tiles.map(t => t.x));
    const maxX = Math.max(...tiles.map(t => t.x));
    const minY = Math.min(...tiles.map(t => t.y));
    const maxY = Math.max(...tiles.map(t => t.y));
    console.log(
      `🧩 Tiles required -> provider: ${provider}, z: ${effectiveZoom}, ` +
      `bounds: (${bounds.min_lat.toFixed(5)}, ${bounds.min_lon.toFixed(5)})..(${bounds.max_lat.toFixed(5)}, ${bounds.max_lon.toFixed(5)}), ` +
      `x:[${minX}-${maxX}] y:[${minY}-${maxY}] count:${tiles.length}`
    );
    return tiles;
  }, [bounds, effectiveZoom]);

  // Initialize tile service and fetch tiles when requirements change
  useEffect(() => {
    const fetchTiles = async () => {
      setIsLoading(true);
      try {
        await tileService.initialize();
        // Reset tile array on each fetch to avoid accumulation across pans/zooms/providers
        setTiles([]);
        console.log(`🗺️ Loading ${requiredTiles.length} tiles for ${provider} at zoom ${effectiveZoom}`);
        const prioritized = tileService.prioritizeTiles(requiredTiles);
        const ordered = prioritized.ordered;
        // At high zoom, render center 3x3 first, then background-load the rest
        const FIRST_RING_COUNT = effectiveZoom >= 14 ? 9 : 16;
        const first = ordered.slice(0, FIRST_RING_COUNT);
        const rest = ordered.slice(FIRST_RING_COUNT);

        const firstTiles = await tileService.loadTiles(first, provider);
        setTiles(firstTiles);
        // Schedule remaining tiles without blocking first paint
        if (rest.length > 0) {
          setTimeout(async () => {
            const moreTiles = await tileService.loadTiles(rest, provider);
            setTiles(prev => {
              // merge unique by key
              const map = new Map(prev.map(t => [`${t.x}-${t.y}-${t.z}`, t] as const));
              for (const t of moreTiles) {
                map.set(`${t.x}-${t.y}-${t.z}`, t);
              }
              return Array.from(map.values());
            });
          }, 50);
        }
        const finalSet = rest.length > 0 ? [...first] : first;
        console.log(`✅ Initial tiles loaded: ${firstTiles.filter(t => !t.hasError).length}/${firstTiles.length}`);
      } catch (error) {
        console.error('❌ Failed to fetch tiles:', error);
        const errorTiles = requiredTiles.map(tile => ({
          ...tile,
          provider,
          url: '',
          isLoading: false,
          hasError: true
        }));
        setTiles(errorTiles);
      } finally {
        setIsLoading(false);
      }
    };

    if (debounceTimer.current) {
      window.clearTimeout(debounceTimer.current);
    }
    // Debounce tile fetch a bit to avoid hammering while panning
    debounceTimer.current = window.setTimeout(() => {
      if (requiredTiles.length > 0) {
        fetchTiles();
      }
    }, 120);

    return () => {
      if (debounceTimer.current) {
        window.clearTimeout(debounceTimer.current);
      }
    };
  }, [requiredTiles, provider, effectiveZoom]);

  // Render individual tile using pixel math
  const renderTile = (tile: TileInfo) => {
    const left = tile.x * TILE_SIZE - originPixel.x;
    const top = tile.y * TILE_SIZE - originPixel.y;

    // Simple viewport culling (can be refined with container bounds)
    if (
      left > window.innerWidth ||
      top > window.innerHeight ||
      left + TILE_SIZE < 0 ||
      top + TILE_SIZE < 0
    ) {
      return null;
    }

    return (
      <img
        key={`tile-${tile.x}-${tile.y}-${tile.z}`}
        className="map-tile"
        alt={`${tile.provider} ${tile.z}/${tile.x}/${tile.y}`}
        src={tile.url || undefined}
        style={{
          position: 'absolute',
          left,
          top,
          width: TILE_SIZE,
          height: TILE_SIZE,
          imageRendering: 'auto',
          backgroundColor: '#f0f0f0',
          border: '1px solid #ddd',
          opacity: tile.hasError ? 0.2 : 1
        }}
      />
    );
  };

  return (
    <div className="tile-layer" style={{ position: 'absolute', inset: 0 }}>
      {tiles.map(renderTile)}

      {isLoading && (
        <div className="tile-layer-loading">
          <div className="loading-message">Loading map tiles...</div>
        </div>
      )}
    </div>
  );
};