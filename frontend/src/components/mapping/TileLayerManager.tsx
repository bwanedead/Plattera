/**
 * Tile Layer Manager Component
 * Manages and renders map tile layers
 */
import React, { useState, useEffect, useMemo } from 'react';

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

interface TileInfo {
  x: number;
  y: number;
  z: number;
  url?: string;
  isLoading: boolean;
  hasError: boolean;
}

export const TileLayerManager: React.FC<TileLayerManagerProps> = ({
  bounds,
  zoom,
  provider,
  geoToScreen
}) => {
  const [tiles, setTiles] = useState<TileInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Calculate required tiles for current view
  const requiredTiles = useMemo(() => {
    const tileSize = 256; // Standard tile size
    const tilesNeeded: TileInfo[] = [];

    // Calculate tile coordinates for bounds
    const minTileX = Math.floor(longitudeToTileX(bounds.min_lon, zoom));
    const maxTileX = Math.floor(longitudeToTileX(bounds.max_lon, zoom));
    const minTileY = Math.floor(latitudeToTileY(bounds.max_lat, zoom)); // Note: Y is inverted
    const maxTileY = Math.floor(latitudeToTileY(bounds.min_lat, zoom));

    for (let x = minTileX; x <= maxTileX; x++) {
      for (let y = minTileY; y <= maxTileY; y++) {
        tilesNeeded.push({
          x,
          y,
          z: zoom,
          isLoading: true,
          hasError: false
        });
      }
    }

    return tilesNeeded;
  }, [bounds, zoom]);

  // Fetch tiles when requirements change
  useEffect(() => {
    const fetchTiles = async () => {
      setIsLoading(true);
      
      try {
        // Create request for tile pipeline
        const tileRequest = {
          bbox: bounds,
          zoom_level: zoom,
          provider: provider
        };

        // In a real implementation, this would call the mapping API
        // For now, we'll simulate tile loading
        console.log('🗺️ Fetching tiles:', tileRequest);
        
        // Simulate API call delay
        await new Promise(resolve => setTimeout(resolve, 500));

        // Update tiles with mock URLs (in production, these would come from the API)
        const updatedTiles = requiredTiles.map(tile => ({
          ...tile,
          url: generateMockTileUrl(tile.x, tile.y, tile.z, provider),
          isLoading: false
        }));

        setTiles(updatedTiles);
      } catch (error) {
        console.error('Failed to fetch tiles:', error);
        
        // Mark tiles as error
        const errorTiles = requiredTiles.map(tile => ({
          ...tile,
          isLoading: false,
          hasError: true
        }));
        
        setTiles(errorTiles);
      } finally {
        setIsLoading(false);
      }
    };

    fetchTiles();
  }, [requiredTiles, provider]);

  // Render individual tile
  const renderTile = (tile: TileInfo) => {
    // Calculate tile bounds in geographic coordinates
    const tileBounds = {
      min_lat: tileYToLatitude(tile.y + 1, tile.z),
      max_lat: tileYToLatitude(tile.y, tile.z),
      min_lon: tileXToLongitude(tile.x, tile.z),
      max_lon: tileXToLongitude(tile.x + 1, tile.z)
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

// Utility functions for tile coordinate conversion
function longitudeToTileX(lon: number, zoom: number): number {
  return ((lon + 180) / 360) * Math.pow(2, zoom);
}

function latitudeToTileY(lat: number, zoom: number): number {
  const latRad = (lat * Math.PI) / 180;
  return ((1 - Math.asinh(Math.tan(latRad)) / Math.PI) / 2) * Math.pow(2, zoom);
}

function tileXToLongitude(x: number, zoom: number): number {
  return (x / Math.pow(2, zoom)) * 360 - 180;
}

function tileYToLatitude(y: number, zoom: number): number {
  const n = Math.PI - (2 * Math.PI * y) / Math.pow(2, zoom);
  return (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
}

function generateMockTileUrl(x: number, y: number, z: number, provider: string): string {
  // In production, this would use real tile URLs from the provider configuration
  const baseUrls: Record<string, string> = {
    'usgs_topo': 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile',
    'usgs_imagery': 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile',
    'osm_standard': 'https://tile.openstreetmap.org',
    'esri_world_topo': 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile',
    'esri_world_imagery': 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile'
  };

  const baseUrl = baseUrls[provider] || baseUrls['osm_standard'];
  
  // Different URL patterns for different providers
  if (provider.startsWith('usgs_') || provider.startsWith('esri_')) {
    return `${baseUrl}/${z}/${y}/${x}`;
  } else {
    return `${baseUrl}/${z}/${x}/${y}.png`;
  }
}