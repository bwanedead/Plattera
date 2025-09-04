/**
 * Measurement Utilities
 * Mathematical functions for distance, bearing, and coordinate calculations
 */

export interface MeasurementPoint {
  lng: number;
  lat: number;
  snappedFeature?: string;
}

export interface Measurement {
  id: string;
  points: MeasurementPoint[];
  distance: number;
  bearing?: number;
  isVisible: boolean;
}

export type CalculationMethod = 'haversine' | 'utm' | 'geodesic';

/**
 * Calculate distance between two points using Haversine formula
 * Returns distance in feet
 */
export function calculateDistance(point1: MeasurementPoint, point2: MeasurementPoint): number {
  const R = 3959; // Earth's radius in miles
  const dLat = (point2.lat - point1.lat) * Math.PI / 180;
  const dLon = (point2.lng - point1.lng) * Math.PI / 180;
  const a =
    Math.sin(dLat/2) * Math.sin(dLat/2) +
    Math.cos(point1.lat * Math.PI / 180) * Math.cos(point2.lat * Math.PI / 180) *
    Math.sin(dLon/2) * Math.sin(dLon/2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  return R * c * 5280; // Convert to feet
}

/**
 * Calculate bearing between two points
 * Returns bearing in degrees (0-360)
 */
export function calculateBearing(point1: MeasurementPoint, point2: MeasurementPoint): number {
  const dLon = (point2.lng - point1.lng) * Math.PI / 180;
  const lat1 = point1.lat * Math.PI / 180;
  const lat2 = point2.lat * Math.PI / 180;

  const y = Math.sin(dLon) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);

  const bearing = Math.atan2(y, x) * 180 / Math.PI;
  return (bearing + 360) % 360; // Normalize to 0-360
}

/**
 * Calculate end point from start point, distance, and bearing
 */
export function calculateEndPoint(
  startPoint: MeasurementPoint,
  distanceFeet: number,
  bearingDegrees: number
): MeasurementPoint {
  const R = 3959; // Earth radius in miles
  const d = distanceFeet / 5280 / R; // Convert feet to radians
  const bearingRad = bearingDegrees * Math.PI / 180;

  const lat1 = startPoint.lat * Math.PI / 180;
  const lon1 = startPoint.lng * Math.PI / 180;

  const lat2 = Math.asin(Math.sin(lat1) * Math.cos(d) + Math.cos(lat1) * Math.sin(d) * Math.cos(bearingRad));
  const lon2 = lon1 + Math.atan2(Math.sin(bearingRad) * Math.sin(d) * Math.cos(lat1), Math.cos(d) - Math.sin(lat1) * Math.sin(lat2));

  return {
    lng: lon2 * 180 / Math.PI,
    lat: lat2 * 180 / Math.PI
  };
}

/**
 * Calculate end point using backend coordinate calculation API
 */
export async function calculateEndPointBackend(
  startPoint: MeasurementPoint,
  distanceFeet: number,
  bearingDegrees: number,
  method: CalculationMethod = 'geodesic'
): Promise<MeasurementPoint> {
  try {
    console.log(`🧮 Calling backend ${method} calculation...`);

    const response = await fetch('http://localhost:8000/api/mapping/coordinates/calculate-endpoint', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        start_lat: startPoint.lat,
        start_lng: startPoint.lng,
        bearing_degrees: bearingDegrees,
        distance_feet: distanceFeet,
        method: method
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();

    if (data.success) {
      console.log(`✅ Backend ${method} calculation successful`);

      // Log quality information if available
      if (data.quality_check) {
        const agreement = data.quality_check.agreement_distance_meters;
        if (agreement > 0.1) {
          console.warn(`⚠️ Method quality check: ${agreement.toFixed(3)}m difference from reference`);
        } else {
          console.log(`✅ Method quality check: ${agreement.toFixed(3)}m agreement with reference`);
        }
      }

      return {
        lng: data.end_lng,
        lat: data.end_lat,
        snappedFeature: `Calculated using ${method} method`
      };
    } else {
      console.warn(`❌ Backend ${method} calculation failed:`, data.error);
      throw new Error(data.error || 'Backend calculation failed');
    }
  } catch (error) {
    console.warn(`🚨 Backend ${method} calculation error:`, error);
    throw error;
  }
}

/**
 * Calculate end point using Haversine method via backend
 */
export async function calculateEndPointHaversine(
  startPoint: MeasurementPoint,
  distanceFeet: number,
  bearingDegrees: number
): Promise<MeasurementPoint> {
  return calculateEndPointBackend(startPoint, distanceFeet, bearingDegrees, 'haversine');
}

/**
 * Calculate end point using UTM method via backend
 */
export async function calculateEndPointUTM(
  startPoint: MeasurementPoint,
  distanceFeet: number,
  bearingDegrees: number
): Promise<MeasurementPoint> {
  return calculateEndPointBackend(startPoint, distanceFeet, bearingDegrees, 'utm');
}

/**
 * Calculate end point using GeographicLib method via backend
 */
export async function calculateEndPointGeodesic(
  startPoint: MeasurementPoint,
  distanceFeet: number,
  bearingDegrees: number
): Promise<MeasurementPoint> {
  return calculateEndPointBackend(startPoint, distanceFeet, bearingDegrees, 'geodesic');
}

/**
 * Find nearest PLSS feature for snapping
 */
export async function findNearestPLSSFeature(
  lng: number,
  lat: number,
  map: any,
  snappingEnabled: boolean,
  stateName?: string
): Promise<MeasurementPoint> {
  if (!snappingEnabled) {
    console.log('🔍 Snapping disabled, returning original coordinates');
    return { lng, lat };
  }

  console.log(`🔍 SNAP DETECTION: Finding nearest PLSS feature for ${lat.toFixed(6)}, ${lng.toFixed(6)} in ${stateName || 'unknown state'}`);

  // Add visual alert to confirm snap detection is running
  if (typeof window !== 'undefined') {
    console.log('🚨 SNAP DETECTION ALERT: Function called!');
  }

  try {
    // First try backend PLSS coordinate lookup
    if (stateName) {
      console.log('🔍 Trying backend PLSS lookup...');
      const backendResult = await findNearestPLSSFromBackend(lng, lat, stateName);
      if (backendResult) {
        console.log(`✅ Backend snap found: ${backendResult.snappedFeature} at ${backendResult.lat.toFixed(6)}, ${backendResult.lng.toFixed(6)}`);
        return backendResult;
      }
      console.log('❌ Backend lookup returned no results');
    } else {
      console.log('⚠️ No state name provided for backend lookup');
    }

    // Fallback to map feature query using existing PLSS overlay data
    console.log('🔍 Trying map feature fallback...');

    // First, let's see what layers are actually available
    const allLayers = map?.getStyle()?.layers || [];
    const layerNames = allLayers.map(layer => layer.id);
    console.log('🔍 Available map layers:', layerNames);

    // Try to find ALL PLSS-related layers (container, plss, sections, township, etc.)
    const plssLayers = layerNames.filter(name =>
      name.includes('container') ||
      name.includes('plss') ||
      name.includes('section') ||
      name.includes('township') ||
      name.includes('range') ||
      name.includes('grid') ||
      name.includes('quarter') ||
      name.includes('subdivision')
    );
    console.log('🔍 Potential PLSS layers:', plssLayers);

    // Get the click point in screen coordinates
    const clickPoint = map.project([lng, lat]);
    console.log(`🔍 Original click point (screen coords): x=${clickPoint.x}, y=${clickPoint.y}`);
    console.log(`🔍 Original click point (lat/lng): ${lat.toFixed(6)}, ${lng.toFixed(6)}`);

    // Try querying with a larger radius (30px box around click)
    const searchBox = [
      [clickPoint.x - 30, clickPoint.y - 30],
      [clickPoint.x + 30, clickPoint.y + 30]
    ];

    let features = map?.queryRenderedFeatures(searchBox, {
      layers: plssLayers.length > 0 ? plssLayers : undefined
    });

    console.log(`🔍 Map query (30px radius) found ${features?.length || 0} features`);

    // If no features found with specific layers, try querying all layers
    if ((!features || features.length === 0) && plssLayers.length > 0) {
      console.log('🔍 No features found with PLSS layers, trying ALL layers...');
      features = map?.queryRenderedFeatures(searchBox);
      console.log(`🔍 All layers query found ${features?.length || 0} features`);
    }

    // Log detailed feature information
    if (features && features.length > 0) {
      console.log('🔍 Found features:');
      features.forEach((feature, index) => {
        console.log(`  Feature ${index + 1}:`, {
          layer: feature.layer?.id,
          sourceLayer: feature.sourceLayer,
          geometryType: feature.geometry?.type,
          properties: feature.properties
        });
      });
    }

    if (features && features.length > 0) {
      // Find the closest feature by calculating distances
      let closestFeature = features[0];
      let minDistance = Number.MAX_VALUE;

      console.log('🔍 Calculating distances for all features...');

      features.forEach((feature, index) => {
        const geometry = feature.geometry;
        let snapPoint: number[] = [];
        let distance = Number.MAX_VALUE;

        if (geometry.type === 'Point') {
          snapPoint = geometry.coordinates;
          distance = Math.sqrt(
            Math.pow(geometry.coordinates[0] - lng, 2) +
            Math.pow(geometry.coordinates[1] - lat, 2)
          );
        } else if (geometry.type === 'Polygon') {
          // For polygons, find the closest corner (vertex) instead of centroid
          const coordinates = geometry.coordinates[0]; // Outer ring
          let closestCorner = coordinates[0];
          let minCornerDistance = Number.MAX_VALUE;

          coordinates.forEach((coord: number[]) => {
            const cornerDistance = Math.sqrt(
              Math.pow(coord[0] - lng, 2) +
              Math.pow(coord[1] - lat, 2)
            );
            if (cornerDistance < minCornerDistance) {
              minCornerDistance = cornerDistance;
              closestCorner = coord;
            }
          });

          snapPoint = closestCorner;
          distance = minCornerDistance;
        } else if (geometry.type === 'LineString' || geometry.type === 'MultiLineString') {
          // For lines, find closest point on the line
          const coordinates = geometry.type === 'LineString'
            ? geometry.coordinates
            : geometry.coordinates[0];

          let closestPoint = coordinates[0];
          distance = Number.MAX_VALUE;

          coordinates.forEach((coord: number[]) => {
            const dist = Math.sqrt(
              Math.pow(coord[0] - lng, 2) +
              Math.pow(coord[1] - lat, 2)
            );
            if (dist < distance) {
              distance = dist;
              closestPoint = coord;
            }
          });

          snapPoint = closestPoint;
        }

        console.log(`  Feature ${index + 1} distance: ${distance.toFixed(6)} (${geometry.type})`);

        if (distance < minDistance) {
          minDistance = distance;
          closestFeature = {
            ...feature,
            geometry: { type: 'Point', coordinates: snapPoint }
          };
        }
      });

      const geometry = closestFeature.geometry;
      const properties = closestFeature.properties;

      console.log(`🔍 Closest feature selected (distance: ${minDistance.toFixed(6)}):`, {
        layer: closestFeature.layer?.id,
        geometryType: geometry.type,
        properties: properties
      });

      if (geometry.type === 'Point') {
        // Extract feature name from various possible property names
        let snappedFeature = 'PLSS Feature';

        if (properties?.SECNUM || properties?.FRSTDIVNO) {
          snappedFeature = `Section ${properties.SECNUM || properties.FRSTDIVNO}`;
        } else if (properties?.name) {
          snappedFeature = properties.name;
        } else if (properties?.section) {
          snappedFeature = `Section ${properties.section}`;
        } else if (properties?.township && properties?.range) {
          snappedFeature = `T${properties.township}${properties.township_direction}-R${properties.range}${properties.range_direction}`;
        } else if (closestFeature.layer?.id) {
          // Use layer name as fallback
          snappedFeature = closestFeature.layer.id.replace(/container-/, '').replace(/-/g, ' ');
        }

        console.log(`✅ Map snap found: ${snappedFeature} at ${geometry.coordinates[1]}, ${geometry.coordinates[0]}`);
        console.log(`   Original click: ${lat}, ${lng}`);
        console.log(`   Snap distance: ${(minDistance * 111320).toFixed(1)} meters`);

        return {
          lng: geometry.coordinates[0] as number,
          lat: geometry.coordinates[1] as number,
          snappedFeature
        };
      }
    }

    console.log('❌ No PLSS features found in map query, returning original coordinates');
  } catch (error) {
    console.warn('PLSS snapping failed:', error);
  }

  console.log('🔄 Returning original coordinates (no snap found)');
  return { lng, lat };
}

/**
 * Query backend for nearest PLSS coordinates
 */
export async function findNearestPLSSFromBackend(
  lng: number,
  lat: number,
  stateName: string
): Promise<MeasurementPoint | null> {
  try {
    // First, try the PLSS cache (much faster and more accurate)
    const { plssCache } = await import('../services/plss');
    const cachedResult = plssCache.findNearestSection(lat, lng, 1.0);

    if (cachedResult) {
      console.log(`🎯 Using cached PLSS section: ${cachedResult.plss_reference}`);
      return {
        lng: cachedResult.centroid.longitude,
        lat: cachedResult.centroid.latitude,
        snappedFeature: `Section ${cachedResult.section_number.padStart(2, '0')}`
      };
    }

    console.log(`🔄 No cached PLSS sections found, falling back to backend lookup`);

    // Use the new PLSSCoordinateService instead of direct fetch
    const { plssCoordinateService } = await import('../services/plss');

    const result = await plssCoordinateService.findNearestPLSS({
      latitude: lat,
      longitude: lng,
      state: stateName,
      search_radius_miles: 1.0
    });

    if (result.success && result.longitude && result.latitude) {
      return {
        lng: result.longitude,
        lat: result.latitude,
        snappedFeature: result.plss_reference || `PLSS ${result.township}${result.township_direction}-${result.range_number}${result.range_direction}-${result.section}`
      };
    } else {
      console.debug('Backend PLSS lookup failed:', result.error);
    }
  } catch (error) {
    console.debug('Backend PLSS lookup failed, falling back to map features:', error instanceof Error ? error.message : 'Unknown error');
  }

  return null;
}

/**
 * Format distance for display
 */
export function formatDistance(feet: number): string {
  if (feet >= 5280) {
    return `${(feet / 5280).toFixed(2)} mi`;
  } else if (feet >= 100) {
    return `${feet.toFixed(0)} ft`;
  } else {
    return `${feet.toFixed(1)} ft`;
  }
}

/**
 * Format bearing for display
 */
export function formatBearing(degrees: number): string {
  const directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
  const index = Math.round(degrees / 45) % 8;
  return `${degrees.toFixed(1)}° ${directions[index]}`;
}

/**
 * Convert cardinal direction to bearing degrees
 */
export function directionToBearing(direction: string): number {
  const directionMap: Record<string, number> = {
    'N': 0,
    'NE': 45,
    'E': 90,
    'SE': 135,
    'S': 180,
    'SW': 225,
    'W': 270,
    'NW': 315,
  };
  return directionMap[direction] || 0;
}

/**
 * Generate unique measurement ID
 */
export function generateMeasurementId(): string {
  return `measurement-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}
