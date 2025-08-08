/**
 * Mapping API Service
 * Handles API calls for geographic mapping functionality
 */

const API_BASE = 'http://localhost:8000/api/mapping';

export interface PLSSDescription {
  state: string;
  county?: string;
  principal_meridian?: string;
  township_number: number;
  township_direction: string;
  range_number: number;
  range_direction: string;
  section_number: number;
  quarter_sections?: string;
}

export interface LocalCoordinate {
  x: number;
  y: number;
}

export interface GeographicBounds {
  min_lat: number;
  max_lat: number;
  min_lon: number;
  max_lon: number;
}

export interface ProjectPolygonRequest {
  local_coordinates: LocalCoordinate[];
  plss_anchor: PLSSDescription;
  options?: {
    datum?: string;
    preserve_area?: boolean;
    intermediate_crs?: string;
    precision_meters?: number;
  };
  starting_point?: {
    tie_to_corner?: {
      corner_label?: string;
      bearing_raw?: string;
      distance_value?: number;
      distance_units?: string;
    }
  };
}

export interface ProjectPolygonResponse {
  success: boolean;
  geographic_polygon?: {
    type: string;
    coordinates: number[][][]; // GeoJSON format
    bounds: GeographicBounds;
  };
  anchor_info?: {
    plss_reference: string;
    resolved_coordinates: {
      lat: number;
      lon: number;
    };
  };
  projection_metadata?: any;
  error?: string;
}

export interface TileRequest {
  bbox: GeographicBounds;
  zoom_level: number;
  provider?: string;
}

export interface TileResponse {
  success: boolean;
  tiles?: Array<{
    x: number;
    y: number;
    z: number;
    url: string;
    size: number;
  }>;
  metadata?: {
    bbox: GeographicBounds;
    zoom_level: number;
    provider: string;
    total_tiles: number;
    cache_hits: number;
    cache_misses: number;
  };
  error?: string;
}

export interface PLSSResolveRequest {
  plss_description: PLSSDescription;
}

export interface PLSSResolveResponse {
  success: boolean;
  coordinates?: {
    lat: number;
    lon: number;
  };
  anchor_point?: {
    lat: number;
    lon: number;
    datum: string;
    accuracy: string;
  };
  metadata?: {
    plss_reference: string;
    quarter_sections?: string;
    state: string;
    data_source?: string;
    resolution_method?: string;
  };
  error?: string;
}

export interface TileProvider {
  name: string;
  description: string;
  attribution: string;
  tile_size: number;
  min_zoom: number;
  max_zoom: number;
  format: string;
}

export interface TileProvidersResponse {
  success: boolean;
  providers?: Record<string, TileProvider>;
  error?: string;
}

export interface PLSSStatesResponse {
  available_states: string[];
  data_directory: string;
}

export interface CacheStatsResponse {
  success: boolean;
  plss_cache?: {
    cache_directory: string;
    cached_states: string[];
    cache_size_mb: number;
    statistics: {
      hits: number;
      misses: number;
      states_cached: number;
    };
    available_states: string[];
  };
  tile_cache?: {
    service_stats: {
      requests: number;
      hits: number;
      misses: number;
      providers_used: string[];
      hit_rate: number;
    };
    cache_stats: {
      cache_size_mb: number;
      cache_size_bytes: number;
      max_size_mb: number;
      usage_percent: number;
      provider_stats: Record<string, number>;
      cache_directory: string;
    };
  };
  error?: string;
}

/**
 * Extract PLSS information from schema for mapping
 * Independent of polygon processing
 */
export async function extractPLSSInfo(schemaData: any): Promise<{
  success: boolean;
  plss_info?: any;
  data_requirements?: any;
  data_status?: any;
  error?: string;
}> {
  try {
    console.log('🗺️ Extracting PLSS info for mapping:', schemaData);
    
    const response = await fetch('/api/mapping/extract-plss-info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(schemaData)
    });
    
    const result = await response.json();
    console.log('📍 PLSS extraction result:', result);
    
    return result;
    
  } catch (error) {
    console.error('❌ PLSS extraction failed:', error);
    return {
      success: false,
      error: `PLSS extraction failed: ${error.message}`
    };
  }
}

class MappingApiService {
  /**
   * Project local polygon coordinates to geographic coordinates
   */
  async projectPolygonToMap(request: ProjectPolygonRequest): Promise<ProjectPolygonResponse> {
    try {
      const response = await fetch(`${API_BASE}/project-polygon`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('❌ Project polygon API error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }

  /**
   * Get map tiles for specified bounds and zoom
   */
  async getMapTiles(request: TileRequest): Promise<TileResponse> {
    try {
      const response = await fetch(`${API_BASE}/get-map-tiles`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('❌ Get map tiles API error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }

  /**
   * Resolve PLSS description to geographic coordinates
   */
  async resolvePLSSCoordinates(request: PLSSResolveRequest): Promise<PLSSResolveResponse> {
    try {
      const response = await fetch(`${API_BASE}/resolve-plss`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('❌ Resolve PLSS API error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }

  /**
   * Get available tile providers
   */
  async getTileProviders(): Promise<TileProvidersResponse> {
    try {
      const response = await fetch(`${API_BASE}/tile-providers`);

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('❌ Get tile providers API error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }

  /**
   * Get available PLSS states
   */
  async getPLSSStates(): Promise<PLSSStatesResponse> {
    try {
      const response = await fetch(`${API_BASE}/plss-states`);

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('❌ Get PLSS states API error:', error);
      throw error;
    }
  }

  /**
   * Get a PLSS section-centered view (center + padded bounds) for tile retrieval independent of deed georef.
   */
  async getPLSSSectionView(
    plss: PLSSDescription,
    padding: number = 0.1
  ): Promise<{ success: boolean; center?: { lat: number; lon: number }; bounds?: GeographicBounds; error?: string }>{
    try {
      const response = await fetch(`${API_BASE}/plss/section-view`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plss_description: plss, padding })
      });
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || `HTTP ${response.status}`);
      }
      return await response.json();
    } catch (e: any) {
      console.error('❌ getPLSSSectionView error:', e);
      return { success: false, error: e?.message || 'Unknown error' };
    }
  }

  /**
   * Clear mapping cache
   */
  async clearCache(cacheType: 'plss' | 'tiles' | 'all' = 'all'): Promise<{ success: boolean; error?: string }> {
    try {
      const response = await fetch(`${API_BASE}/cache/clear`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ cache_type: cacheType }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('❌ Clear cache API error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }

  /**
   * Get cache statistics
   */
  async getCacheStats(): Promise<CacheStatsResponse> {
    try {
      const response = await fetch(`${API_BASE}/cache/stats`);

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('❌ Get cache stats API error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }

  /**
   * Generate map tiles for polygon bounds with padding
   */
  async getTilesForPolygon(
    polygonBounds: GeographicBounds, 
    zoom: number, 
    provider: string = 'usgs_topo',
    padding: number = 0.1
  ): Promise<TileResponse> {
    // Add padding to polygon bounds
    const latPadding = (polygonBounds.max_lat - polygonBounds.min_lat) * padding;
    const lonPadding = (polygonBounds.max_lon - polygonBounds.min_lon) * padding;

    const paddedBounds: GeographicBounds = {
      min_lat: polygonBounds.min_lat - latPadding,
      max_lat: polygonBounds.max_lat + latPadding,
      min_lon: polygonBounds.min_lon - lonPadding,
      max_lon: polygonBounds.max_lon + lonPadding
    };

    return this.getMapTiles({
      bbox: paddedBounds,
      zoom_level: zoom,
      provider
    });
  }

  /**
   * Convert polygon from schema format to mapping format
   */
  convertPolygonForMapping(polygonResult: any, plssData: any): ProjectPolygonRequest | null {
    try {
      if (!polygonResult.coordinates || !plssData) {
        return null;
      }

      // Convert coordinates to required format
      const localCoordinates: LocalCoordinate[] = polygonResult.coordinates.map((coord: any) => {
        if (Array.isArray(coord)) {
          return { x: coord[0], y: coord[1] };
        } else if (coord && typeof coord === 'object' && 'x' in coord && 'y' in coord) {
          return { x: coord.x, y: coord.y };
        }
        throw new Error('Invalid coordinate format');
      });

      // Extract PLSS anchor from schema
      const plssAnchor: PLSSDescription = {
        state: plssData.state,
        county: plssData.county,
        principal_meridian: plssData.principal_meridian,
        township_number: plssData.township_number,
        township_direction: plssData.township_direction,
        range_number: plssData.range_number,
        range_direction: plssData.range_direction,
        section_number: plssData.section_number,
        quarter_sections: plssData.quarter_sections
      };

      const request: ProjectPolygonRequest = {
        local_coordinates: localCoordinates,
        plss_anchor: plssAnchor,
        options: {
          datum: 'WGS84',
          preserve_area: true,
          intermediate_crs: 'utm',
          precision_meters: 1.0
        }
      };

      // Pass through starting_point info if available (for tie_to_corner)
      if (polygonResult?.origin?.reference_corner || polygonResult?.origin?.bearing || polygonResult?.origin?.distance_feet) {
        request.starting_point = {
          tie_to_corner: {
            corner_label: polygonResult?.origin?.reference_corner,
            bearing_raw: polygonResult?.origin?.bearing,
            distance_value: polygonResult?.origin?.distance_feet,
            distance_units: 'feet'
          }
        };
      }

      return request;
    } catch (error) {
      console.error('❌ Error converting polygon for mapping:', error);
      return null;
    }
  }
}

// Export singleton instance
export const mappingApi = new MappingApiService();