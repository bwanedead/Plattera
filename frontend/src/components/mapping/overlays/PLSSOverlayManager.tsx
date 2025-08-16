import React, { useEffect, useMemo, useRef, useCallback } from 'react';
import { useMapContext } from '../core/MapContext';
import { plssOverlayApi, type OverlayLayer } from '../../../services/plssOverlayApi';

// Add cache interface
interface CacheEntry {
	data: any;
	timestamp: number;
	bounds: { west: number; south: number; east: number; north: number } | null; // Allow null
}

interface OverlayCache {
	[key: string]: CacheEntry;
}

export interface ParcelRelativeConfig {
	showTownship: boolean;
	showRange: boolean;
	showSection: boolean;
	showQuarter: boolean;
	showGrid: boolean; // Add the new grid option
	selectedParcelId?: string;
}

export interface RegionalConfig {
	mode: 'all-in-view' | 'selected-areas' | 'custom';
	maxFeatures: number;
}

export interface PLSSOverlayManagerProps {
	stateName: string;
	parcelRelative: ParcelRelativeConfig;
	regional: RegionalConfig;
	mode?: 'parcel' | 'regional';
	trs?: { t?: number; td?: string; r?: number; rd?: string; s?: number };
	containerBounds?: { west: number; south: number; east: number; north: number };
}

function ensureSource(map: any, sourceId: string, data: any) {
	if (!map || !map.getSource) return false;
	
	try {
		if (map.getSource(sourceId)) {
			map.getSource(sourceId).setData(data);
		} else {
			map.addSource(sourceId, { type: 'geojson', data });
		}
		return true;
	} catch (error) {
		console.warn(`Failed to add/update source ${sourceId}:`, error);
		return false;
	}
}

function ensureLineLayer(map: any, layerId: string, sourceId: string, color: string, width: number, dash?: number[]) {
	if (!map || !map.getLayer) return false;
	
	try {
		if (map.getLayer(layerId)) return true;
		
		map.addLayer({
			id: layerId,
				type: 'line',
				source: sourceId,
			paint: { 'line-color': color, 'line-width': width, ...(dash && { 'line-dasharray': dash }) },
			layout: { 'line-join': 'round', 'line-cap': 'round' }
		});
		return true;
	} catch (error) {
		console.warn(`Failed to add line layer ${layerId}:`, error);
		return false;
	}
}

function ensureLabelLayer(map: any, layerId: string, sourceId: string, minzoom: number) {
	if (!map || !map.getLayer) return false;
	
	try {
		if (map.getLayer(layerId)) return true;
		
		// Skip labels for now to avoid font issues - we can add them back later with proper font loading
		return true;
		
		/* 
		map.addLayer({
			id: layerId,
			type: 'symbol',
			source: sourceId,
			minzoom,
			layout: {
				'text-field': ['get', '__label'],
				'text-font': ['Open Sans Semibold', 'Arial Unicode MS Bold'],
				'text-size': 10,
				'text-allow-overlap': false
			},
			paint: { 'text-color': '#333', 'text-halo-color': '#fff', 'text-halo-width': 1 }
		});
		*/
	} catch (error) {
		console.warn(`Failed to add label layer ${layerId}:`, error);
		return false;
	}
}

function getStyleForLayer(layer: OverlayLayer): { color: string; width: number; dash?: number[]; minzoom: number } {
	switch (layer) {
		case 'townships': return { color: '#e74c3c', width: 2, minzoom: 8 };
		case 'ranges': return { color: '#3498db', width: 2.5, minzoom: 7 };
		case 'sections': return { color: '#2ecc71', width: 1.5, minzoom: 10 };
		case 'quarter_sections': return { color: '#f39c12', width: 1, dash: [2, 2], minzoom: 12 };
		case 'grid': return { color: '#9b59b6', width: 2, minzoom: 7 }; // Add grid styling
		default: return { color: '#999', width: 1, minzoom: 8 } as any;
	}
}

// Helper function to create cache key
function createCacheKey(layer: OverlayLayer, bounds: any, mode: string, trs?: any): string {
	const round = (n: number) => Math.round(n * 1000) / 1000;
	const boundsStr = bounds ? `${round(bounds.west)},${round(bounds.south)},${round(bounds.east)},${round(bounds.north)}` : 'nobounds';
	const trsStr = trs ? `${trs.t || ''}${trs.td || ''}${trs.r || ''}${trs.rd || ''}${trs.s || ''}` : 'notrs';
	return `${layer}_${mode}_${boundsStr}_${trsStr}`;
}

// Helper function to check if bounds overlap significantly
function boundsOverlap(bounds1: any, bounds2: any, threshold = 0.8): boolean {
	if (!bounds1 || !bounds2) return false;
	
	const intersection = {
		west: Math.max(bounds1.west, bounds2.west),
		east: Math.min(bounds1.east, bounds2.east),
		north: Math.min(bounds1.north, bounds2.north),
		south: Math.max(bounds1.south, bounds2.south)
	};
	
	if (intersection.west >= intersection.east || intersection.south >= intersection.north) {
		return false;
	}
	
	const intersectionArea = (intersection.east - intersection.west) * (intersection.north - intersection.south);
	const bounds1Area = (bounds1.east - bounds1.west) * (bounds1.north - bounds1.south);
	
	return (intersectionArea / bounds1Area) >= threshold;
}

export const PLSSOverlayManager: React.FC<PLSSOverlayManagerProps> = ({ 
	stateName, 
	parcelRelative, 
	regional, 
	mode = 'parcel',
	trs,
	containerBounds 
}) => {
	const { map, isLoaded, bounds } = useMapContext();
	const activeSources = useRef<string[]>([]);
	const abortControllerRef = useRef<AbortController | null>(null);
	const updateTimeoutRef = useRef<NodeJS.Timeout | null>(null);
	const cache = useRef<OverlayCache>({});
	const lastSuccessfulUpdate = useRef<{ bounds: any; config: any } | null>(null);

	// Debounced update function to prevent rapid-fire requests
	const debouncedUpdate = useCallback(() => {
		// Clear any existing timeout
		if (updateTimeoutRef.current) {
			clearTimeout(updateTimeoutRef.current);
		}

		// Cancel any in-flight requests
		if (abortControllerRef.current) {
			abortControllerRef.current.abort();
		}

		// Set new timeout for debounced execution
		updateTimeoutRef.current = setTimeout(() => {
			performUpdate();
		}, 500); // 500ms debounce
	// Only depend on viewport bounds in regional mode; in parcel mode depend on containerBounds instead
	}, [mode, parcelRelative, stateName, trs, (mode === 'parcel' ? containerBounds : bounds)]);

	// Enhanced load layer with caching
	const loadLayer = async (layer: OverlayLayer, abortSignal: AbortSignal) => {
		const currentMap = map;
		if (!currentMap || !isLoaded) {
			console.warn(`🚫 Cannot load ${layer}: map not ready`);
			return;
		}
		
		// Choose appropriate bounds for filtering
		let filterBounds = bounds;
		
		if (mode === 'parcel') {
			if (containerBounds) {
				filterBounds = containerBounds;
				console.log(`🎯 Loading ${layer} with container bounds:`, containerBounds);
			} else {
				console.warn(`⚠️ Container mode but no container bounds available`);
				return;
			}
		} else if (bounds) {
			console.log(`🗺️ Loading ${layer} with map viewport bounds:`, bounds);
		} else {
			console.warn(`⚠️ No bounds available for loading ${layer}`);
			return;
		}

		try {
			// Check cache first
			const cacheKey = createCacheKey(layer, filterBounds, mode, trs);
			const cached = cache.current[cacheKey];
			
			// Use cache if it's recent (within 5 minutes) and bounds overlap significantly
			if (cached && 
				(Date.now() - cached.timestamp) < 300000 && 
				cached.bounds && // Check that cached bounds exists
				boundsOverlap(cached.bounds, filterBounds)) {
				console.log(`💾 Using cached data for ${layer}`);
				
				// Verify map is still valid before using cached data
				if (!currentMap || !currentMap.getSource) {
					console.warn(`🚫 Map no longer valid for cached ${layer}`);
					return;
				}
				
		const sourceId = `plss-${layer}`;
		const { color, width, dash, minzoom } = getStyleForLayer(layer);

				const sourceSuccess = ensureSource(currentMap, sourceId, cached.data);
				if (sourceSuccess) {
					ensureLineLayer(currentMap, `${sourceId}-line`, sourceId, color, width, dash);
					ensureLabelLayer(currentMap, `${sourceId}-labels`, sourceId, minzoom);
					
					if (!activeSources.current.includes(sourceId)) {
						activeSources.current.push(sourceId);
					}
				}
				return;
			}

			// Fetch new data
			let data;
			
			// Use container endpoint for parcel mode, regular endpoint for regional mode
			if (mode === 'parcel' && containerBounds) {
				data = await plssOverlayApi.getContainerOverlay(
					layer,
					containerBounds,
					undefined, // schemaData will be set from context
					abortSignal
				);
			} else {
				data = await plssOverlayApi.getOverlay(
					layer, 
					stateName, 
					filterBounds || undefined, 
					undefined, // no TRS filtering for regional mode
					abortSignal
				);
			}
			
			// Check if request was aborted
			if (abortSignal.aborted) {
				console.log(`🚫 Request aborted for ${layer}`);
				return;
			}
			
			console.log(`✅ Loaded ${layer}: ${data.features?.length || 0} features`);
			
			// Cache the result - only if we have valid bounds
			if (filterBounds) {
				cache.current[cacheKey] = {
					data,
					timestamp: Date.now(),
					bounds: filterBounds
				};
				
				// Clean old cache entries (keep only last 10)
				const cacheKeys = Object.keys(cache.current);
				if (cacheKeys.length > 10) {
					const sortedKeys = cacheKeys.sort((a, b) => 
						cache.current[b].timestamp - cache.current[a].timestamp
					);
					sortedKeys.slice(10).forEach(key => delete cache.current[key]);
				}
			}
			
			// Verify map is still valid before proceeding
			if (!currentMap || !currentMap.getSource) {
				console.warn(`🚫 Map no longer valid for ${layer}`);
				return;
			}
			
			const sourceId = `plss-${layer}`;
			const { color, width, dash, minzoom } = getStyleForLayer(layer);

			const sourceSuccess = ensureSource(currentMap, sourceId, data);
			if (sourceSuccess) {
				ensureLineLayer(currentMap, `${sourceId}-line`, sourceId, color, width, dash);
				ensureLabelLayer(currentMap, `${sourceId}-labels`, sourceId, minzoom);

				if (!activeSources.current.includes(sourceId)) {
					activeSources.current.push(sourceId);
				}
			}
		} catch (error) {
			if (error instanceof Error && error.name === 'AbortError') {
				console.log(`🚫 Request cancelled for ${layer}`);
			} else {
				console.error(`❌ Failed to load ${layer}:`, error);
			}
		}
	};

	// Main update function with better persistence
	const performUpdate = async () => {
		if (!map || !isLoaded) return;

		// Skip update if configuration hasn't changed significantly
		const currentConfig = { mode, parcelRelative, containerBounds, bounds };
		if (lastSuccessfulUpdate.current && 
			JSON.stringify(lastSuccessfulUpdate.current.config) === JSON.stringify(currentConfig) &&
			boundsOverlap(lastSuccessfulUpdate.current.bounds, bounds, 0.9)) {
			console.log('🔄 Skipping update - configuration unchanged');
			return;
		}

		console.log(`🔄 Updating PLSS overlays - Mode: ${mode}, Container Bounds:`, containerBounds);

		// Create new abort controller for this update cycle
		if (abortControllerRef.current) {
			abortControllerRef.current.abort();
		}
		abortControllerRef.current = new AbortController();
		const abortSignal = abortControllerRef.current.signal;

		// Determine desired layers based on toggles
		const wantLayers: OverlayLayer[] = [];
		if (parcelRelative.showGrid) {
			wantLayers.push('grid');
		} else {
			if (parcelRelative.showTownship) wantLayers.push('townships');
			if (parcelRelative.showRange) wantLayers.push('ranges');
		}
		if (parcelRelative.showSection) wantLayers.push('sections');
		if (parcelRelative.showQuarter) wantLayers.push('quarter_sections');

		// Remove only layers that are not desired
		const allLayerTypes: OverlayLayer[] = ['townships','ranges','sections','quarter_sections','grid'];
		for (const layerType of allLayerTypes) {
			if (!wantLayers.includes(layerType)) {
			const sourceId = `plss-${layerType}`;
			try {
				if (map.getLayer(`${sourceId}-labels`)) map.removeLayer(`${sourceId}-labels`);
				if (map.getLayer(`${sourceId}-line`)) map.removeLayer(`${sourceId}-line`);
				if (map.getSource(sourceId)) map.removeSource(sourceId);
			} catch {}
			}
		}

		// Clear active sources list; they will be repopulated
		activeSources.current = [];

		// Check mode requirements
		if (mode === 'parcel' && !containerBounds) {
			console.warn('🚫 Container mode selected but no container bounds available');
			return;
		}

		// Load desired layers
		const tasks: Promise<any>[] = [];
		for (const layer of wantLayers) {
			tasks.push(loadLayer(layer, abortSignal));
		}
		await Promise.allSettled(tasks);
		
		// Record successful update
		lastSuccessfulUpdate.current = {
			config: currentConfig,
			bounds: bounds
		};
	};

	// Use debounced update effect
	useEffect(() => {
		debouncedUpdate();
		return () => {
			if (updateTimeoutRef.current) clearTimeout(updateTimeoutRef.current);
			if (abortControllerRef.current) abortControllerRef.current.abort();
		};
	}, [debouncedUpdate]);

	// Regional placeholder
	useEffect(() => {
		if (mode !== 'regional') return;
		console.log('🌍 Regional overlay mode - future implementation');
	}, [mode, regional]);

	return null;
};


