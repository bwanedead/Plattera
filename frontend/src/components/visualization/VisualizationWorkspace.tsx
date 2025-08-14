/**
 * Visualization Workspace - Container with swappable backgrounds + polygon overlay
 */
import React, { useState, useEffect } from 'react';
import { PolygonResult } from '../../services/polygonApi';
import { GridBackground } from './backgrounds/GridBackground';
import { CleanMapBackground } from './backgrounds/CleanMapBackground';
import { PolygonLayer } from './layers/PolygonLayer';
import { cleanMappingApi } from '../../services/cleanMappingApi';
// Global CSS imports must live in pages/_app.tsx per Next.js rules

type ViewMode = 'grid' | 'map' | 'hybrid';

interface LayerSettings {
  showPolygon: boolean;
  showGrid: boolean;
  showLabels: boolean;
  showOrigin: boolean;
  showSectionOverlay: boolean;
  showTownshipOverlay: boolean;
  showQuarterSplits: boolean;
  showValidationBanner: boolean;
}

interface VisualizationWorkspaceProps {
  polygon?: PolygonResult;
  schemaData?: any; // Add schema data
  isOpen: boolean;
  onClose: () => void;
}

export const VisualizationWorkspace: React.FC<VisualizationWorkspaceProps> = ({
  polygon,
  schemaData, // Add schema data parameter
  isOpen,
  onClose
}) => {
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [layers, setLayers] = useState<LayerSettings>({
    showPolygon: true,
    showGrid: true,
    showLabels: true,
    showOrigin: true,
    showSectionOverlay: true,
    showTownshipOverlay: true,
    showQuarterSplits: true,
    showValidationBanner: true,
  });

  // Georeferenced polygon for map overlay
  const [geoPolygonData, setGeoPolygonData] = useState<any | null>(null);

  const toggleLayer = (layer: keyof LayerSettings) => {
    setLayers(prev => ({ ...prev, [layer]: !prev[layer] }));
  };

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen, onClose]);

  // Clear geo data when switching away from map modes
  useEffect(() => {
    if (viewMode === 'grid') {
      setGeoPolygonData(null);
    }
  }, [viewMode]);

  if (!isOpen) return null;

  return (
    <div className="visualization-workspace-overlay" onClick={onClose}>
      <div className="visualization-workspace-modal" onClick={(e) => e.stopPropagation()}>
        
        {/* Header with view mode tabs */}
        <div className="workspace-header">
          <div className="workspace-title">
            <h3>Property Visualization</h3>
            {polygon && (
              <div className="workspace-subtitle">
                Description {polygon.description_id} • {(polygon.properties.area_calculated / 43560).toFixed(2)} acres
              </div>
            )}
          </div>
          
          <div className="view-mode-tabs">
            <button 
              className={`tab-button ${viewMode === 'grid' ? 'active' : ''}`}
              onClick={() => setViewMode('grid')}
            >
              📊 Grid
            </button>
            <button 
              className={`tab-button ${viewMode === 'map' ? 'active' : ''}`}
              onClick={() => setViewMode('map')}
            >
              🗺️ Map
            </button>
            <button 
              className={`tab-button ${viewMode === 'hybrid' ? 'active' : ''}`}
              onClick={() => setViewMode('hybrid')}
            >
              🔄 Hybrid
            </button>
          </div>
          
          <button className="close-button" onClick={onClose}>✕</button>
        </div>

        {/* Main content area */}
        <div className="workspace-content">
          
          {/* Main Viewport */}
          <div className="viewport-container">
            <div className="viewport-stack">
              
              {/* Background Layer */}
              <div className="background-layer">
                {viewMode === 'grid' && (
                  <GridBackground 
                    polygon={polygon}
                    showGrid={layers.showGrid}
                    showLabels={layers.showLabels}
                  />
                )}
                
                {viewMode === 'map' && (
                  <CleanMapBackground 
                    schemaData={schemaData}
                    polygonData={polygon}
                    onPolygonUpdate={setGeoPolygonData}
                  />
                )}
                
                {viewMode === 'hybrid' && (
                  <CleanMapBackground 
                    schemaData={schemaData}
                    polygonData={polygon}
                    onPolygonUpdate={setGeoPolygonData}
                  />
                )}
              </div>

              {/* Polygon Layer */}
              {polygon && layers.showPolygon && viewMode === 'grid' && (
                <div className="polygon-layer">
                  <PolygonLayer 
                    polygon={polygon}
                    showOrigin={layers.showOrigin}
                    viewMode={viewMode}
                  />
                </div>
              )}
            </div>
          </div>

          {/* Controls Panel */}
          <div className="controls-panel">
            
            {/* Layer Controls */}
            <div className="control-section">
              <h4>Layers</h4>
              <div className="layer-toggles">
                <label className="toggle-control">
                  <input 
                    type="checkbox" 
                    checked={layers.showPolygon}
                    onChange={() => toggleLayer('showPolygon')}
                  />
                  Polygon
                </label>
                <label className="toggle-control">
                  <input 
                    type="checkbox" 
                    checked={layers.showGrid}
                    onChange={() => toggleLayer('showGrid')}
                  />
                  Grid
                </label>
                <label className="toggle-control">
                  <input 
                    type="checkbox" 
                    checked={layers.showLabels}
                    onChange={() => toggleLayer('showLabels')}
                  />
                  Labels
                </label>
                <label className="toggle-control">
                  <input 
                    type="checkbox" 
                    checked={layers.showOrigin}
                    onChange={() => toggleLayer('showOrigin')}
                  />
                  Origin
                </label>
                {(viewMode === 'map' || viewMode === 'hybrid') && (
                  <>
                    <label className="toggle-control">
                      <input 
                        type="checkbox" 
                        checked={layers.showSectionOverlay}
                        onChange={() => toggleLayer('showSectionOverlay')}
                      />
                      Section Overlay
                    </label>
                    <label className="toggle-control">
                      <input 
                        type="checkbox" 
                        checked={layers.showTownshipOverlay}
                        onChange={() => toggleLayer('showTownshipOverlay')}
                      />
                      Township Overlay
                    </label>
                    <label className="toggle-control">
                      <input 
                        type="checkbox" 
                        checked={layers.showQuarterSplits}
                        onChange={() => toggleLayer('showQuarterSplits')}
                      />
                      Quarter Splits
                    </label>
                    <label className="toggle-control">
                      <input 
                        type="checkbox" 
                        checked={layers.showValidationBanner}
                        onChange={() => toggleLayer('showValidationBanner')}
                      />
                      Validation Banner
                    </label>
                  </>
                )}
              </div>
            </div>

            {/* Background Selector for Map/Hybrid modes */}
            {(viewMode === 'map' || viewMode === 'hybrid') && (
              <div className="control-section">
                <h4>Background</h4>
                <div className="background-selector">
                  <label className="radio-control">
                    <input type="radio" name="background" value="usgs_topo" defaultChecked />
                    USGS Topo
                  </label>
                  <label className="radio-control">
                    <input type="radio" name="background" value="osm" />
                    OpenStreetMap
                  </label>
                </div>
              </div>
            )}

            {/* Polygon Properties */}
            {polygon && (
              <div className="control-section">
                <h4>Properties</h4>
                <div className="property-list">
                  <div className="property-item">
                    <span>Area (Calculated):</span>
                    <span>
                      {polygon.properties.area_calculated.toLocaleString()} sq ft
                      <span className="property-secondary">
                        ({(polygon.properties.area_calculated / 43560).toFixed(3)} acres)
                      </span>
                    </span>
                  </div>
                  
                  <div className="property-item">
                    <span>Perimeter:</span>
                    <span>{polygon.properties.perimeter.toLocaleString()} ft</span>
                  </div>
                  
                  <div className="property-item">
                    <span>Closure Error:</span>
                    <span className={polygon.properties.closure_error > 1 ? 'error' : 'success'}>
                      {polygon.properties.closure_error.toFixed(2)} ft
                    </span>
                  </div>
                  
                  <div className="property-item">
                    <span>Boundary Courses:</span>
                    <span>{polygon.properties.courses_count}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Coordinate System */}
            {polygon && (
              <div className="control-section">
                <h4>Coordinate System</h4>
                <div className="coordinate-type">{polygon.coordinate_system}</div>
                {polygon.origin && (
                  <div className="origin-details">
                    <span className="origin-label">Origin Type:</span>
                    <span className="origin-type">{polygon.origin.type}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}; 