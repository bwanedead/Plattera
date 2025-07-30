/**
 * Professional Polygon Viewer Modal
 * Displays polygon with grid, measurements, and professional styling
 */
import React, { useEffect, useRef, useMemo } from 'react';
import { PolygonResult } from '../../services/polygonApi';

interface PolygonViewerProps {
  polygon: PolygonResult;
  isOpen: boolean;
  onClose: () => void;
}

// Helper function to normalize coordinates
const normalizeCoordinates = (coords: any[]): {x: number, y: number}[] => {
  return coords.map(coord => {
    // Handle both array format [x, y] and object format {x, y}
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

export const PolygonViewer: React.FC<PolygonViewerProps> = ({
  polygon,
  isOpen,
  onClose
}) => {
  const svgRef = useRef<SVGSVGElement>(null);

  // Normalize coordinates first
  const normalizedCoordinates = useMemo(() => {
    if (!polygon.coordinates || polygon.coordinates.length === 0) {
      return [];
    }
    return normalizeCoordinates(polygon.coordinates);
  }, [polygon.coordinates]);

  // Debug coordinates
  useEffect(() => {
    if (polygon.coordinates && polygon.coordinates.length > 0) {
      console.log('🔍 Raw Polygon Coordinates:', polygon.coordinates);
      console.log('🔍 Normalized Coordinates:', normalizedCoordinates);
    }
  }, [polygon.coordinates, normalizedCoordinates]);

  // Calculate polygon bounds and scaling
  const polygonData = useMemo(() => {
    if (!normalizedCoordinates || normalizedCoordinates.length === 0) {
      console.warn('⚠️ No normalized coordinates available for polygon');
      return null;
    }

    const coords = normalizedCoordinates;
    
    // Find bounds
    const minX = Math.min(...coords.map(c => c.x));
    const maxX = Math.max(...coords.map(c => c.x));
    const minY = Math.min(...coords.map(c => c.y));
    const maxY = Math.max(...coords.map(c => c.y));
    
    console.log('📐 Polygon Bounds:', { minX, maxX, minY, maxY });
    
    const width = maxX - minX;
    const height = maxY - minY;
    
    // Add padding (20% of dimensions, but minimum 50 units)
    const paddingPercent = Math.max(width, height) * 0.2;
    const paddingMin = 50;
    const padding = Math.max(paddingPercent, paddingMin);
    
    const viewMinX = minX - padding;
    const viewMaxX = maxX + padding;
    const viewMinY = minY - padding;
    const viewMaxY = maxY + padding;
    
    const viewWidth = viewMaxX - viewMinX;
    const viewHeight = viewMaxY - viewMinY;
    
    const result = {
      bounds: { minX, maxX, minY, maxY, width, height },
      viewBox: { x: viewMinX, y: viewMinY, width: viewWidth, height: viewHeight },
      padding
    };
    
    console.log('🖼️ ViewBox:', result.viewBox);
    return result;
  }, [normalizedCoordinates]);

  // Generate grid lines
  const gridLines = useMemo(() => {
    if (!polygonData) return { major: [], minor: [], labels: [] };
    
    const { viewBox } = polygonData;
    const maxDimension = Math.max(viewBox.width, viewBox.height);
    const gridSpacing = Math.pow(10, Math.floor(Math.log10(maxDimension / 8)));
    
    console.log('📏 Grid spacing:', gridSpacing);
    
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
      
      if (isMajor) {
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
      
      if (isMajor) {
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
  }, [polygonData]);

  // Generate polygon path
  const polygonPath = useMemo(() => {
    if (!normalizedCoordinates || normalizedCoordinates.length === 0) return '';
    
    const coords = normalizedCoordinates;
    let path = `M ${coords[0].x} ${coords[0].y}`;
    
    for (let i = 1; i < coords.length; i++) {
      path += ` L ${coords[i].x} ${coords[i].y}`;
    }
    
    path += ' Z'; // Close the path
    console.log('🎨 SVG Path:', path);
    return path;
  }, [normalizedCoordinates]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen, onClose]);

  if (!isOpen || !polygonData) {
    return null;
  }

  return (
    <div className="polygon-viewer-overlay" onClick={onClose}>
      <div className="polygon-viewer-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="polygon-viewer-header">
          <div className="polygon-title">
            <h3>Polygon Visualization - Description {polygon.description_id}</h3>
            <div className="polygon-subtitle">
              {polygon.coordinate_system} coordinate system
            </div>
          </div>
          <button className="close-button" onClick={onClose}>
            ✕
          </button>
        </div>

        {/* Main Viewer */}
        <div className="polygon-viewer-content">
          <div className="polygon-canvas-container">
            <svg
              ref={svgRef}
              className="polygon-canvas"
              viewBox={`${polygonData.viewBox.x} ${polygonData.viewBox.y} ${polygonData.viewBox.width} ${polygonData.viewBox.height}`}
              preserveAspectRatio="xMidYMid meet"
            >
              {/* Grid - Minor Lines */}
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

              {/* Grid - Major Lines */}
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

              {/* Grid Labels */}
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
              {polygon.origin && (polygon.origin.x !== undefined || polygon.origin.y !== undefined) && (
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

          {/* Information Panel */}
          <div className="polygon-info-panel">
            <div className="info-section">
              <h4>Polygon Properties</h4>
              <div className="info-grid">
                <div className="info-item">
                  <span className="info-label">Area (Calculated):</span>
                  <span className="info-value">
                    {polygon.properties.area_calculated.toLocaleString()} sq ft
                    <span className="info-secondary">
                      ({(polygon.properties.area_calculated / 43560).toFixed(3)} acres)
                    </span>
                  </span>
                </div>
                
                {polygon.properties.area_stated && (
                  <div className="info-item">
                    <span className="info-label">Area (Stated):</span>
                    <span className="info-value">
                      {polygon.properties.area_stated} acres
                    </span>
                  </div>
                )}
                
                <div className="info-item">
                  <span className="info-label">Perimeter:</span>
                  <span className="info-value">
                    {polygon.properties.perimeter.toLocaleString()} ft
                  </span>
                </div>
                
                <div className="info-item">
                  <span className="info-label">Closure Error:</span>
                  <span className={`info-value ${polygon.properties.closure_error > 1 ? 'error' : 'success'}`}>
                    {polygon.properties.closure_error.toFixed(2)} ft
                  </span>
                </div>
                
                <div className="info-item">
                  <span className="info-label">Boundary Courses:</span>
                  <span className="info-value">
                    {polygon.properties.courses_count}
                  </span>
                </div>
              </div>
            </div>

            <div className="info-section">
              <h4>Coordinate System</h4>
              <div className="coordinate-info">
                <span className="coordinate-type">{polygon.coordinate_system}</span>
                {polygon.origin && (
                  <div className="origin-details">
                    <span className="origin-label">Origin Type:</span>
                    <span className="origin-type">{polygon.origin.type}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="polygon-viewer-footer">
          <div className="viewer-controls">
            <button className="secondary-button" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};