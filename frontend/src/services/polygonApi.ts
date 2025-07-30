/**
 * Polygon Drawing API Service
 * Handles all API calls related to polygon generation from schema data
 */

export interface PolygonDrawingRequest {
  parcel_data: any;
  options?: {
    coordinate_system?: 'local' | 'utm' | 'geographic';
    distance_units?: string;
    closure_tolerance_feet?: number;
    output_format?: 'geojson' | 'wkt' | 'coordinates';
  };
}

export interface PolygonCoordinate {
  x: number;
  y: number;
}

export interface PolygonResult {
  description_id: number;
  coordinates: PolygonCoordinate[];
  geometry_type: string;
  coordinate_system: string;
  origin: any;
  properties: {
    area_calculated: number;
    area_stated?: number;
    perimeter: number;
    closure_error: number;
    courses_count: number;
  };
}

export interface PolygonDrawingResponse {
  success: boolean;
  polygons?: PolygonResult[];
  metadata?: {
    parcel_id: string;
    schema_version: string;
    processing_options: any;
    total_descriptions: number;
    processed_descriptions: number;
    summary_statistics: any;
  };
  error?: string;
}

const API_BASE_URL = 'http://localhost:8000/api/polygon';

/**
 * Generate polygon coordinates from structured parcel data
 */
export const drawPolygonFromSchema = async (request: PolygonDrawingRequest): Promise<PolygonDrawingResponse> => {
  try {
    console.log('🔧 Drawing polygon from schema:', {
      hasData: !!request.parcel_data,
      options: request.options
    });

    const response = await fetch(`${API_BASE_URL}/draw`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request)
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    console.log('📐 Polygon drawing response:', data);

    return data;
  } catch (error) {
    console.error('❌ Polygon drawing error:', error);
    throw error;
  }
};

/**
 * Get available polygon drawing options
 */
export const getPolygonDrawingOptions = async () => {
  try {
    const response = await fetch(`${API_BASE_URL}/options`);
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Failed to load polygon drawing options:', error);
    throw error;
  }
}; 