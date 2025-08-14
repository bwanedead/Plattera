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

      const attempt = async () => {
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        return resp;
      };

      let response: Response;
      try {
        response = await attempt();
      } catch {
        // brief backoffs to smooth transient hiccups
        await new Promise(r => setTimeout(r, 250));
        try {
          response = await attempt();
        } catch {
          await new Promise(r => setTimeout(r, 500));
          response = await attempt();
        }
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
    
    // Hard limit to avoid requesting excessive tiles when view bounds are huge
    const MAX_TILE_BATCH = 48;
    const limitedTiles = tiles.slice(0, MAX_TILE_BATCH);
    // Tighter concurrency to reduce network pressure and UI jank
    const CONCURRENCY = 8;
    const loaded: TileInfo[] = [];

    try {
      for (let i = 0; i < limitedTiles.length; i += CONCURRENCY) {
        const chunk = limitedTiles.slice(i, i + CONCURRENCY);
        console.debug(`📦 Loading tile chunk ${Math.floor(i / CONCURRENCY) + 1}/${Math.ceil(limitedTiles.length / CONCURRENCY)} (size ${chunk.length})`);
        const settled = await Promise.allSettled(
          chunk.map(({ x, y, z }) => this.loadTile(provider, z, x, y))
        );
        for (let j = 0; j < settled.length; j++) {
          const result = settled[j];
          const t = chunk[j];
          if (result.status === 'fulfilled') {
            loaded.push(result.value as TileInfo);
          } else {
            console.error(`❌ Failed to load tile ${t.x}/${t.y}/${t.z}:`, result.reason);
            loaded.push({ ...t, provider, url: '', isLoading: false, hasError: true });
          }
        }
      }
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
   * Prioritize tiles center-first in rings (for progressive loading)
   */
  prioritizeTiles(
    tiles: Array<{ x: number; y: number; z: number }>,
  ): { ordered: Array<{ x: number; y: number; z: number }>, center: { x: number; y: number; z: number } | null } {
    if (tiles.length === 0) return { ordered: [], center: null };
    const xs = tiles.map(t => t.x);
    const ys = tiles.map(t => t.y);
    const zs = tiles.map(t => t.z);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const z = zs[0];
    const cx = Math.round((minX + maxX) / 2);
    const cy = Math.round((minY + maxY) / 2);
    const withRing = tiles.map(t => ({
      ...t,
      ring: Math.max(Math.abs(t.x - cx), Math.abs(t.y - cy)),
      dist: Math.abs(t.x - cx) + Math.abs(t.y - cy)
    }));
    withRing.sort((a, b) => a.ring - b.ring || a.dist - b.dist);
    return { ordered: withRing.map(({ x, y, z }) => ({ x, y, z })), center: { x: cx, y: cy, z } };
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
    const dim = Math.pow(2, zoom);
    let minTileX = Math.floor(this.longitudeToTileX(bounds.min_lon, zoom));
    let maxTileX = Math.floor(this.longitudeToTileX(bounds.max_lon, zoom));
    let minTileY = Math.floor(this.latitudeToTileY(bounds.max_lat, zoom)); // Note: Y is flipped
    let maxTileY = Math.floor(this.latitudeToTileY(bounds.min_lat, zoom));

    // Overfetch one tile on each edge to avoid gaps at screen borders
    minTileX = Math.max(0, minTileX - 1);
    maxTileX = Math.min(dim - 1, maxTileX + 1);
    minTileY = Math.max(0, minTileY - 1);
    maxTileY = Math.min(dim - 1, maxTileY + 1);

    const tiles: Array<{ x: number; y: number; z: number }> = [];
    
    for (let x = minTileX; x <= maxTileX; x++) {
      for (let y = minTileY; y <= maxTileY; y++) {
        tiles.push({ x, y, z: zoom });
      }
    }

    // Debug: log tile range and count
    console.debug(`🧮 Tile range z=${zoom} x:[${minTileX}-${maxTileX}] y:[${minTileY}-${maxTileY}] -> ${tiles.length} tiles`);

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