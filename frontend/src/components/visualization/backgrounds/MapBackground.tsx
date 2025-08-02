/**
 * Map Background Component
 * Renders map tiles using our mapping APIs (placeholder for now)
 */
import React from 'react';
import { PolygonResult } from '../../../services/polygonApi';

interface MapBackgroundProps {
  polygon?: PolygonResult;
  showGrid?: boolean;
}

export const MapBackground: React.FC<MapBackgroundProps> = ({
  polygon,
  showGrid
}) => {
  return (
    <div className="map-background">
      <div style={{ 
        width: '100%', 
        height: '100%', 
        backgroundColor: '#f0f0f0',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#666',
        fontSize: '18px'
      }}>
        🗺️ Map View - Coming Soon
        <br />
        <small style={{ fontSize: '14px' }}>
          Will integrate with /api/mapping/tile endpoints
        </small>
      </div>
    </div>
  );
};