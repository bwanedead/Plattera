/**
 * Grid Background Component
 * Renders SVG grid background (extracted from original PolygonViewer)
 */
import React, { useMemo } from 'react';
import { PolygonResult } from '../../../services/polygonApi';

interface GridBackgroundProps {
  polygon?: PolygonResult;
  showGrid: boolean;
  showLabels: boolean;
}

// Helper function to normalize coordinates
const normalizeCoordinates = (coords: any[]): {x: number, y: number}[] => {
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
};

export const GridBackground: React.FC<GridBackgroundProps> = ({
  polygon,
  showGrid,
  showLabels
}) => {
  // Normalize coordinates
  const normalizedCoordinates = useMemo(() => {
    if (!polygon?.coordinates || polygon.coordinates.length === 0) {
      return [];
    }
    return normalizeCoordinates(polygon.coordinates);
  }, [polygon?.coordinates]);

  // Calculate polygon bounds and scaling (from original PolygonViewer)
  const polygonData = useMemo(() => {
    if (!normalizedCoordinates || normalizedCoordinates.length === 0) {
      // Default view for when there's no polygon
      return {
        bounds: { minX: -100, maxX: 100, minY: -100, maxY: 100, width: 200, height: 200 },
        viewBox: { x: -150, y: -150, width: 300, height: 300 },
        padding: 50
      };
    }

    const coords = normalizedCoordinates;
    
    const minX = Math.min(...coords.map(c => c.x));
    const maxX = Math.max(...coords.map(c => c.x));
    const minY = Math.min(...coords.map(c => c.y));
    const maxY = Math.max(...coords.map(c => c.y));
    
    const width = maxX - minX;
    const height = maxY - minY;
    
    const paddingPercent = Math.max(width, height) * 0.2;
    const paddingMin = 50;
    const padding = Math.max(paddingPercent, paddingMin);
    
    const viewMinX = minX - padding;
    const viewMaxX = maxX + padding;
    const viewMinY = minY - padding;
    const viewMaxY = maxY + padding;
    
    const viewWidth = viewMaxX - viewMinX;
    const viewHeight = viewMaxY - viewMinY;
    
    return {
      bounds: { minX, maxX, minY, maxY, width, height },
      viewBox: { x: viewMinX, y: viewMinY, width: viewWidth, height: viewHeight },
      padding
    };
  }, [normalizedCoordinates]);

  // Generate grid lines (from original PolygonViewer)
  const gridLines = useMemo(() => {
    if (!polygonData) return { major: [], minor: [], labels: [] };
    
    const { viewBox } = polygonData;
    const maxDimension = Math.max(viewBox.width, viewBox.height);
    const gridSpacing = Math.pow(10, Math.floor(Math.log10(maxDimension / 8)));
    
    const lines: { x1: number; y1: number; x2: number; y2: number; type: 'major' | 'minor' }[] = [];
    const labels: { x: number; y: number; text: string; type: 'x' | 'y' }[] = [];
    
    // Vertical lines
    const startX = Math.floor(viewBox.x / gridSpacing) * gridSpacing;
    for (let x = startX; x <= viewBox.x + viewBox.width; x += gridSpacing) {
      const isMajor = Math.abs(x % (gridSpacing * 5)) < 0.001;
      lines.push({
        x1: x,
        y1: viewBox.y,
        x2: x,
        y2: viewBox.y + viewBox.height,
        type: isMajor ? 'major' : 'minor'
      });
      
      if (isMajor && showLabels) {
        labels.push({
          x: x,
          y: viewBox.y + viewBox.height - 20,
          text: `${x.toFixed(0)}`,
          type: 'x'
        });
      }
    }
    
    // Horizontal lines
    const startY = Math.floor(viewBox.y / gridSpacing) * gridSpacing;
    for (let y = startY; y <= viewBox.y + viewBox.height; y += gridSpacing) {
      const isMajor = Math.abs(y % (gridSpacing * 5)) < 0.001;
      lines.push({
        x1: viewBox.x,
        y1: y,
        x2: viewBox.x + viewBox.width,
        y2: y,
        type: isMajor ? 'major' : 'minor'
      });
      
      if (isMajor && showLabels) {
        labels.push({
          x: viewBox.x + 20,
          y: y,
          text: `${y.toFixed(0)}`,
          type: 'y'
        });
      }
    }
    
    return {
      major: lines.filter(l => l.type === 'major'),
      minor: lines.filter(l => l.type === 'minor'),
      labels
    };
  }, [polygonData, showLabels]);

  return (
    <div className="grid-background">
      <svg
        className="grid-svg"
        viewBox={`${polygonData.viewBox.x} ${polygonData.viewBox.y} ${polygonData.viewBox.width} ${polygonData.viewBox.height}`}
        preserveAspectRatio="xMidYMid meet"
        style={{ width: '100%', height: '100%' }}
      >
        {/* Grid - Minor Lines */}
        {showGrid && (
          <g className="grid-minor">
            {gridLines.minor.map((line, i) => (
              <line
                key={`minor-${i}`}
                x1={line.x1}
                y1={line.y1}
                x2={line.x2}
                y2={line.y2}
                stroke="#404040"
                strokeWidth="0.5"
              />
            ))}
          </g>
        )}

        {/* Grid - Major Lines */}
        {showGrid && (
          <g className="grid-major">
            {gridLines.major.map((line, i) => (
              <line
                key={`major-${i}`}
                x1={line.x1}
                y1={line.y1}
                x2={line.x2}
                y2={line.y2}
                stroke="#606060"
                strokeWidth="1"
              />
            ))}
          </g>
        )}

        {/* Grid Labels */}
        {showLabels && (
          <g className="grid-labels">
            {gridLines.labels.map((label, i) => (
              <text
                key={`label-${i}`}
                x={label.x}
                y={label.y}
                fill="#888888"
                fontSize="14"
                textAnchor={label.type === 'x' ? 'middle' : 'start'}
                dominantBaseline={label.type === 'x' ? 'auto' : 'middle'}
              >
                {label.text}
              </text>
            ))}
          </g>
        )}
      </svg>
    </div>
  );
};

// Export the polygon data calculation for use by PolygonLayer
export { normalizeCoordinates }; 