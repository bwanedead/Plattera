/**
 * Clean Mapping API Service
 * Simple, fast mapping operations using new backend services
 */

const API_BASE = 'http://localhost:8000/api/mapping';

export interface ProjectPolygonRequest {
  local_coordinates: Array<{ x: number; y: number }>;
  plss_anchor: {
    state: string;
    township_number: number;
    township_direction: string;
    range_number: number;
    range_direction: string;
    section_number: number;
    quarter_sections?: string;
    principal_meridian?: string;
  };
  starting_point?: {
    tie_to_corner?: {
      bearing_raw?: number;
      distance_value?: number;
      distance_units?: string;
    };
  };
}

export interface ProjectPolygonResponse {
  success: boolean;
  geographic_polygon?: {
    type: string;
    coordinates: number[][][];
  };
  bounds?: {
    min_lat: number;
    max_lat: number;
    min_lon: number;
    max_lon: number;
  };
  anchor_info?: {
    plss_reference: string;
    resolved_coordinates: {
      lat: number;
      lon: number;
    };
  };
  projection_metadata?: {
    method: string;
    coordinate_count: number;
  };
  error?: string;
}

export class CleanMappingApi {
  /**
   * Project local polygon coordinates to geographic coordinates
   * Fast projection using new clean backend services
   */
  async projectPolygon(request: ProjectPolygonRequest): Promise<ProjectPolygonResponse> {
    try {
      console.log('🗺️ Projecting polygon with clean API');
      
      const response = await fetch(`${API_BASE}/project-polygon`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();
      
      if (result.success) {
        console.log(`✅ Polygon projected using ${result.projection_metadata?.method} method`);
      } else {
        console.error('❌ Projection failed:', result.error);
      }

      return result;
    } catch (error) {
      console.error('❌ Projection API error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }

  /**
   * Convert schema polygon data to projection request
   */
  convertFromSchema(polygonResult: any, plssData: any): ProjectPolygonRequest | null {
    try {
      if (!polygonResult?.coordinates || !plssData) {
        return null;
      }

      // Convert coordinates to required format
      const local_coordinates = polygonResult.coordinates.map((coord: any) => {
        if (Array.isArray(coord)) {
          return { x: coord[0], y: coord[1] };
        } else if (coord && typeof coord === 'object' && 'x' in coord && 'y' in coord) {
          return { x: coord.x, y: coord.y };
        }
        throw new Error('Invalid coordinate format');
      });

      // Extract PLSS anchor from schema
      const plss_anchor = {
        state: plssData.state,
        township_number: plssData.township_number,
        township_direction: plssData.township_direction,
        range_number: plssData.range_number,
        range_direction: plssData.range_direction,
        section_number: plssData.section_number,
        quarter_sections: plssData.quarter_sections,
        principal_meridian: plssData.principal_meridian
      };

      const request: ProjectPolygonRequest = {
        local_coordinates,
        plss_anchor
      };

      // Add starting point if available
      if (polygonResult?.origin?.reference_corner || polygonResult?.origin?.bearing || polygonResult?.origin?.distance_feet) {
        request.starting_point = {
          tie_to_corner: {
            bearing_raw: polygonResult?.origin?.bearing,
            distance_value: polygonResult?.origin?.distance_feet,
            distance_units: 'feet'
          }
        };
      }

      return request;
    } catch (error) {
      console.error('❌ Schema conversion failed:', error);
      return null;
    }
  }

  /**
   * Get tile cache statistics
   */
  async getTileCacheStats() {
    try {
      const response = await fetch(`${API_BASE}/tile-cache/stats`);
      return await response.json();
    } catch (error) {
      console.error('❌ Failed to get cache stats:', error);
      return { error: 'Failed to get cache stats' };
    }
  }
}

// Export singleton instance
export const cleanMappingApi = new CleanMappingApi();
