import React, { useCallback, useMemo, useState, useEffect, useRef } from 'react';
import { MapContext, type MapContextValue } from './core/MapContext';
import { MapEngine } from './core/MapEngine';
import { OverlayManager } from './overlays/OverlayManager';
import { PLSSOverlayManager } from './overlays/PLSSOverlayManager';
import { PLSSControlPanel } from './controls/PLSSControls/PLSSControlPanel';
import { ParcelRelativePanel, type ParcelRelativeConfig } from './controls/PLSSControls/ParcelRelativePanel';
import { RegionalPanel, type RegionalConfig } from './controls/PLSSControls/RegionalPanel';
import { SidePanel } from './panels/SidePanel';
import { PLSSOverlaysSection } from './panels/PLSSOverlaysSection';
import { TilesSection } from './panels/TilesSection';
import { PropertiesSection } from './panels/PropertiesSection';
import type maplibregl from 'maplibre-gl';
import { plssOverlayApi, type OverlayLayer } from '../../services/plssOverlayApi';

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

	// PLSS overlay state management with proper logging
	const [overlayMode, setOverlayMode] = useState<'container' | 'regional'>('container');
	const [parcelCfg, setParcelCfg] = useState<ParcelRelativeConfig>({ 
		showTownship: false, 
		showRange: false, 
		showSection: false, 
		showQuarter: false,
		showGrid: false // Add the missing showGrid property
	});
	const [regionalCfg, setRegionalCfg] = useState<RegionalConfig>({ 
		mode: 'all-in-view', 
		maxFeatures: 10000 
	});

	// Extract TRS and container bounds from schema for container-based overlays
	const { trsFromSchema, containerBounds } = useMemo(() => {
		try {
			const plss = schemaData?.descriptions?.[0]?.plss;
			if (!plss) {
				console.log('🔍 No PLSS data found in schema for overlay filtering');
				return { trsFromSchema: undefined, containerBounds: undefined };
			}
			
			const trs = {
				t: plss.township_number,
				td: plss.township_direction,
				r: plss.range_number, 
				rd: plss.range_direction,
				s: plss.section_number
			};

			// Calculate container bounds - use section-level bounds for PLSS filtering
			// A section is roughly 1 mile x 1 mile, approximately 0.014° x 0.014°
			let containerBounds = undefined;
			
			// Check if we have coordinates from the starting point
			const startingPoint = plss.starting_point;
			if (startingPoint?.lat && startingPoint?.lon) {
				// Use actual coordinates if available
				const lat = startingPoint.lat;
				const lon = startingPoint.lon;
				const buffer = 0.02; // ~1.4 mile buffer around the point
				
				containerBounds = {
					west: lon - buffer,
					south: lat - buffer,
					east: lon + buffer,
					north: lat + buffer
				};
			} else if (trs.t && trs.td && trs.r && trs.rd && trs.s) {
				// QUICK TEST: Use backend-calculated coordinates for T14N R75W S2
				// TODO: Make this dynamic by calling backend PLSS lookup API
				const actualParcelCenter = { lat: 41.212048, lon: -105.779444 };
				const buffer = 0.02; // ~1.4 mile buffer around the section
				
				containerBounds = {
					west: actualParcelCenter.lon - buffer,
					south: actualParcelCenter.lat - buffer,
					east: actualParcelCenter.lon + buffer,
					north: actualParcelCenter.lat + buffer
				};
				console.log('🎯 TEST: Using backend-calculated coordinates for container bounds');
			}

			console.log('📍 Extracted TRS and container bounds from schema:', { trs, containerBounds });
			return { trsFromSchema: trs, containerBounds };
		} catch (error) {
			console.warn('⚠️ Error extracting TRS from schema:', error);
			return { trsFromSchema: undefined, containerBounds: undefined };
		}
	}, [schemaData]);

	// Handle overlay mode changes with logging
	const handleOverlayModeChange = useCallback((mode: 'container' | 'regional') => {
		console.log(`🔄 Switching overlay mode from ${overlayMode} to ${mode}`);
		setOverlayMode(mode);
	}, [overlayMode]);

	const sidePanelWidth = sidePanelCollapsed ? 40 : 320;

	useEffect(() => {
		// Set schema data on the PLSS overlay API when schema changes
		if (schemaData) {
			plssOverlayApi.setSchemaData(schemaData);
		}
	}, [schemaData]);

	const hasFitToContainerRef = useRef<string | null>(null);

	// Fit map to container bounds once when they become available; do not override user movement
	useEffect(() => {
		if (!map || !isLoaded) return;
		if (overlayMode !== 'container') return;
		if (!containerBounds) return;
		const key = `${containerBounds.west},${containerBounds.south},${containerBounds.east},${containerBounds.north}`;
		if (hasFitToContainerRef.current === key) return; // already fit for this bounds
		try {
			// Set map to parcel location immediately without animation
			(map as any).fitBounds(
				[[containerBounds.west, containerBounds.south], [containerBounds.east, containerBounds.north]],
				{ 
					padding: 50, 
					animate: false,  // Remove unwanted animation 
					duration: 0      // No duration
				}
			);
			hasFitToContainerRef.current = key;
			console.log('🗺️ Map centered on container bounds:', containerBounds);
		} catch (error) {
			console.warn('⚠️ Failed to center map:', error);
		}
	}, [map, isLoaded, overlayMode, containerBounds]);

	return (
		<MapContext.Provider value={ctx}>
			<div className={className} style={{ 
				width: '100%', 
				height: '100%', 
				display: 'flex',
				flexDirection: 'row'
			}}>
				{/* Main map area - takes remaining space */}
				<div style={{ 
					flex: 1,
					position: 'relative',
					minWidth: 0 // Important for flex child to shrink
				}}>
					<MapEngine
						center={center}
						zoom={zoom}
						onMapLoad={handleMapLoad}
						onMapMove={handleMapMove}
						onBasemapChange={(apply) => {
							// placeholder; next phase wire to TilesSection onChange
						}}
					/>
					<OverlayManager>
						<PLSSOverlayManager 
							stateName={(schemaData?.descriptions?.[0]?.plss?.state || 'Wyoming')} 
							parcelRelative={parcelCfg} 
							regional={regionalCfg}
							mode={overlayMode === 'container' ? 'parcel' : 'regional'}
							trs={overlayMode === 'container' ? trsFromSchema : undefined}
							containerBounds={overlayMode === 'container' ? containerBounds : undefined}
							schemaData={schemaData} // Add schema data prop
						/>
					</OverlayManager>
				</div>

				{/* Side panel - fixed width, docked to right */}
				<div style={{ 
					width: sidePanelWidth,
					height: '100%',
					flexShrink: 0,
					position: 'relative',
					borderLeft: '1px solid rgba(255, 255, 255, 0.1)'
				}}>
					{sidePanelCollapsed ? (
						// Collapsed state - thin bar with expand button
						<div style={{
							width: '100%',
							height: '100%',
							background: 'rgba(20,20,25,0.95)',
							display: 'flex',
							flexDirection: 'column',
							alignItems: 'center',
							padding: '12px 0'
						}}>
							<button
								onClick={() => setSidePanelCollapsed(false)}
								style={{
									background: 'rgba(255,255,255,0.1)',
									border: 'none',
									color: 'white',
									padding: '8px',
									borderRadius: '4px',
									cursor: 'pointer',
									fontSize: '16px'
								}}
								title="Expand Panel"
							>
								◀
							</button>
						</div>
					) : (
						// Expanded state - full panel
						<div style={{ 
							width: '100%', 
							height: '100%',
							position: 'relative'
						}}>
							{/* Collapse button */}
							<button
								onClick={() => setSidePanelCollapsed(true)}
								style={{
									position: 'absolute',
									top: '12px',
									right: '12px',
									background: 'rgba(255,255,255,0.1)',
									border: 'none',
									color: 'white',
									padding: '4px 8px',
									borderRadius: '4px',
									cursor: 'pointer',
									fontSize: '12px',
									zIndex: 10
								}}
								title="Collapse Panel"
							>
								▶
							</button>

							<SidePanel>
								<PLSSOverlaysSection
									parcelCfg={parcelCfg}
									setParcelCfg={setParcelCfg}
									regionalCfg={regionalCfg}
									setRegionalCfg={setRegionalCfg}
									mode={overlayMode}
									setMode={handleOverlayModeChange}
									containerAvailable={!!trsFromSchema}
									trsData={trsFromSchema}
									containerBounds={containerBounds}
								/>
								<TilesSection onChange={() => { /* next phase: swap basemap source */ }} />
								<PropertiesSection polygon={initialParcels?.[0]} />
							</SidePanel>
						</div>
					)}
				</div>
			</div>
		</MapContext.Provider>
	);
};


