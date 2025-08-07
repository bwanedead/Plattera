/**
 * Tile Service
 * High-performance tile loading with backend integration and cache awareness
 */

export interface TileProvider {
  name: string;
  description: string;
  attribution: string;
  min_zoom: number;
  max_zoom: number;
  cors_enabled?: boolean;
}

export interface TileInfo {
  x: number;
  y: number;
  z: number;
  url: string;
  provider: string;
  isLoading?: boolean;
  hasError?: boolean;
  source?: 'cache' | 'remote' | 'direct';
}

export interface TileConfig {
  tiles_proxy_enabled: boolean;
  cors_enabled: boolean;
}

class TileService {
  private apiBase = 'http://localhost:8000/api/mapping';
  private providers: Map<string, TileProvider> = new Map();
  private config: TileConfig | null = null;

  /**
   * Initialize tile service and load provider configurations
   */
  async initialize(): Promise<void> {
    try {
      const providersResponse = await fetch(`${this.apiBase}/tile-providers`);
      if (!providersResponse.ok) {
        throw new Error(`Failed to fetch providers: ${providersResponse.status}`);
      }

      const providersData = await providersResponse.json();
      
      // Store provider configurations
      Object.entries(providersData.providers || {}).forEach(([key, provider]: [string, any]) => {
        this.providers.set(key, {
          name: provider.name,
          description: provider.description,
          attribution: provider.attribution,
          min_zoom: provider.min_zoom,
          max_zoom: provider.max_zoom,
          cors_enabled: provider.cors_enabled
        });
      });

      console.log(`🗺️ Loaded ${this.providers.size} tile providers`);
    } catch (error) {
      console.error('❌ Failed to initialize tile service:', error);
      // Use fallback providers if backend unavailable
      this.loadFallbackProviders();
    }
  }

  /**
   * Get available tile providers
   */
  getProviders(): TileProvider[] {
    return Array.from(this.providers.values());
  }

  /**
   * Get specific provider configuration
   */
  getProvider(name: string): TileProvider | null {
    return this.providers.get(name) || null;
  }

  /**
   * Get tile URL with cache-aware routing
   * 
   * @param provider Provider name
   * @param z Zoom level
   * @param x Tile X coordinate
   * @param y Tile Y coordinate
   * @returns Tile URL (backend proxy or direct)
   */
  getTileUrl(provider: string, z: number, x: number, y: number): string {
    const providerConfig = this.providers.get(provider);
    
    if (!providerConfig) {
      console.warn(`⚠️ Unknown provider: ${provider}, falling back to usgs_topo`);
      provider = 'usgs_topo';
    }

    // Validate zoom level
    if (providerConfig && (z < providerConfig.min_zoom || z > providerConfig.max_zoom)) {
      console.warn(`⚠️ Zoom ${z} outside valid range for ${provider} (${providerConfig.min_zoom}-${providerConfig.max_zoom})`);
      return ''; // Return empty URL for invalid zoom
    }

    // Always use backend proxy for cache benefits and rate limiting
    return `${this.apiBase}/tile/${provider}/${z}/${x}/${y}`;
  }

  /**
   * Load tile with error handling and cache awareness
   * 
   * @param provider Provider name
   * @param z Zoom level
   * @param x Tile X coordinate
   * @param y Tile Y coordinate
   * @returns Promise resolving to TileInfo
   */
  async loadTile(provider: string, z: number, x: number, y: number): Promise<TileInfo> {
    const tileInfo: TileInfo = {
      x, y, z, provider,
      url: '',
      isLoading: true,
      hasError: false
    };

    try {
      const url = this.getTileUrl(provider, z, x, y);
      if (!url) {
        throw new Error('Invalid zoom level for provider');
      }

      // Fetch tile through backend (which handles caching)
      const response = await fetch(url);
      
      if (!response.ok) {
        // Graceful: mark error and return, do not throw to avoid Promise.allSettled churn
        tileInfo.isLoading = false;
        tileInfo.hasError = true;
        return tileInfo;
      }

      // Check if response is a redirect (CORS bypass mode)
      const contentType = response.headers.get('content-type');
      if (contentType?.includes('application/json')) {
        const redirectData = await response.json();
        if (redirectData.redirect) {
          tileInfo.url = redirectData.redirect;
          tileInfo.source = 'direct';
        }
      } else {
        // Normal tile response
        tileInfo.url = url;
        tileInfo.source = response.headers.get('X-Tile-Source') as any || 'remote';
      }

      tileInfo.isLoading = false;
      console.debug(`🗺️ Loaded tile ${provider}/${z}/${x}/${y} from ${tileInfo.source}`);
      
      return tileInfo;

    } catch (error) {
      console.error(`❌ Failed to load tile ${provider}/${z}/${x}/${y}:`, error);
      
      tileInfo.isLoading = false;
      tileInfo.hasError = true;
      tileInfo.url = ''; // Clear URL on error
      
      return tileInfo;
    }
  }

  /**
   * Batch load multiple tiles efficiently
   * 
   * @param tiles Array of tile coordinates
   * @param provider Provider name
   * @returns Promise resolving to array of TileInfo
   */
  async loadTiles(
    tiles: Array<{ x: number; y: number; z: number }>, 
    provider: string
  ): Promise<TileInfo[]> {
    console.log(`🗺️ Loading ${tiles.length} tiles from ${provider}`);
    
    // Load tiles in parallel for better performance
    // Hard limit to avoid requesting excessive tiles when view bounds are huge
    const MAX_TILE_BATCH = 64;
    const limitedTiles = tiles.slice(0, MAX_TILE_BATCH);
    const tilePromises = limitedTiles.map(({ x, y, z }) => this.loadTile(provider, z, x, y));

    try {
      const results = await Promise.allSettled(tilePromises);
      
      const loaded = results.map((result, index) => {
        if (result.status === 'fulfilled') {
          return result.value;
        } else {
          console.error(`❌ Failed to load tile ${tiles[index].x}/${tiles[index].y}/${tiles[index].z}:`, result.reason);
          return {
            ...limitedTiles[index],
            provider,
            url: '',
            isLoading: false,
            hasError: true
          };
        }
      });
      // If we truncated, pad rest as errors to keep lengths consistent for callers that expect same length
      if (tiles.length > limitedTiles.length) {
        const remaining = tiles.slice(limitedTiles.length).map(t => ({ ...t, provider, url: '', isLoading: false, hasError: true }));
        return [...loaded, ...remaining];
      }
      return loaded;
    } catch (error) {
      console.error('❌ Batch tile loading failed:', error);
      throw error;
    }
  }

  /**
   * Calculate required tiles for given bounds and zoom
   * 
   * @param bounds Geographic bounds
   * @param zoom Zoom level
   * @returns Array of tile coordinates
   */
  calculateTiles(
    bounds: { min_lat: number; max_lat: number; min_lon: number; max_lon: number },
    zoom: number
  ): Array<{ x: number; y: number; z: number }> {
    // Convert bounds to tile coordinates
    const minTileX = Math.floor(this.longitudeToTileX(bounds.min_lon, zoom));
    const maxTileX = Math.floor(this.longitudeToTileX(bounds.max_lon, zoom));
    const minTileY = Math.floor(this.latitudeToTileY(bounds.max_lat, zoom)); // Note: Y is flipped
    const maxTileY = Math.floor(this.latitudeToTileY(bounds.min_lat, zoom));

    const tiles: Array<{ x: number; y: number; z: number }> = [];
    
    for (let x = minTileX; x <= maxTileX; x++) {
      for (let y = minTileY; y <= maxTileY; y++) {
        tiles.push({ x, y, z: zoom });
      }
    }

    return tiles;
  }

  /**
   * Tile coordinate conversion utilities
   */
  private longitudeToTileX(lon: number, zoom: number): number {
    return ((lon + 180) / 360) * Math.pow(2, zoom);
  }

  private latitudeToTileY(lat: number, zoom: number): number {
    return (1 - Math.log(Math.tan(lat * Math.PI / 180) + 1 / Math.cos(lat * Math.PI / 180)) / Math.PI) / 2 * Math.pow(2, zoom);
  }

  /**
   * Load fallback provider configurations if backend unavailable
   */
  private loadFallbackProviders(): void {
    const fallbackProviders: Record<string, TileProvider> = {
      usgs_topo: {
        name: 'USGS Topographic',
        description: 'USGS National Map topographic maps',
        attribution: '© USGS | The National Map',
        min_zoom: 0,
        max_zoom: 16,
        cors_enabled: true
      },
      usgs_imagery_only: {
        name: 'USGS Imagery Only',
        description: 'USGS high-resolution orthoimagery',
        attribution: '© USGS | The National Map',
        min_zoom: 0,
        max_zoom: 23,
        cors_enabled: true
      },
      osm_standard: {
        name: 'OpenStreetMap',
        description: 'Standard OpenStreetMap tiles (fallback)',
        attribution: '© OpenStreetMap contributors',
        min_zoom: 0,
        max_zoom: 19,
        cors_enabled: false
      }
    };

    Object.entries(fallbackProviders).forEach(([key, provider]) => {
      this.providers.set(key, provider);
    });

    console.log('🔄 Using fallback tile providers');
  }
}

// Export singleton instance
export const tileService = new TileService();