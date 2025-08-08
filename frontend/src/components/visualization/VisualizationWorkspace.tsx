/**
 * Visualization Workspace - Container with swappable backgrounds + polygon overlay
 */
import React, { useState, useEffect } from 'react';
import { PolygonResult } from '../../services/polygonApi';
import { GridBackground } from './backgrounds/GridBackground';
import { MapBackground } from './backgrounds/MapBackground';
import { PolygonLayer } from './layers/PolygonLayer';
import { mappingApi } from '../../services/mapping';

type ViewMode = 'grid' | 'map' | 'hybrid';

interface LayerSettings {
  showPolygon: boolean;
  showGrid: boolean;
  showLabels: boolean;
  showOrigin: boolean;
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
    showOrigin: true
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

  // When in map/hybrid mode and we have polygon + schema, request georeferencing
  useEffect(() => {
    const runGeoref = async () => {
      try {
        if (!polygon || !schemaData) {
          setGeoPolygonData(null);
          return;
        }
        if (!(viewMode === 'map' || viewMode === 'hybrid')) {
          setGeoPolygonData(null);
          return;
        }

        // Extract PLSS from the first complete description; fallback to first
        const descriptions = Array.isArray(schemaData?.descriptions) ? schemaData.descriptions : [];
        const chosen = descriptions.find((d: any) => d?.is_complete && d?.plss) || descriptions[0];
        const plss = chosen?.plss;
        if (!plss) {
          setGeoPolygonData(null);
          return;
        }

        // Debug: log outgoing PLSS request
        console.log('📤 PLSS request', {
          state: plss.state,
          county: plss.county,
          principal_meridian: plss.principal_meridian,
          township_number: plss.township_number,
          township_direction: plss.township_direction,
          range_number: plss.range_number,
          range_direction: plss.range_direction,
          section_number: plss.section_number,
          quarter_sections: plss.quarter_sections,
          starting_point: chosen?.plss?.starting_point?.tie_to_corner || null,
        });

        const req = mappingApi.convertPolygonForMapping(polygon, {
          state: plss.state,
          county: plss.county,
          principal_meridian: plss.principal_meridian,
          township_number: plss.township_number,
          township_direction: plss.township_direction,
          range_number: plss.range_number,
          range_direction: plss.range_direction,
          section_number: plss.section_number,
          quarter_sections: plss.quarter_sections,
        });
        if (!req) {
          setGeoPolygonData(null);
          return;
        }

        // Include starting_point if present on schema (tie_to_corner)
        if (chosen?.plss?.starting_point?.tie_to_corner) {
          req.starting_point = { tie_to_corner: chosen.plss.starting_point.tie_to_corner };
        }

        const projected = await mappingApi.projectPolygonToMap(req);
        if (projected.success && projected.geographic_polygon) {
          // Debug: log returned polygon bounds and anchor info
          if (projected.geographic_polygon.bounds) {
            const b = projected.geographic_polygon.bounds;
            console.log(
              `📥 Projected polygon bounds: (${b.min_lat.toFixed(5)}, ${b.min_lon.toFixed(5)}) .. (${b.max_lat.toFixed(5)}, ${b.max_lon.toFixed(5)})`,
              { anchor: projected.anchor_info }
            );
          }
          setGeoPolygonData({
            geographic_polygon: projected.geographic_polygon,
            anchor_info: projected.anchor_info,
          });
        } else {
          setGeoPolygonData(null);
        }
      } catch (e) {
        console.error('❌ Georeference failed:', e);
        setGeoPolygonData(null);
      }
    };

    runGeoref();
  }, [viewMode, polygon, schemaData]);

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
                  <MapBackground 
                    schemaData={schemaData}
                    polygonData={geoPolygonData}
                  />
                )}
                
                {viewMode === 'hybrid' && (
                  <MapBackground 
                    schemaData={schemaData}
                    polygonData={geoPolygonData}
                    showGrid={layers.showGrid}
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