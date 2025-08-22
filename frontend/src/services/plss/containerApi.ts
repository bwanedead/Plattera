/**
 * Container PLSS API
 * Dedicated service for container-based PLSS overlays
 * Clean, focused API for parcel-relative overlay data
 */

export type ContainerLayer = 'township' | 'range' | 'grid' | 'sections' | 'quarter-sections' | 'subdivisions';

export interface ContainerRequest {
  schema_data: any;
  container_bounds: {
    west: number;
    south: number;
    east: number;
    north: number;
  };
}

export interface ContainerResponse {
  type: 'FeatureCollection';
  features: Array<any>;
  validation: {
    status: string;
    features_returned: number;
    engine: string;
    requested_township?: string;
    requested_range?: string;
    cell_identifier?: string;
    spatial_validation?: any;
    [key: string]: any;
  };
}

export class ContainerApi {
  private baseUrl = 'http://localhost:8000/api/plss/container';

  /**
   * Get container overlay for a specific layer
   */
  async getOverlay(
    layer: ContainerLayer,
    state: string,
    request: ContainerRequest,
    abortSignal?: AbortSignal
  ): Promise<ContainerResponse> {
    const url = `${this.baseUrl}/${layer}/${state}`;
    
    console.log(`🎯 Container overlay request: ${layer} for ${state}`);
    console.log(`📍 Container bounds:`, request.container_bounds);
    
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
      signal: abortSignal,
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Container overlay failed (${response.status}): ${errorText}`);
    }

    const result = await response.json();
    
    console.log(`✅ Container ${layer} overlay loaded: ${result.validation?.features_returned || 0} features`);
    console.log(`🔍 Validation:`, result.validation);
    
    return result;
  }

  /**
   * Get multiple container overlays in parallel
   */
  async getMultipleOverlays(
    layers: ContainerLayer[],
    state: string,
    request: ContainerRequest,
    abortSignal?: AbortSignal
  ): Promise<Map<ContainerLayer, ContainerResponse>> {
    const promises = layers.map(layer => 
      this.getOverlay(layer, state, request, abortSignal)
        .then(result => ({ layer, result }))
        .catch(error => ({ layer, error }))
    );

    const results = await Promise.allSettled(promises);
    const overlayMap = new Map<ContainerLayer, ContainerResponse>();

    results.forEach((result, index) => {
      if (result.status === 'fulfilled') {
        const value = result.value;
        if ('error' in value) {
          console.error(`❌ Container ${value.layer} overlay failed:`, value.error);
        } else {
          overlayMap.set(value.layer, value.result);
        }
      } else {
        const layer = layers[index];
        console.error(`❌ Container ${layer} overlay failed:`, result.reason);
      }
    });

    return overlayMap;
  }

  /**
   * Validate container request data
   */
  validateRequest(request: ContainerRequest): { valid: boolean; errors: string[] } {
    const errors: string[] = [];

    if (!request.schema_data) {
      errors.push('Schema data is required');
    }

    if (!request.container_bounds) {
      errors.push('Container bounds are required');
    } else {
      const { west, south, east, north } = request.container_bounds;
      if (typeof west !== 'number' || typeof south !== 'number' || 
          typeof east !== 'number' || typeof north !== 'number') {
        errors.push('Container bounds must be numbers');
      }
      if (west >= east) {
        errors.push('West bound must be less than east bound');
      }
      if (south >= north) {
        errors.push('South bound must be less than north bound');
      }
    }

    return {
      valid: errors.length === 0,
      errors
    };
  }
}

// Default export for easy importing
export default ContainerApi;


