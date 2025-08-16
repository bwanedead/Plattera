import React, { createContext, useContext } from 'react';
import type maplibregl from 'maplibre-gl';

export interface MapViewState {
	center: { lat: number; lon: number };
	zoom: number;
	bounds: { west: number; south: number; east: number; north: number } | null;
	isLoaded: boolean;
}

export interface MapContextValue extends MapViewState {
	map: maplibregl.Map | null;
}

const defaultValue: MapContextValue = {
	map: null,
	center: { lat: 41.5, lon: -107.5 },
	zoom: 10,
	bounds: null,
	isLoaded: false
};

export const MapContext = createContext<MapContextValue>(defaultValue);

export function useMapContext(): MapContextValue {
	return useContext(MapContext);
}



