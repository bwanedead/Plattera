/**
 * Container Overlay API
 * Dedicated service for container-based PLSS overlays
 * Clean, focused API for parcel-relative overlay data
 */

export type ContainerOverlayLayer = 'township' | 'range' | 'grid' | 'sections' | 'quarter-sections';

export interface ContainerOverlayRequest {
  schema_data: any;
  container_bounds: {
    west: number;
    south: number;
    east: number;
    north: number;
  };
}

export interface ContainerOverlayResponse {
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

export class ContainerOverlayApi {
  private baseUrl = 'http://localhost:8000/api/plss/container';

  /**
   * Get container overlay for a specific layer
   */
  async getContainerOverlay(
    layer: ContainerOverlayLayer,
    state: string,
    request: ContainerOverlayRequest,
    abortSignal?: AbortSignal
  ): Promise<ContainerOverlayResponse> {
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
  async getMultipleContainerOverlays(
    layers: ContainerOverlayLayer[],
    state: string,
    request: ContainerOverlayRequest,
    abortSignal?: AbortSignal
  ): Promise<Map<ContainerOverlayLayer, ContainerOverlayResponse>> {
    const promises = layers.map(layer => 
      this.getContainerOverlay(layer, state, request, abortSignal)
        .then(result => ({ layer, result }))
        .catch(error => ({ layer, error }))
    );

    const results = await Promise.allSettled(promises);
    const overlayMap = new Map<ContainerOverlayLayer, ContainerOverlayResponse>();

    results.forEach((result, index) => {
      if (result.status === 'fulfilled' && !('error' in result.value)) {
        overlayMap.set(result.value.layer, result.value.result);
      } else {
        const layer = layers[index];
        const error = result.status === 'rejected' ? result.reason : result.value.error;
        console.error(`❌ Container ${layer} overlay failed:`, error);
      }
    });

    return overlayMap;
  }
}


