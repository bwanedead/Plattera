import React, { useCallback, useMemo, useState, useEffect, useRef } from 'react';
import { MapContext, type MapContextValue } from './core/MapContext';
import { MapEngine } from './core/MapEngine';
import { OverlayManager } from './overlays/OverlayManager';
import { PLSSManager } from './overlays/PLSSManager';
import { SidePanel, SidePanelSection } from './panels/SidePanel';
import { TilesSection } from './panels/TilesSection';
import { PropertiesSection } from './panels/PropertiesSection';
import type maplibregl from 'maplibre-gl';

interface MapWorkspaceProps {
	standalone?: boolean;
	initialParcels?: any[];
	schemaData?: any;
	initialView?: { center: { lat: number; lon: number }; zoom: number };
	className?: string;
}

export const MapWorkspace: React.FC<MapWorkspaceProps> = ({
	standalone = false,
	initialParcels = [],
	schemaData,
	initialView = { center: { lat: 41.5, lon: -107.5 }, zoom: 10 },
	className
}) => {
	const [map, setMap] = useState<maplibregl.Map | null>(null);
	const [isLoaded, setIsLoaded] = useState(false);
	const [center, setCenter] = useState(initialView.center);
	const [zoom, setZoom] = useState(initialView.zoom);
	const [bounds, setBounds] = useState<{ west: number; south: number; east: number; north: number } | null>(null);
	const [sidePanelCollapsed, setSidePanelCollapsed] = useState(false);

	const handleMapLoad = useCallback((m: maplibregl.Map) => {
		setMap(m);
		setIsLoaded(true);
	}, []);

	const handleMapMove = useCallback((view: { center: { lat: number; lon: number }; zoom: number; bounds: { west: number; south: number; east: number; north: number } }) => {
		setCenter(view.center);
		setZoom(view.zoom);
		setBounds(view.bounds);
	}, []);

	const ctx = useMemo<MapContextValue>(() => ({ map, isLoaded, center, zoom, bounds }), [map, isLoaded, center, zoom, bounds]);

  // Extract container bounds and center from schema for container-based overlays
  const { containerBounds, stateName, parcelCenter } = useMemo(() => {
    try {
      console.log('🔍 Schema data structure:', schemaData);
      console.log('🔍 PLSS data:', schemaData?.plss);
      console.log('🔍 Descriptions:', schemaData?.descriptions);
      
      if (!schemaData) {
        return { containerBounds: undefined, stateName: undefined, parcelCenter: initialView.center };
      }
      
			const plss = schemaData?.descriptions?.[0]?.plss;
			if (!plss) {
        console.log('🔍 No PLSS data found in schema for container overlays');
        return { containerBounds: undefined, stateName: undefined, parcelCenter: initialView.center };
      }
      
      // Debug: Log the schema structure more comprehensively to find coordinates
      console.log('🔍 Full schema structure:', {
        hasProjectedCoordinates: !!schemaData?.projected_coordinates,
        projectedCoordinatesLength: schemaData?.projected_coordinates?.length,
        projectedCoordinates: schemaData?.projected_coordinates,
        startingPoint: plss?.starting_point,
        hasLatLon: !!(plss?.starting_point?.latitude && plss?.starting_point?.longitude),
        // Check for coordinates in various nested locations
        topLevelProj: schemaData?.projected_coordinates,
        descriptionsProj: schemaData?.descriptions?.[0]?.projected_coordinates,
        descriptions: schemaData?.descriptions,
        // Add more detailed logging
        schemaKeys: Object.keys(schemaData || {}),
        descriptionsKeys: schemaData?.descriptions?.[0] ? Object.keys(schemaData.descriptions[0]) : [],
        plssKeys: plss ? Object.keys(plss) : []
      });
      
      // Initialize variables
      let containerBounds: any = undefined;
      let parcelCenter: any = initialView.center;
      
      // First, check if we have projected coordinates from the polygon drawing
      const projectedCoordinates = schemaData?.projected_coordinates;
      if (projectedCoordinates && projectedCoordinates.length > 0) {
        // Use the first projected coordinate as the center
        const firstCoord = projectedCoordinates[0];
        console.log('🔍 Checking first projected coord:', firstCoord);
        if (firstCoord && typeof firstCoord.latitude === 'number' && typeof firstCoord.longitude === 'number') {
          const lat = firstCoord.latitude;
          const lon = firstCoord.longitude;
          const buffer = 0.02; // ~1.4 mile buffer around the point
          
          containerBounds = {
            west: lon - buffer,
            south: lat - buffer,
            east: lon + buffer,
            north: lat + buffer
          };
          
          parcelCenter = { lat, lon };
          
          console.log('📍 Using projected coordinates from schema:', { lat, lon });
        }
        // Try alternate property names (lat/lon vs latitude/longitude)
        else if (firstCoord && typeof firstCoord.lat === 'number' && typeof firstCoord.lon === 'number') {
          const lat = firstCoord.lat;
          const lon = firstCoord.lon;
          const buffer = 0.02;
          
          containerBounds = {
            west: lon - buffer,
            south: lat - buffer,
            east: lon + buffer,
            north: lat + buffer
          };
          
          parcelCenter = { lat, lon };
          
          console.log('📍 Using projected coordinates (lat/lon) from schema:', { lat, lon });
        }
      }
      // Check if projected coordinates are in descriptions
      else if (schemaData?.descriptions?.[0]?.projected_coordinates) {
        const descProjectedCoords = schemaData.descriptions[0].projected_coordinates;
        if (descProjectedCoords && descProjectedCoords.length > 0) {
          const firstCoord = descProjectedCoords[0];
          if (firstCoord && typeof firstCoord.latitude === 'number' && typeof firstCoord.longitude === 'number') {
            const lat = firstCoord.latitude;
            const lon = firstCoord.longitude;
            const buffer = 0.02;
            
            containerBounds = {
              west: lon - buffer,
              south: lat - buffer,
              east: lon + buffer,
              north: lat + buffer
            };
            
            parcelCenter = { lat, lon };
            
            console.log('📍 Using projected coordinates from descriptions:', { lat, lon });
          }
        }
      }
			// Check if we have coordinates from the starting point
      else if (plss.starting_point?.latitude && plss.starting_point?.longitude) {
				// Use actual coordinates if available
        const lat = plss.starting_point.latitude;
        const lon = plss.starting_point.longitude;
				const buffer = 0.02; // ~1.4 mile buffer around the point
				
				containerBounds = {
					west: lon - buffer,
					south: lat - buffer,
					east: lon + buffer,
					north: lat + buffer
				};
        
        // Use the actual parcel coordinates for centering
        parcelCenter = { lat, lon };
        
        console.log('📍 Using actual starting point coordinates:', { lat, lon });
      } else if (plss.township_number && plss.township_direction && plss.range_number && plss.range_direction && plss.section_number) {
        // Fallback to estimated bounds based on TRS
        // This is a rough approximation - in practice, you'd want to use a proper TRS to coordinate conversion
        const baseLat = 41.5; // Wyoming approximate center
        const baseLon = -107.5;
        const buffer = 0.02;
				
				containerBounds = {
          west: baseLon - buffer,
          south: baseLat - buffer,
          east: baseLon + buffer,
          north: baseLat + buffer
        };
        
        parcelCenter = { lat: baseLat, lon: baseLon };
        
        console.log('📍 Using estimated bounds based on TRS');
      }

      const stateName = plss.state || 'Wyoming'; // Default to Wyoming
      
      console.log('📦 Container bounds calculated:', containerBounds);
      console.log('🏛️ State name:', stateName);
      console.log('🎯 Parcel center:', parcelCenter);
      
      return { containerBounds, stateName, parcelCenter };
		} catch (error) {
      console.error('❌ Error extracting container bounds from schema:', error);
      return { containerBounds: undefined, stateName: undefined, parcelCenter: initialView.center };
		}
  }, [schemaData, initialView.center]);

	return (
    <div className={`map-workspace ${className || ''}`} style={{ display: 'flex', height: '100%', width: '100%' }}>
		<MapContext.Provider value={ctx}>
        <div className="map-container" style={{ flex: 1, position: 'relative' }}>
					<MapEngine
            center={parcelCenter}
						zoom={zoom}
						onMapLoad={handleMapLoad}
						onMapMove={handleMapMove}
          />
				</div>

        {/* Side Panel */}
        <div style={{ width: '300px', minWidth: '300px', maxWidth: '300px', height: '100%', overflowY: 'auto' }}>
          <SidePanel>
            <TilesSection />
            <PropertiesSection polygon={initialParcels?.[0]} />
            
            {/* PLSS Overlays Section */}
            <SidePanelSection title="PLSS Overlays">
              <PLSSManager
                stateName={stateName || 'Wyoming'}
                schemaData={schemaData}
									containerBounds={containerBounds}
								/>
            </SidePanelSection>
							</SidePanel>
						</div>
      </MapContext.Provider>
			</div>
	);
};

export default MapWorkspace;


