/**
 * Coordinate Projection Utilities
 * Web Mercator (EPSG:3857) projection for map tile integration
 */

// Earth radius in meters (WGS84)
const EARTH_RADIUS = 6378137;

/**
 * Convert latitude/longitude to Web Mercator coordinates (EPSG:3857)
 * 
 * @param lon Longitude in decimal degrees
 * @param lat Latitude in decimal degrees
 * @returns [x, y] coordinates in Web Mercator projection (meters)
 */
export function latLonToWebMercator(lon: number, lat: number): [number, number] {
  const x = EARTH_RADIUS * lon * Math.PI / 180;
  const y = EARTH_RADIUS * Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360));
  return [x, y];
}

/**
 * Convert Web Mercator coordinates to latitude/longitude (EPSG:4326)
 * 
 * @param x X coordinate in Web Mercator (meters)
 * @param y Y coordinate in Web Mercator (meters)
 * @returns [lon, lat] coordinates in decimal degrees
 */
export function webMercatorToLatLon(x: number, y: number): [number, number] {
  const lon = (x / EARTH_RADIUS) * 180 / Math.PI;
  const lat = (2 * Math.atan(Math.exp(y / EARTH_RADIUS)) - Math.PI / 2) * 180 / Math.PI;
  return [lon, lat];
}

/**
 * Convert array of lat/lon coordinates to Web Mercator
 * 
 * @param coordinates Array of [lon, lat] pairs
 * @returns Array of [x, y] Web Mercator coordinates
 */
export function coordinatesToWebMercator(coordinates: [number, number][]): [number, number][] {
  return coordinates.map(([lon, lat]) => latLonToWebMercator(lon, lat));
}

/**
 * Convert array of Web Mercator coordinates to lat/lon
 * 
 * @param coordinates Array of [x, y] Web Mercator pairs
 * @returns Array of [lon, lat] coordinates
 */
export function coordinatesFromWebMercator(coordinates: [number, number][]): [number, number][] {
  return coordinates.map(([x, y]) => webMercatorToLatLon(x, y));
}

/**
 * Calculate bounding box in Web Mercator from lat/lon bounds
 * 
 * @param bounds Geographic bounds {min_lat, max_lat, min_lon, max_lon}
 * @returns Web Mercator bounds {min_x, max_x, min_y, max_y}
 */
export function boundingBoxToWebMercator(bounds: {
  min_lat: number;
  max_lat: number;
  min_lon: number;
  max_lon: number;
}): {
  min_x: number;
  max_x: number;
  min_y: number;
  max_y: number;
} {
  const [min_x, min_y] = latLonToWebMercator(bounds.min_lon, bounds.min_lat);
  const [max_x, max_y] = latLonToWebMercator(bounds.max_lon, bounds.max_lat);
  
  return { min_x, max_x, min_y, max_y };
}

/**
 * Calculate geographic bounds from Web Mercator bounding box
 * 
 * @param bounds Web Mercator bounds {min_x, max_x, min_y, max_y}
 * @returns Geographic bounds {min_lat, max_lat, min_lon, max_lon}
 */
export function boundingBoxFromWebMercator(bounds: {
  min_x: number;
  max_x: number;
  min_y: number;
  max_y: number;
}): {
  min_lat: number;
  max_lat: number;
  min_lon: number;
  max_lon: number;
} {
  const [min_lon, min_lat] = webMercatorToLatLon(bounds.min_x, bounds.min_y);
  const [max_lon, max_lat] = webMercatorToLatLon(bounds.max_x, bounds.max_y);
  
  return { min_lat, max_lat, min_lon, max_lon };
}

/**
 * Tile coordinate conversion utilities for zoom/tile calculations
 */
export const TileUtils = {
  /**
   * Convert longitude to tile X coordinate at given zoom
   */
  longitudeToTileX(lon: number, zoom: number): number {
    return ((lon + 180) / 360) * Math.pow(2, zoom);
  },

  /**
   * Convert latitude to tile Y coordinate at given zoom
   */
  latitudeToTileY(lat: number, zoom: number): number {
    return (1 - Math.log(Math.tan(lat * Math.PI / 180) + 1 / Math.cos(lat * Math.PI / 180)) / Math.PI) / 2 * Math.pow(2, zoom);
  },

  /**
   * Convert tile X coordinate to longitude at given zoom
   */
  tileXToLongitude(x: number, zoom: number): number {
    return x / Math.pow(2, zoom) * 360 - 180;
  },

  /**
   * Convert tile Y coordinate to latitude at given zoom
   */
  tileYToLatitude(y: number, zoom: number): number {
    const n = Math.PI - 2 * Math.PI * y / Math.pow(2, zoom);
    return 180 / Math.PI * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
  },

  /**
   * Calculate tile bounds in geographic coordinates
   */
  tileBounds(x: number, y: number, zoom: number): {
    min_lat: number;
    max_lat: number;
    min_lon: number;
    max_lon: number;
  } {
    const min_lon = this.tileXToLongitude(x, zoom);
    const max_lon = this.tileXToLongitude(x + 1, zoom);
    const min_lat = this.tileYToLatitude(y + 1, zoom);
    const max_lat = this.tileYToLatitude(y, zoom);
    
    return { min_lat, max_lat, min_lon, max_lon };
  }
};

/**
 * Polygon projection utilities
 */
export const PolygonProjection = {
  /**
   * Project polygon coordinates from lat/lon to Web Mercator for map display
   * 
   * @param polygon Array of [lon, lat] coordinate pairs
   * @returns Projected polygon in Web Mercator coordinates
   */
  projectToWebMercator(polygon: [number, number][]): [number, number][] {
    return coordinatesToWebMercator(polygon);
  },

  /**
   * Calculate polygon centroid in Web Mercator coordinates
   * 
   * @param polygon Web Mercator polygon coordinates
   * @returns [x, y] centroid coordinates
   */
  calculateCentroid(polygon: [number, number][]): [number, number] {
    const sumX = polygon.reduce((sum, [x, _]) => sum + x, 0);
    const sumY = polygon.reduce((sum, [_, y]) => sum + y, 0);
    return [sumX / polygon.length, sumY / polygon.length];
  },

  /**
   * Calculate polygon bounds in Web Mercator coordinates
   * 
   * @param polygon Web Mercator polygon coordinates
   * @returns Bounding box {min_x, max_x, min_y, max_y}
   */
  calculateBounds(polygon: [number, number][]): {
    min_x: number;
    max_x: number;
    min_y: number;
    max_y: number;
  } {
    const xs = polygon.map(([x, _]) => x);
    const ys = polygon.map(([_, y]) => y);
    
    return {
      min_x: Math.min(...xs),
      max_x: Math.max(...xs),
      min_y: Math.min(...ys),
      max_y: Math.max(...ys)
    };
  }
};

export const TILE_SIZE = 256;

export function lonLatToPixel(
  lon: number,
  lat: number,
  zoom: number,
  tileSize: number = TILE_SIZE
): { x: number; y: number } {
  const scale = tileSize * Math.pow(2, zoom);
  const x = (lon + 180) / 360 * scale;
  const sinLat = Math.sin((lat * Math.PI) / 180);
  const y = (0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI)) * scale;
  return { x, y };
}

export function pixelToLonLat(
  x: number,
  y: number,
  zoom: number,
  tileSize: number = TILE_SIZE
): [number, number] {
  const scale = tileSize * Math.pow(2, zoom);
  const lon = (x / scale) * 360 - 180;
  const n = Math.PI - (2 * Math.PI * y) / scale;
  const lat = (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
  return [lon, lat];
}

export function wrapTileX(x: number, zoom: number): number {
  const n = Math.pow(2, zoom);
  return ((x % n) + n) % n;
}