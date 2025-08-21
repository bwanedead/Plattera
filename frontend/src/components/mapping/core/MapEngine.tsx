import React, { useEffect, useRef } from 'react';
import maplibregl, { Map as MapLibreMap } from 'maplibre-gl';

export interface MapEngineProps {
	center: { lat: number; lon: number };
	zoom: number;
	className?: string;
	styleConfig?: any; // MapLibre style JSON override if desired
	onMapLoad?: (map: MapLibreMap) => void;
	onMapMove?: (view: { center: { lat: number; lon: number }; zoom: number; bounds: { west: number; south: number; east: number; north: number } }) => void;
    onBasemapChange?: (apply: (map: MapLibreMap) => void) => void;
}

export const MapEngine: React.FC<MapEngineProps> = ({
	center,
	zoom,
	className,
	styleConfig,
	onMapLoad,
	onMapMove,
	onBasemapChange
}) => {
	const containerRef = useRef<HTMLDivElement>(null);
	const mapRef = useRef<MapLibreMap | null>(null);
	const hasInitiallyPositioned = useRef(false);

	// Create map only once
	useEffect(() => {
		if (!containerRef.current || mapRef.current) return;

		const style =
			styleConfig || {
				version: 8,
				sources: {
					'raster-tiles': {
						type: 'raster',
						tiles: ['http://localhost:8000/api/mapping/tile/usgs_topo/{z}/{x}/{y}'],
						tileSize: 256,
						minzoom: 0,
						maxzoom: 16,
						attribution: '© USGS'
					}
				},
				layers: [
					{ id: 'background', type: 'raster', source: 'raster-tiles' }
				]
			};

		const map = new maplibregl.Map({
			container: containerRef.current,
			style,
			center: [center.lon, center.lat],
			zoom,
			maxZoom: 20,
			attributionControl: false
		});

		mapRef.current = map;

		map.on('load', () => {
			onMapLoad?.(map);
		});

		map.on('moveend', () => {
			const c = map.getCenter();
			const b = map.getBounds();
			onMapMove?.({
				center: { lat: c.lat, lon: c.lng },
				zoom: map.getZoom(),
				bounds: { west: b.getWest(), south: b.getSouth(), east: b.getEast(), north: b.getNorth() }
			});
		});

		return () => {
			map.remove();
			mapRef.current = null;
		};
	}, [styleConfig, onMapLoad, onMapMove]); // REMOVED center/zoom from dependencies

	// Separate effect to position map ONLY when parcel coordinates become available
	useEffect(() => {
		const map = mapRef.current;
		if (map && !hasInitiallyPositioned.current && center.lat !== 41.5 && center.lon !== -107.5) {
			// Only move the map if we have real coordinates (not the default Wyoming center)
			console.log('🗺️ MapEngine: Flying to parcel location:', center, 'zoom:', zoom);
			map.flyTo({
				center: [center.lon, center.lat],
				zoom: zoom,
				duration: 1500
			});
			hasInitiallyPositioned.current = true;
		}
	}, [center.lat, center.lon, zoom]);

	// Allow external code to inject basemap changes safely
	useEffect(() => {
		if (mapRef.current && onBasemapChange) {
			onBasemapChange((map) => {
				// no-op default; caller provides implementation
			});
		}
	}, [onBasemapChange]);

	return <div ref={containerRef} className={className} style={{ width: '100%', height: '100%' }} />;
};


