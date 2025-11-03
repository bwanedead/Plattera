/**
 * PLSS Services - Cache, Coordinate lookups, and data management
 *
 * Handles PLSS coordinate lookups and calculations without proxy
 *
 * Domain: PLSS (Public Land Survey System) Coordinates
 * Responsibility: Direct backend communication and caching for coordinate operations
 */

export interface PLSSCoordinateRequest {
  latitude: number;
  longitude: number;
  state: string;
  search_radius_miles?: number;
}

export interface PLSSCoordinateResult {
  success: boolean;
  longitude?: number;
  latitude?: number;
  plss_reference?: string;
  township?: number;
  township_direction?: string;
  range_number?: number;
  range_direction?: string;
  section?: number;
  quarter_sections?: string;
  distance_miles?: number;
  method?: string;
  error?: string;
  fallback?: boolean;
  search_location?: {
    latitude: number;
    longitude: number;
    state: string;
    search_radius_miles: number;
  };
}

/**
 * PLSS Coordinate Service
 * 
 * Provides direct backend communication for PLSS coordinate operations
 */
export class PLSSCoordinateService {
  private readonly apiBase = 'http://localhost:8000/api/plss';

  /**
   * Find nearest PLSS feature to given coordinates
   */
  async findNearestPLSS(request: PLSSCoordinateRequest): Promise<PLSSCoordinateResult> {
    try {
      console.log(`🔍 PLSS Coordinate Service: Finding nearest PLSS for ${request.latitude.toFixed(6)}, ${request.longitude.toFixed(6)} in ${request.state}`);
      
      const response = await fetch(`${this.apiBase}/find-nearest-plss`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          latitude: request.latitude,
          longitude: request.longitude,
          state: request.state,
          search_radius_miles: request.search_radius_miles || 1.0
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      console.log(`📡 Raw response received:`, response);
      const data = await response.json();
      console.log(`📋 Parsed response data:`, data);

      if (data.success) {
        console.log(`✅ PLSS Coordinate Service: Found ${data.plss_reference} at ${data.latitude.toFixed(6)}, ${data.longitude.toFixed(6)}`);
        return {
          success: true,
          longitude: data.longitude,
          latitude: data.latitude,
          plss_reference: data.plss_reference,
          township: data.township,
          township_direction: data.township_direction,
          range_number: data.range_number,
          range_direction: data.range_direction,
          section: data.section,
          quarter_sections: data.quarter_sections,
          distance_miles: data.distance_miles,
          method: data.method
        };
      } else {
        console.log(`❌ PLSS Coordinate Service: Backend lookup failed - ${data.error || 'No result returned'}`);
        return {
          success: false,
          error: data.error || 'No PLSS feature found',
          fallback: data.fallback || false,
          search_location: data.search_location
        };
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      console.error('❌ PLSS Coordinate Service: Network error -', errorMessage);
      return {
        success: false,
        error: `Network error: ${errorMessage}`
      };
    }
  }

  /**
   * Test backend connectivity
   */
  async testConnection(): Promise<{ success: boolean; error?: string }> {
    try {
      const response = await fetch(`${this.apiBase}/find-nearest-plss`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          latitude: 41.0,
          longitude: -105.0,
          state: 'Wyoming',
          search_radius_miles: 0.1
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      await response.json();
      return { success: true };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }
}

// Singleton instance for app-wide use
export const plssCoordinateService = new PLSSCoordinateService();

/**
 * PLSS Cache Service
 *
 * Caches PLSS section data from container overlays for efficient snap detection
 * Avoids re-querying parquet files when user clicks on already-displayed sections
 *
 * Domain: PLSS Data Caching
 * Responsibility: Cache management for PLSS section features
 */

export interface PLSSCacheSection {
  section_number: string;
  township_number: number;
  township_direction: string;
  range_number: number;
  range_direction: string;
  corners: Array<{
    latitude: number;
    longitude: number;
    corner_type?: string; // NW, NE, SW, SE
  }>;
  plss_reference: string;
  geometry: {
    type: 'Polygon';
    coordinates: number[][][];
  };
}

export interface PLSSCacheEntry {
  sections: PLSSCacheSection[];
  timestamp: number;
  cell_identifier: string;
}

export class PLSSCacheService {
  private cache = new Map<string, PLSSCacheEntry>();
  private readonly CACHE_TTL = 30 * 60 * 1000; // 30 minutes

  /**
   * Store PLSS sections from container overlay response
   */
  public storeSections(containerResponse: any): void {
    try {
      if (!containerResponse?.features) return;

      const validation = containerResponse.validation;
      if (!validation?.cell_identifier) return;

      const cellId = validation.cell_identifier;
      const sections: PLSSCacheSection[] = [];

      for (const feature of containerResponse.features) {
        if (feature.properties?.feature_type === 'section') {
          const corners = this.extractCorners(feature.geometry);

          const section: PLSSCacheSection = {
            section_number: feature.properties.section_number || feature.properties.SECNUM,
            township_number: feature.properties.township_number,
            township_direction: feature.properties.township_direction,
            range_number: feature.properties.range_number,
            range_direction: feature.properties.range_direction,
            corners,
            plss_reference: `T${feature.properties.township_number}${feature.properties.township_direction} R${feature.properties.range_number}${feature.properties.range_direction} S${feature.properties.section_number}`,
            geometry: feature.geometry
          };

          sections.push(section);
        }
      }

      if (sections.length > 0) {
        this.cache.set(cellId, {
          sections,
          timestamp: Date.now(),
          cell_identifier: cellId
        });

        console.log(`💾 Cached ${sections.length} PLSS sections for ${cellId}`);
      }
    } catch (error) {
      console.warn('Failed to cache PLSS sections:', error);
    }
  }

  /**
   * Find nearest cached corner to given coordinates
   */
  public findNearestSection(
    latitude: number,
    longitude: number,
    searchRadiusMiles: number = 1.0
  ): PLSSCacheSection | null {
    const result = this.findNearestCorner(latitude, longitude, searchRadiusMiles);
    return result ? result.section : null;
  }

  /**
   * Find nearest cached corner with detailed information
   */
  public findNearestCorner(
    latitude: number,
    longitude: number,
    searchRadiusMiles: number = 1.0
  ): { section: PLSSCacheSection; corner: { latitude: number; longitude: number; corner_type?: string }; distance: number } | null {
    try {
      console.log(`🔍 Searching PLSS cache for nearest corner to ${latitude}, ${longitude}`);

      // Clean expired entries
      this.cleanExpiredEntries();

      let nearestSection: PLSSCacheSection | null = null;
      let nearestCorner: { latitude: number; longitude: number; corner_type?: string } | null = null;
      let minDistance = Infinity;
      const searchRadiusDegrees = searchRadiusMiles / 69.0; // Approximate conversion

      for (const [cellId, entry] of this.cache.entries()) {
        for (const section of entry.sections) {
          // Check each corner of the section
          for (const corner of section.corners) {
            const distance = this.calculateDistance(
              latitude, longitude,
              corner.latitude, corner.longitude
            );

            if (distance <= searchRadiusDegrees && distance < minDistance) {
              minDistance = distance;
              nearestSection = section;
              nearestCorner = corner;
            }
          }
        }
      }

      if (nearestSection && nearestCorner) {
        const distanceMiles = minDistance * 69.0;
        console.log(`✅ Found cached section corner: ${nearestSection.plss_reference} ${nearestCorner.corner_type || 'corner'} (${distanceMiles.toFixed(2)} miles away)`);
        console.log(`📍 Corner coordinates: ${nearestCorner.latitude}, ${nearestCorner.longitude}`);
        return {
          section: nearestSection,
          corner: nearestCorner,
          distance: minDistance
        };
      } else {
        console.log(`❌ No cached section corners found within ${searchRadiusMiles} miles`);
        return null;
      }
    } catch (error) {
      console.warn('Error searching PLSS cache:', error);
      return null;
    }
  }

  /**
   * Extract corners from polygon geometry
   */
  private extractCorners(geometry: any): Array<{ latitude: number; longitude: number; corner_type?: string }> {
    if (geometry.type !== 'Polygon' || !geometry.coordinates?.[0]) {
      return [];
    }

    const coords = geometry.coordinates[0];
    const corners: Array<{ latitude: number; longitude: number; corner_type?: string }> = [];

    // Extract all vertices as corners (excluding the closing duplicate)
    for (let i = 0; i < coords.length - 1; i++) {
      const [lon, lat] = coords[i];
      if (typeof lat === 'number' && typeof lon === 'number') {
        corners.push({
          latitude: lat,
          longitude: lon,
          corner_type: this.getCornerType(i, coords.length - 1) // -1 because we exclude closing duplicate
        });
      }
    }

    return corners;
  }

  /**
   * Determine corner type based on position in polygon
   */
  private getCornerType(index: number, totalCorners: number): string {
    // For a standard section polygon, corners are typically in order: SW, NW, NE, SE
    const cornerTypes = ['SW', 'NW', 'NE', 'SE'];
    if (totalCorners === 4 && index < cornerTypes.length) {
      return cornerTypes[index];
    }
    return `corner_${index}`;
  }

  /**
   * Calculate centroid of polygon geometry (kept for backward compatibility)
   */
  private calculateCentroid(geometry: any): { latitude: number; longitude: number } {
    if (geometry.type !== 'Polygon' || !geometry.coordinates?.[0]) {
      return { latitude: 0, longitude: 0 };
    }

    const coords = geometry.coordinates[0];
    let sumLat = 0;
    let sumLon = 0;
    let count = 0;

    for (const [lon, lat] of coords) {
      if (typeof lat === 'number' && typeof lon === 'number') {
        sumLat += lat;
        sumLon += lon;
        count++;
      }
    }

    return {
      latitude: count > 0 ? sumLat / count : 0,
      longitude: count > 0 ? sumLon / count : 0
    };
  }

  /**
   * Calculate distance between two points in degrees
   */
  private calculateDistance(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const dlat = lat2 - lat1;
    const dlon = lon2 - lon1;
    return Math.sqrt(dlat * dlat + dlon * dlon);
  }

  /**
   * Clean expired cache entries
   */
  private cleanExpiredEntries(): void {
    const now = Date.now();
    for (const [cellId, entry] of this.cache.entries()) {
      if (now - entry.timestamp > this.CACHE_TTL) {
        this.cache.delete(cellId);
        console.log(`🗑️ Removed expired PLSS cache entry: ${cellId}`);
      }
    }
  }

  /**
   * Clear all cached data
   */
  public clearCache(): void {
    this.cache.clear();
    console.log('🗑️ Cleared PLSS cache');
  }

  /**
   * Get cache status
   */
  public getCacheStatus(): { totalEntries: number; totalSections: number } {
    let totalSections = 0;
    for (const entry of this.cache.values()) {
      totalSections += entry.sections.length;
    }

    return {
      totalEntries: this.cache.size,
      totalSections
    };
  }
}

// Singleton instance for app-wide use
export const plssCache = new PLSSCacheService();
