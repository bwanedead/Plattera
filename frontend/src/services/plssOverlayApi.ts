export type OverlayLayer = 'townships' | 'ranges' | 'sections' | 'quarter_sections' | 'grid';

export interface OverlayFeatureCollection {
	type: 'FeatureCollection';
	features: Array<any>;
}

export interface PLSSCoordinates {
	latitude: number;
	longitude: number;
	trs_string: string;
}

export class PLSSOverlayApi {
	private cleanUrl = 'http://localhost:8000/api/plss/overlays'; // NEW: Clean endpoints
	private legacyUrl = 'http://localhost:8000/api/mapping/overlays'; // Fallback
	private schemaData?: any;

	async getOverlay(
		layer: OverlayLayer, 
		state: string, 
		bounds?: { west: number; south: number; east: number; north: number }, 
		trs?: { t?: number; td?: string; r?: number; rd?: string; s?: number },
		abortSignal?: AbortSignal
	): Promise<OverlayFeatureCollection> {
		// Try new clean endpoints first, fallback to legacy if needed
		try {
			return await this._getOverlayClean(layer, state, bounds, trs, abortSignal);
		} catch (error) {
			console.warn(`🔄 Clean API failed for ${layer}, falling back to legacy:`, error);
			return await this._getOverlayLegacy(layer, state, bounds, trs, abortSignal);
		}
	}

	private async _getOverlayClean(
		layer: OverlayLayer, 
		state: string, 
		bounds?: { west: number; south: number; east: number; north: number }, 
		trs?: { t?: number; td?: string; r?: number; rd?: string; s?: number },
		abortSignal?: AbortSignal
	): Promise<OverlayFeatureCollection> {
		// Map 'grid' to 'townships' for backward compatibility
		const apiLayer = layer === 'grid' ? 'townships' : layer;
		
		// Use appropriate endpoint based on parameters
		if (trs && Object.values(trs).some(v => v !== undefined)) {
			// Use exact endpoint for TRS queries
			const url = new URL(`${this.cleanUrl}/exact/${apiLayer}/${state}`);
			if (trs.t !== undefined) url.searchParams.set('t', String(trs.t));
			if (trs.td) url.searchParams.set('td', trs.td);
			if (trs.r !== undefined) url.searchParams.set('r', String(trs.r));
			if (trs.rd) url.searchParams.set('rd', trs.rd);
			if (trs.s !== undefined) url.searchParams.set('s', String(trs.s));
			
			const res = await fetch(url.toString(), { signal: abortSignal });
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const data = await res.json();
			
			if (!data.success) throw new Error(data.error || 'Exact overlay request failed');
			return data; // New format already has features at root level
		} else if (bounds) {
			// Use regional endpoint for bounds queries
			const url = new URL(`${this.cleanUrl}/regional/${apiLayer}/${state}`);
			url.searchParams.set('min_lon', String(bounds.west));
			url.searchParams.set('min_lat', String(bounds.south));
			url.searchParams.set('max_lon', String(bounds.east));
			url.searchParams.set('max_lat', String(bounds.north));
			
			const res = await fetch(url.toString(), { signal: abortSignal });
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const data = await res.json();
			
			if (!data.success) throw new Error(data.error || 'Regional overlay request failed');
			return data; // New format already has features at root level
		} else {
			throw new Error('Either bounds or TRS must be provided for overlay query');
		}
	}

	private async _getOverlayLegacy(
		layer: OverlayLayer, 
		state: string, 
		bounds?: { west: number; south: number; east: number; north: number }, 
		trs?: { t?: number; td?: string; r?: number; rd?: string; s?: number },
		abortSignal?: AbortSignal
	): Promise<OverlayFeatureCollection> {
		// Legacy endpoint format
		const apiLayer = layer === 'grid' ? 'townships' : layer;
		const url = new URL(`${this.legacyUrl}/${apiLayer}/${state}`);
		if (bounds) {
			url.searchParams.set('min_lon', String(bounds.west));
			url.searchParams.set('min_lat', String(bounds.south));
			url.searchParams.set('max_lon', String(bounds.east));
			url.searchParams.set('max_lat', String(bounds.north));
		}
		if (trs) {
			if (trs.t !== undefined) url.searchParams.set('t', String(trs.t));
			if (trs.td) url.searchParams.set('td', trs.td);
			if (trs.r !== undefined) url.searchParams.set('r', String(trs.r));
			if (trs.rd) url.searchParams.set('rd', trs.rd);
			if (trs.s !== undefined) url.searchParams.set('s', String(trs.s));
		}
		
		const res = await fetch(url.toString(), { signal: abortSignal });
		if (!res.ok) throw new Error(`HTTP ${res.status}`);
		const data = await res.json();
		return data?.data || { type: 'FeatureCollection', features: [] }; // Legacy format
	}

	async getContainerOverlay(
		layer: OverlayLayer, 
		containerBounds: { west: number; south: number; east: number; north: number },
		schemaData?: any,
		abortSignal?: AbortSignal
	): Promise<GeoJSON.FeatureCollection> {
		// Try new clean container endpoint first, fallback to legacy if needed
		try {
			return await this._getContainerOverlayClean(layer, containerBounds, schemaData, abortSignal);
		} catch (error) {
			console.warn(`🔄 Clean container API failed for ${layer}, falling back to legacy:`, error);
			return await this._getContainerOverlayLegacy(layer, containerBounds, schemaData, abortSignal);
		}
	}

	private async _getContainerOverlayClean(
		layer: OverlayLayer, 
		containerBounds: { west: number; south: number; east: number; north: number },
		schemaData?: any,
		abortSignal?: AbortSignal
	): Promise<GeoJSON.FeatureCollection> {
		const apiLayer = layer === 'grid' ? 'townships' : layer;
		const response = await fetch(`${this.cleanUrl}/container/${apiLayer}/Wyoming`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
			},
			body: JSON.stringify({
				container_bounds: containerBounds,
				schema_data: schemaData || this.schemaData || {}
			}),
			signal: abortSignal
		});

		if (!response.ok) {
			throw new Error(`HTTP ${response.status}`);
		}

		const data = await response.json();
		if (!data.success) {
			throw new Error(data.error || 'Container overlay request failed');
		}
		return data; // New format
	}

	private async _getContainerOverlayLegacy(
		layer: OverlayLayer, 
		containerBounds: { west: number; south: number; east: number; north: number },
		schemaData?: any,
		abortSignal?: AbortSignal
	): Promise<GeoJSON.FeatureCollection> {
		const response = await fetch(`${this.legacyUrl}/container/${layer}/Wyoming`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
			},
			body: JSON.stringify({
				container_bounds: containerBounds,
				schema_data: schemaData || this.schemaData || {}
			}),
			signal: abortSignal
		});

		if (!response.ok) {
			throw new Error(`HTTP ${response.status}`);
		}

		const data = await response.json();
		return data; // Legacy format
	}

	// NEW: Get PLSS coordinates from TRS data
	async getPLSSCoordinates(
		trs: { t: number; td: string; r: number; rd: string; s?: number },
		state: string = 'Wyoming'
	): Promise<PLSSCoordinates> {
		try {
			const trsString = `T${trs.t}${trs.td} R${trs.r}${trs.rd}${trs.s ? ` S${trs.s}` : ''}`;
			console.log(`🔍 Getting PLSS coordinates for: ${trsString}`);

			const response = await fetch('http://localhost:8000/api/mapping/plss-lookup', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
				},
				body: JSON.stringify({
					trs_string: trsString,
					state: state
				})
			});

			if (!response.ok) {
				throw new Error(`HTTP ${response.status}`);
			}

			const data = await response.json();
			console.log(`✅ PLSS coordinates for ${trsString}:`, data);
			
			return {
				latitude: data.latitude,
				longitude: data.longitude,
				trs_string: trsString
			};
		} catch (error) {
			console.error(`❌ PLSS coordinate lookup failed:`, error);
			throw error;
		}
	}

	// Add method to set schema data
	setSchemaData(schemaData: any) {
		this.schemaData = schemaData;
	}
}

export const plssOverlayApi = new PLSSOverlayApi();


