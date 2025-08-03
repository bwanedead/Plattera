/**
 * Simple coordinate utilities for display-ready coordinates
 */

export interface BBox {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

export interface WorldCoordinate {
  x: number;
  y: number;
}

/**
 * Calculate bounding box from coordinates
 */
export function calculateBounds(coordinates: WorldCoordinate[]): BBox {
  if (coordinates.length === 0) {
    return { minX: -100, maxX: 100, minY: -100, maxY: 100 };
  }

  const minX = Math.min(...coordinates.map(c => c.x));
  const maxX = Math.max(...coordinates.map(c => c.x));
  const minY = Math.min(...coordinates.map(c => c.y));
  const maxY = Math.max(...coordinates.map(c => c.y));

  return { minX, maxX, minY, maxY };
}

/**
 * Calculate viewBox with padding for SVG display
 */
export function calculateViewBox(bbox: BBox, paddingPercent: number = 0.2, minPadding: number = 50) {
  const width = bbox.maxX - bbox.minX;
  const height = bbox.maxY - bbox.minY;
  
  const paddingAmount = Math.max(
    Math.max(width, height) * paddingPercent,
    minPadding
  );
  
  return {
    x: bbox.minX - paddingAmount,
    y: bbox.minY - paddingAmount,
    width: width + 2 * paddingAmount,
    height: height + 2 * paddingAmount
  };
}

/**
 * Normalize coordinate input to consistent format
 */
export function normalizeCoordinates(coords: any[]): WorldCoordinate[] {
  return coords.map(coord => {
    if (Array.isArray(coord)) {
      return { x: coord[0], y: coord[1] };
    } else if (coord && typeof coord === 'object' && 'x' in coord && 'y' in coord) {
      return { x: coord.x, y: coord.y };
    } else {
      console.error('Invalid coordinate format:', coord);
      return { x: 0, y: 0 };
    }
  });
} 