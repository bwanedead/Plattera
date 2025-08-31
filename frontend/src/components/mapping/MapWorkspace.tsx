import React, { useCallback, useMemo, useState, useEffect, useRef } from 'react';
import { MapContext, type MapContextValue } from './core/MapContext';
import { MapEngine } from './core/MapEngine';
import { OverlayManager } from './overlays/OverlayManager';
import { PLSSManager } from './overlays/PLSSManager';
import { MeasurementManager } from './overlays/MeasurementManager';
import { SidePanel, SidePanelSection } from './panels/SidePanel';
import { TilesSection } from './panels/TilesSection';
import { PropertiesSection } from './panels/PropertiesSection';
import { ParcelOverlay } from './overlays/ParcelOverlay';
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
		try {
			const c = m.getCenter();
			const z = m.getZoom();
			console.log('🗺️ Map loaded:', { center: { lat: c.lat, lon: c.lng }, zoom: z });
		} catch (e) {
			console.warn('Map load logging failed:', e);
		}
	}, []);

	const handleMapMove = useCallback((view: { center: { lat: number; lon: number }; zoom: number; bounds: { west: number; south: number; east: number; north: number } }) => {
		setCenter(view.center);
		setZoom(view.zoom);
		setBounds(view.bounds);
		console.log('🔄 Map moved:', view);
	}, []);

	const ctx = useMemo<MapContextValue>(() => ({ map, isLoaded, center, zoom, bounds }), [map, isLoaded, center, zoom, bounds]);

  // Extract container bounds and center from multiple sources for container-based overlays
  const { containerBounds, stateName, parcelCenter } = useMemo(() => {
    try {
      console.log('🔍 Schema data structure:', schemaData);
      console.log('🔍 Initial parcels:', initialParcels);
      
      // Initialize variables
      let containerBounds: any = undefined;
      let parcelCenter: any = initialView.center;
      let stateName = 'Wyoming'; // Default
      
      // Priority 1: Use POB from georeferenced polygon data (most accurate)
      if (initialParcels && initialParcels.length > 0) {
        const polygon = initialParcels[0];
        console.log('🔍 Using georeferenced polygon data:', polygon);
        
        if (polygon?.anchor_info?.pob_coordinates) {
          const pob = polygon.anchor_info.pob_coordinates;
          const lat = pob.lat;
          const lon = pob.lon;
          const buffer = 0.02; // ~1.4 mile buffer
          
          containerBounds = {
            west: lon - buffer,
            south: lat - buffer,
            east: lon + buffer,
            north: lat + buffer
          };
          
          parcelCenter = { lat, lon };
          console.log('📍 Using POB coordinates from georeferenced polygon:', { lat, lon });
        }
        // Fallback: use polygon bounds
        else if (polygon?.geographic_polygon?.bounds) {
          const bounds = polygon.geographic_polygon.bounds;
          const buffer = 0.01; // Smaller buffer since we have actual bounds
          
          containerBounds = {
            west: bounds.min_lon - buffer,
            south: bounds.min_lat - buffer,
            east: bounds.max_lon + buffer,
            north: bounds.max_lat + buffer
          };
          
          parcelCenter = {
            lat: (bounds.min_lat + bounds.max_lat) / 2,
            lon: (bounds.min_lon + bounds.max_lon) / 2
          };
          console.log('📍 Using polygon bounds for container bounds:', containerBounds);
        }
      }
      
      // Priority 2: Extract state from schema data
      if (schemaData?.descriptions?.[0]?.plss?.state) {
        stateName = schemaData.descriptions[0].plss.state;
      }
      
      // Priority 3: Fallback to schema-based approach if no polygon data
      if (!containerBounds && schemaData) {
        const plss = schemaData?.descriptions?.[0]?.plss;
        if (plss) {
          // Use starting point coordinates if available
          if (plss.starting_point?.latitude && plss.starting_point?.longitude) {
            const lat = plss.starting_point.latitude;
            const lon = plss.starting_point.longitude;
            const buffer = 0.02;
            
            containerBounds = {
              west: lon - buffer,
              south: lat - buffer,
              east: lon + buffer,
              north: lat + buffer
            };
            
            parcelCenter = { lat, lon };
            console.log('📍 Using starting point coordinates from schema:', { lat, lon });
          }
          // Final fallback: rough TRS-based estimate
          else if (plss.township_number && plss.township_direction && plss.range_number && plss.range_direction) {
            const baseLat = 41.5; // Wyoming center
            const baseLon = -107.5;
            const buffer = 0.02;
            
            containerBounds = {
              west: baseLon - buffer,
              south: baseLat - buffer,
              east: baseLon + buffer,
              north: baseLat + buffer
            };
            
            parcelCenter = { lat: baseLat, lon: baseLon };
            console.log('📍 Using TRS-based estimate for container bounds');
          }
        }
      }
      
      console.log('📦 Final container bounds:', containerBounds);
      console.log('🏛️ State name:', stateName);
      console.log('🎯 Parcel center:', parcelCenter);
      
      return { containerBounds, stateName, parcelCenter };
    } catch (error) {
      console.error('❌ Error extracting container bounds:', error);
      return { containerBounds: undefined, stateName: 'Wyoming', parcelCenter: initialView.center };
    }
  }, [schemaData, initialParcels, initialView.center]);

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
          
          {/* Add ParcelOverlay to render georeferenced polygons */}
          <ParcelOverlay parcels={initialParcels} />

				{/* Debug: print rendered polygon vertices */}
				{isLoaded && initialParcels?.[0]?.geographic_polygon?.coordinates && (
					(() => {
						const coords = initialParcels[0].geographic_polygon.coordinates?.[0] || [];
						console.log('🧩 Rendered parcel vertices (lon,lat):', coords);
						return null;
					})()
				)}
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

            {/* Measurement Tools */}
            <MeasurementManager stateName={stateName || 'Wyoming'} />
							</SidePanel>
						</div>
      </MapContext.Provider>
			</div>
	);
};

export default MapWorkspace;


