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
	private baseUrl = 'http://localhost:8000/api/mapping/overlays';
	private schemaData?: any;

	async getOverlay(
		layer: OverlayLayer, 
		state: string, 
		bounds?: { west: number; south: number; east: number; north: number }, 
		trs?: { t?: number; td?: string; r?: number; rd?: string; s?: number },
		abortSignal?: AbortSignal
	): Promise<OverlayFeatureCollection> {
		// Temporary fallback: map 'grid' to 'townships' until backend grid is guaranteed
		const apiLayer = layer === 'grid' ? 'townships' : layer;
		const url = new URL(`${this.baseUrl}/${apiLayer}/${state}`);
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
		
		const res = await fetch(url.toString(), { 
			signal: abortSignal 
		});
		
		if (!res.ok) throw new Error(`HTTP ${res.status}`);
		const data = await res.json();
		return data?.data || { type: 'FeatureCollection', features: [] };
	}

	async getContainerOverlay(
		layer: OverlayLayer, 
		containerBounds: { west: number; south: number; east: number; north: number },
		schemaData?: any,
		abortSignal?: AbortSignal
	): Promise<GeoJSON.FeatureCollection> {
		try {
			const response = await fetch(`${this.baseUrl}/container/${layer}/Wyoming`, {
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
			return data;
		} catch (error) {
			console.error(`❌ Container overlay API failed for ${layer}:`, error);
			throw error;
		}
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


