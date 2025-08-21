/**
 * Legacy PLSS Overlay API
 * DEPRECATED: This file is kept for backward compatibility
 * New code should use the modular container overlay system
 */

import { ContainerApi, ContainerLayer } from './plss/containerApi';

export type OverlayLayer = 'townships' | 'ranges' | 'sections' | 'quarter_sections' | 'grid';

export interface OverlayFeatureCollection {
  type: 'FeatureCollection';
  features: Array<any>;
}

export interface PLSSCoordinates {
  latitude: number;
  longitude: number;
  trs_string: string;
}

export class PLSSOverlayApi {
  private containerApi = new ContainerApi();
  private schemaData?: any;

  /**
   * @deprecated Use ContainerApi instead
   */
  async getOverlay(
    layer: OverlayLayer, 
    state: string, 
    bounds?: { west: number; south: number; east: number; north: number }, 
    trs?: { t?: number; td?: string; r?: number; rd?: string; s?: number },
    abortSignal?: AbortSignal
  ): Promise<OverlayFeatureCollection> {
    console.warn('⚠️ PLSSOverlayApi.getOverlay is deprecated. Use ContainerApi instead.');
    
    // Convert legacy layer names to new format
    const containerLayer = this.convertLayerName(layer);
    
    if (!bounds) {
      throw new Error('Container overlays require bounds');
    }

    if (!this.schemaData) {
      throw new Error('Schema data not set. Call setSchemaData() first.');
    }

    try {
      const result = await this.containerApi.getOverlay(
        containerLayer,
        state,
        {
          schema_data: this.schemaData,
          container_bounds: bounds,
        },
        abortSignal
      );

      return {
        type: 'FeatureCollection',
        features: result.features,
      };
    } catch (error) {
      console.error('Container overlay request failed:', error);
      throw error;
    }
  }

  /**
   * @deprecated Use ContainerApi instead
   */
  setSchemaData(data: any) {
    console.warn('⚠️ PLSSOverlayApi.setSchemaData is deprecated. Use ContainerApi directly.');
    this.schemaData = data;
  }

  /**
   * @deprecated Use ContainerApi instead
   */
  async getCoordinates(lat: number, lon: number, state: string): Promise<PLSSCoordinates> {
    console.warn('⚠️ PLSSOverlayApi.getCoordinates is deprecated. Use dedicated coordinate service instead.');
    
    // This would need to be implemented with a proper coordinate service
    throw new Error('Coordinate lookup not implemented in container-only mode');
  }

  private convertLayerName(legacyLayer: OverlayLayer): ContainerLayer {
    switch (legacyLayer) {
      case 'townships':
        return 'township';
      case 'ranges':
        return 'range';
      case 'sections':
        return 'sections';
      case 'quarter_sections':
        return 'quarter-sections';
      case 'grid':
        return 'grid';
      default:
        throw new Error(`Unknown layer: ${legacyLayer}`);
    }
  }
}

// Default export for backward compatibility
const plssOverlayApi = new PLSSOverlayApi();
export default plssOverlayApi;


