/**
 * Polygon Overlay Component
 * Renders polygon overlays on the geographic map
 */
import React, { useMemo } from 'react';

interface PolygonOverlayProps {
  polygonData: any;
  geoToScreen: (lat: number, lon: number) => { x: number; y: number } | null;
  mapBounds: {
    min_lat: number;
    max_lat: number;
    min_lon: number;
    max_lon: number;
  };
}

export const PolygonOverlay: React.FC<PolygonOverlayProps> = ({
  polygonData,
  geoToScreen,
  mapBounds
}) => {
  // Convert geographic polygon coordinates to screen coordinates
  const screenPolygons = useMemo(() => {
    if (!polygonData || !polygonData.geographic_polygon) return [];

    const geoCoords = polygonData.geographic_polygon.coordinates[0]; // GeoJSON format
    const screenCoords = [];

    for (const coord of geoCoords) {
      const [lon, lat] = coord; // GeoJSON is [lon, lat]
      const screenPos = geoToScreen(lat, lon);
      
      if (screenPos) {
        // Check if point is within visible bounds (with some tolerance)
        const tolerance = 100; // pixels
        if (screenPos.x >= -tolerance && screenPos.x <= window.innerWidth + tolerance &&
            screenPos.y >= -tolerance && screenPos.y <= window.innerHeight + tolerance) {
          screenCoords.push(screenPos);
        }
      }
    }

    return screenCoords.length >= 3 ? [screenCoords] : [];
  }, [polygonData, geoToScreen, mapBounds]);

  // Generate SVG path for polygon
  const polygonPath = useMemo(() => {
    if (screenPolygons.length === 0) return '';

    return screenPolygons.map(coords => {
      if (coords.length < 3) return '';
      
      const pathCommands = coords.map((coord, index) => 
        `${index === 0 ? 'M' : 'L'} ${coord.x} ${coord.y}`
      ).join(' ');
      
      return pathCommands + ' Z'; // Close path
    }).join(' ');
  }, [screenPolygons]);

  // Calculate polygon center for label positioning
  const polygonCenter = useMemo(() => {
    if (screenPolygons.length === 0 || screenPolygons[0].length === 0) return null;

    const coords = screenPolygons[0];
    const centerX = coords.reduce((sum, coord) => sum + coord.x, 0) / coords.length;
    const centerY = coords.reduce((sum, coord) => sum + coord.y, 0) / coords.length;

    return { x: centerX, y: centerY };
  }, [screenPolygons]);

  if (screenPolygons.length === 0 || !polygonPath) {
    return null;
  }

  return (
    <svg
      className="polygon-overlay"
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 10
      }}
    >
      {/* Polygon Fill */}
      <path
        d={polygonPath}
        fill="rgba(59, 130, 246, 0.3)"
        stroke="#3b82f6"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* Polygon Vertices */}
      {screenPolygons[0].map((coord, index) => (
        <circle
          key={`vertex-${index}`}
          cx={coord.x}
          cy={coord.y}
          r="4"
          fill="#1d4ed8"
          stroke="white"
          strokeWidth="2"
        />
      ))}

      {/* Polygon Label */}
      {polygonCenter && polygonData.anchor_info && (
        <g className="polygon-label">
          {/* Label Background */}
          <rect
            x={polygonCenter.x - 60}
            y={polygonCenter.y - 25}
            width="120"
            height="20"
            fill="rgba(0, 0, 0, 0.8)"
            rx="4"
          />
          
          {/* Label Text */}
          <text
            x={polygonCenter.x}
            y={polygonCenter.y - 10}
            textAnchor="middle"
            fill="white"
            fontSize="12"
            fontFamily="monospace"
          >
            {polygonData.anchor_info.plss_reference}
          </text>
        </g>
      )}

      {/* Anchor Point Marker */}
      {polygonData.anchor_info && polygonData.anchor_info.resolved_coordinates && (() => {
        const anchorScreen = geoToScreen(
          polygonData.anchor_info.resolved_coordinates.lat,
          polygonData.anchor_info.resolved_coordinates.lon
        );
        
        return anchorScreen ? (
          <g className="anchor-marker">
            <circle
              cx={anchorScreen.x}
              cy={anchorScreen.y}
              r="6"
              fill="#ef4444"
              stroke="white"
              strokeWidth="2"
            />
            <text
              x={anchorScreen.x}
              y={anchorScreen.y - 12}
              textAnchor="middle"
              fill="#ef4444"
              fontSize="10"
              fontWeight="bold"
            >
              POB
            </text>
          </g>
        ) : null;
      })()}
    </svg>
  );
};