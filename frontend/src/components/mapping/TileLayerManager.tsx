/**
 * Tile Layer Manager Component
 * Manages and renders map tile layers with backend integration
 */
import React, { useState, useEffect, useMemo } from 'react';
import { tileService, type TileInfo } from '../../services/mapping';
import { TileUtils } from '../../utils/coordinateProjection';

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

  // Calculate required tiles for current view using tile service
  const requiredTiles = useMemo(() => {
    return tileService.calculateTiles(bounds, zoom);
  }, [bounds, zoom]);

  // Initialize tile service and fetch tiles when requirements change
  useEffect(() => {
    const fetchTiles = async () => {
      setIsLoading(true);
      
      try {
        // Initialize tile service (loads provider configs)
        await tileService.initialize();
        
        console.log(`🗺️ Loading ${requiredTiles.length} tiles for ${provider} at zoom ${zoom}`);
        
        // Use tile service for efficient batch loading
        const loadedTiles = await tileService.loadTiles(requiredTiles, provider);
        
        setTiles(loadedTiles);
        console.log(`✅ Successfully loaded ${loadedTiles.filter(t => !t.hasError).length}/${loadedTiles.length} tiles`);
        
      } catch (error) {
        console.error('❌ Failed to fetch tiles:', error);
        
        // Mark all tiles as error
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
  }, [requiredTiles, provider]);

  // Render individual tile
  const renderTile = (tile: TileInfo) => {
    // Calculate tile bounds in geographic coordinates using TileUtils
    const tileBounds = {
      min_lat: TileUtils.tileYToLatitude(tile.y + 1, tile.z),
      max_lat: TileUtils.tileYToLatitude(tile.y, tile.z),
      min_lon: TileUtils.tileXToLongitude(tile.x, tile.z),
      max_lon: TileUtils.tileXToLongitude(tile.x + 1, tile.z)
    };

    // Convert to screen coordinates
    const topLeft = geoToScreen(tileBounds.max_lat, tileBounds.min_lon);
    const bottomRight = geoToScreen(tileBounds.min_lat, tileBounds.max_lon);

    if (!topLeft || !bottomRight) return null;

    const width = bottomRight.x - topLeft.x;
    const height = bottomRight.y - topLeft.y;

    // Skip tiles that are too small or outside view
    if (width < 10 || height < 10 || 
        topLeft.x > window.innerWidth || bottomRight.x < 0 ||
        topLeft.y > window.innerHeight || bottomRight.y < 0) {
      return null;
    }

    return (
      <div
        key={`tile-${tile.x}-${tile.y}-${tile.z}`}
        className="map-tile"
        style={{
          position: 'absolute',
          left: topLeft.x,
          top: topLeft.y,
          width: width,
          height: height,
          backgroundColor: '#f0f0f0',
          border: '1px solid #ddd',
          backgroundImage: tile.url && !tile.hasError ? `url(${tile.url})` : 'none',
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          backgroundRepeat: 'no-repeat'
        }}
      >
        {/* Loading indicator */}
        {tile.isLoading && (
          <div className="tile-loading">
            <div className="loading-spinner-small"></div>
          </div>
        )}

        {/* Error indicator */}
        {tile.hasError && (
          <div className="tile-error">
            <div className="error-text">✕</div>
          </div>
        )}

        {/* Debug info (remove in production) */}
        {process.env.NODE_ENV === 'development' && (
          <div className="tile-debug">
            {tile.x}/{tile.y}/{tile.z}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="tile-layer" style={{ position: 'absolute', inset: 0 }}>
      {tiles.map(renderTile)}
      
      {/* Overall loading indicator */}
      {isLoading && (
        <div className="tile-layer-loading">
          <div className="loading-message">Loading map tiles...</div>
        </div>
      )}
    </div>
  );
};

// Tile coordinate utilities now provided by TileUtils from coordinateProjection