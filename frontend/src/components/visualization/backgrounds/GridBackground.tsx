/**
 * Grid Background Component
 * Renders grid for display-ready coordinates (already north-up oriented)
 */
import React, { useMemo } from 'react';
import { PolygonResult } from '../../../services/polygonApi';
import { 
  normalizeCoordinates, 
  calculateBounds, 
  calculateViewBox 
} from '../../../utils/coordinateUtils';

interface GridBackgroundProps {
  polygon?: PolygonResult;
  showGrid: boolean;
  showLabels: boolean;
}

export const GridBackground: React.FC<GridBackgroundProps> = ({
  polygon,
  showGrid,
  showLabels
}) => {
  // Normalize coordinates (already display-ready from backend)
  const displayCoordinates = useMemo(() => {
    if (!polygon?.coordinates || polygon.coordinates.length === 0) {
      return [];
    }
    return normalizeCoordinates(polygon.coordinates);
  }, [polygon?.coordinates]);

  // Calculate bounds and viewBox
  const polygonData = useMemo(() => {
    const bounds = displayCoordinates.length > 0 
      ? calculateBounds(displayCoordinates)
      : { minX: -100, maxX: 100, minY: -100, maxY: 100 };
    
    const viewBox = calculateViewBox(bounds);
    
    console.log('🎨 GridBackground display coordinates:', displayCoordinates);
    console.log('🎨 GridBackground bounds:', bounds);
    console.log('🎨 GridBackground viewBox:', viewBox);
    
    return { bounds, viewBox };
  }, [displayCoordinates]);

  // Generate grid lines (no transforms needed)
  const gridLines = useMemo(() => {
    if (!polygonData) return { major: [], minor: [], labels: [] };
    
    const { viewBox } = polygonData;
    const maxDimension = Math.max(viewBox.width, viewBox.height);
    const gridSpacing = Math.pow(10, Math.floor(Math.log10(maxDimension / 8)));
    
    const lines: { x1: number; y1: number; x2: number; y2: number; type: 'major' | 'minor' }[] = [];
    const labels: { x: number; y: number; text: string; type: 'x' | 'y' }[] = [];
    
    // Vertical lines (East-West)
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
          y: viewBox.y + 20,
          text: `${x.toFixed(0)}E`,
          type: 'x'
        });
      }
    }
    
    // Horizontal lines (North-South) 
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
          text: `${y.toFixed(0)}N`,
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
        style={{ 
          width: '100%', 
          height: '100%'
        }}
      >
        {/* No transforms needed - coordinates are already display-ready */}
        {showGrid && (
          <g className="grid-lines">
            {/* Minor grid lines */}
            {gridLines.minor.map((line, i) => (
              <line
                key={`minor-${i}`}
                x1={line.x1}
                y1={line.y1}
                x2={line.x2}
                y2={line.y2}
                stroke="#4a5568"
                strokeWidth="0.5"
                opacity="0.6"
              />
            ))}
            
            {/* Major grid lines */}
            {gridLines.major.map((line, i) => (
              <line
                key={`major-${i}`}
                x1={line.x1}
                y1={line.y1}
                x2={line.x2}
                y2={line.y2}
                stroke="#718096"
                strokeWidth="1"
                opacity="0.8"
              />
            ))}
          </g>
        )}
        
        {/* Simple labels (no coordinate system adjustments needed) */}
        {showLabels && (
          <g className="grid-labels">
            {gridLines.labels.map((label, i) => (
              <text
                key={`label-${i}`}
                x={label.x}
                y={label.y}
                fill="#a0aec0"
                fontSize="12"
                textAnchor={label.type === 'x' ? 'middle' : 'start'}
                dominantBaseline={label.type === 'x' ? 'hanging' : 'middle'}
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