export type OverlayLayer = 'townships' | 'ranges' | 'sections' | 'quarter_sections' | 'grid';

export interface OverlayFeatureCollection {
	type: 'FeatureCollection';
	features: Array<any>;
}

export class PLSSOverlayApi {
	private baseUrl = 'http://localhost:8000/api/mapping/overlays';
	private schemaData?: any; // Add schemaData property

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
		layer: OverlayLayer, // Fix type to use OverlayLayer
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

			return await response.json();
		} catch (error) {
			console.error(`❌ Container overlay API failed for ${layer}:`, error);
			throw error;
		}
	}

	// Add method to set schema data
	setSchemaData(schemaData: any) {
		this.schemaData = schemaData;
	}
}

export const plssOverlayApi = new PLSSOverlayApi();


