/**
 * Tile Layer Manager Component
 * Manages and renders map tile layers with backend integration
 */
import React, { useState, useEffect, useMemo } from 'react';
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
}

// TileInfo interface now imported from tileService

export const TileLayerManager: React.FC<TileLayerManagerProps> = ({
  bounds,
  zoom,
  provider,
  geoToScreen
}) => {
  const [tiles, setTiles] = useState<TileInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Pixel-space origin at the top-left of the current view bounds
  const originPixel = useMemo(() => {
    return lonLatToPixel(bounds.min_lon, bounds.max_lat, zoom);
  }, [bounds.min_lon, bounds.max_lat, zoom]);

  // Calculate required tiles for current view using tile service
  const requiredTiles = useMemo(() => {
    return tileService.calculateTiles(bounds, zoom);
  }, [bounds, zoom]);

  // Initialize tile service and fetch tiles when requirements change
  useEffect(() => {
    const fetchTiles = async () => {
      setIsLoading(true);
      try {
        await tileService.initialize();
        console.log(`🗺️ Loading ${requiredTiles.length} tiles for ${provider} at zoom ${zoom}`);
        const loadedTiles = await tileService.loadTiles(requiredTiles, provider);
        setTiles(loadedTiles);
        console.log(`✅ Successfully loaded ${loadedTiles.filter(t => !t.hasError).length}/${loadedTiles.length} tiles`);
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

    if (requiredTiles.length > 0) {
      fetchTiles();
    }
  }, [requiredTiles, provider, zoom]);

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