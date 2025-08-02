/**
 * Polygon Layer Component  
 * Renders polygon as overlay that can be placed over any background
 */
import React, { useMemo } from 'react';
import { PolygonResult } from '../../../services/polygonApi';
import { normalizeCoordinates } from '../backgrounds/GridBackground';

interface PolygonLayerProps {
  polygon: PolygonResult;
  showOrigin: boolean;
  viewMode: 'grid' | 'map' | 'hybrid';
}

export const PolygonLayer: React.FC<PolygonLayerProps> = ({
  polygon,
  showOrigin,
  viewMode
}) => {
  // Normalize coordinates
  const normalizedCoordinates = useMemo(() => {
    if (!polygon?.coordinates || polygon.coordinates.length === 0) {
      return [];
    }
    return normalizeCoordinates(polygon.coordinates);
  }, [polygon?.coordinates]);

  // Calculate polygon bounds for viewBox (same logic as GridBackground)
  const polygonData = useMemo(() => {
    if (!normalizedCoordinates || normalizedCoordinates.length === 0) {
      return null;
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

  // Generate polygon path
  const polygonPath = useMemo(() => {
    if (!normalizedCoordinates || normalizedCoordinates.length === 0) return '';
    
    const coords = normalizedCoordinates;
    let path = `M ${coords[0].x} ${coords[0].y}`;
    
    for (let i = 1; i < coords.length; i++) {
      path += ` L ${coords[i].x} ${coords[i].y}`;
    }
    
    path += ' Z'; // Close the path
    return path;
  }, [normalizedCoordinates]);

  if (!polygonData) return null;

  return (
    <div className="polygon-layer">
      <svg
        className="polygon-svg"
        viewBox={`${polygonData.viewBox.x} ${polygonData.viewBox.y} ${polygonData.viewBox.width} ${polygonData.viewBox.height}`}
        preserveAspectRatio="xMidYMid meet"
        style={{ 
          width: '100%', 
          height: '100%',
          position: 'absolute',
          top: 0,
          left: 0,
          pointerEvents: 'none' // Allow interaction with background
        }}
      >
        {/* Polygon */}
        <g className="polygon-group">
          <path
            d={polygonPath}
            fill="rgba(59, 130, 246, 0.3)"
            stroke="#3b82f6"
            strokeWidth="2"
            strokeLinejoin="round"
          />
          
          {/* Polygon vertices */}
          {normalizedCoordinates.map((coord, i) => (
            <circle
              key={`vertex-${i}`}
              cx={coord.x}
              cy={coord.y}
              r="3"
              fill="#1d4ed8"
              stroke="white"
              strokeWidth="1"
            />
          ))}
        </g>

        {/* Origin point */}
        {showOrigin && polygon.origin && (polygon.origin.x !== undefined || polygon.origin.y !== undefined) && (
          <g className="origin-point">
            <circle
              cx={polygon.origin.x || 0}
              cy={polygon.origin.y || 0}
              r="5"
              fill="#dc2626"
              stroke="white"
              strokeWidth="2"
            />
            <text
              x={(polygon.origin.x || 0) + 15}
              y={(polygon.origin.y || 0) - 10}
              fill="#dc2626"
              fontSize="14"
              fontWeight="bold"
            >
              Origin
            </text>
          </g>
        )}
      </svg>
    </div>
  );
};