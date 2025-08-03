/**
 * Polygon Layer Component  
 * Renders polygon coordinates that are already oriented for north-up display
 */
import React, { useMemo } from 'react';
import { PolygonResult } from '../../../services/polygonApi';
import { 
  normalizeCoordinates, 
  calculateBounds, 
  calculateViewBox
} from '../../../utils/coordinateUtils';

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
  // Normalize coordinates (already display-ready from backend)
  const displayCoordinates = useMemo(() => {
    if (!polygon?.coordinates || polygon.coordinates.length === 0) {
      return [];
    }
    return normalizeCoordinates(polygon.coordinates);
  }, [polygon?.coordinates]);

  // Calculate bounds and viewBox for display coordinates
  const polygonData = useMemo(() => {
    if (displayCoordinates.length === 0) {
      return null;
    }

    const bounds = calculateBounds(displayCoordinates);
    const viewBox = calculateViewBox(bounds);
    
    console.log('🎨 PolygonLayer display coordinates:', displayCoordinates);
    console.log('🎨 PolygonLayer bounds:', bounds);
    console.log('🎨 PolygonLayer viewBox:', viewBox);
    
    return { bounds, viewBox };
  }, [displayCoordinates]);

  // Generate polygon path (no transforms needed)
  const polygonPath = useMemo(() => {
    if (displayCoordinates.length === 0) {
      return '';
    }
    
    let path = `M ${displayCoordinates[0].x} ${displayCoordinates[0].y}`;
    
    for (let i = 1; i < displayCoordinates.length; i++) {
      path += ` L ${displayCoordinates[i].x} ${displayCoordinates[i].y}`;
    }
    
    path += ' Z';
    console.log('🎨 PolygonLayer display-ready path:', path);
    return path;
  }, [displayCoordinates]);

  if (!polygonData) {
    return null;
  }

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
          pointerEvents: 'none'
        }}
      >
        {/* No transforms needed - coordinates are already display-ready */}
        <g className="polygon-group">
          <path
            d={polygonPath}
            fill="rgba(59, 130, 246, 0.3)"
            stroke="#3b82f6"
            strokeWidth="2"
            strokeLinejoin="round"
          />
          
          {/* Polygon vertices */}
          {displayCoordinates.map((coord, i) => (
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
