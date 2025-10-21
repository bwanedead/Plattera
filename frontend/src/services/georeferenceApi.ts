/**
 * Georeference API Service (dedicated)
 * Provides endpoints to project polygons and resolve POB
 */

const API_BASE = 'http://localhost:8000/api/mapping/georeference';

export interface LocalCoordinate {
  x: number;
  y: number;
}

export interface PLSSDescription {
  state: string;
  county?: string;
  principal_meridian?: string;
  township_number: number;
  township_direction: string;
  range_number: number;
  range_direction: string;
  section_number: number;
  quarter_sections?: string;
}

export interface GeographicBounds {
  min_lat: number;
  max_lat: number;
  min_lon: number;
  max_lon: number;
}

export interface GeoreferenceProjectRequest {
  local_coordinates: LocalCoordinate[];
  plss_anchor: PLSSDescription;
  options?: Record<string, any>;
  starting_point?: {
    tie_to_corner?: {
      corner_label?: string;
      bearing_raw?: string;
      distance_value?: number;
      distance_units?: string;
      tie_direction?: 'corner_bears_from_pob' | 'pob_bears_from_corner';
    }
  };
}

export interface GeoreferenceProjectFromSchemaRequest {
  schema_data: any;
  polygon_data: any;
}

export interface GeoreferenceProjectResponse {
  success: boolean;
  geographic_polygon?: {
    type: string;
    coordinates: number[][][];
    bounds: GeographicBounds;
  };
  bounds?: GeographicBounds; // normalized top-level copy
  anchor_info?: any;
  projection_metadata?: any;
  error?: string;
}

export interface ResolvePOBRequest {
  plss_anchor: PLSSDescription;
  starting_point?: {
    tie_to_corner?: {
      corner_label?: string;
      bearing_raw?: string;
      distance_value?: number;
      distance_units?: string;
      tie_direction?: 'corner_bears_from_pob' | 'pob_bears_from_corner';
    }
  };
}

export interface ResolvePOBResponse {
  success: boolean;
  pob_geographic?: { lat: number; lon: number };
  pob_utm?: { x: number; y: number; zone: string };
  method?: string;
  corner_info?: any;
  error?: string;
}

class GeoreferenceApiService {
  async project(request: GeoreferenceProjectRequest): Promise<GeoreferenceProjectResponse> {
    try {
      const res = await fetch(`${API_BASE}/project`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request)
      });
      if (!res.ok) {
        const e = await res.json();
        throw new Error(e.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      if (data?.geographic_polygon?.bounds && !data.bounds) {
        data.bounds = data.geographic_polygon.bounds;
      }
      return data;
    } catch (e: any) {
      return { success: false, error: e?.message || 'Unknown error' };
    }
  }

  async projectFromSchema(request: GeoreferenceProjectFromSchemaRequest): Promise<GeoreferenceProjectResponse> {
    try {
      const res = await fetch(`${API_BASE}/project-from-schema`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request)
      });
      if (!res.ok) {
        const e = await res.json();
        throw new Error(e.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      if (data?.geographic_polygon?.bounds && !data.bounds) {
        data.bounds = data.geographic_polygon.bounds;
      }
      return data;
    } catch (e: any) {
      return { success: false, error: e?.message || 'Unknown error' };
    }
  }

  async resolvePOB(request: ResolvePOBRequest): Promise<ResolvePOBResponse> {
    try {
      const res = await fetch(`${API_BASE}/resolve-pob`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request)
      });
      if (!res.ok) {
        const e = await res.json();
        throw new Error(e.detail || `HTTP ${res.status}`);
      }
      return await res.json();
    } catch (e: any) {
      return { success: false, error: e?.message || 'Unknown error' };
    }
  }
}

export const georeferenceApi = new GeoreferenceApiService();

export const saveGeoreferenceForDossier = async (payload: {
  dossier_id: string;
  georef_result: any;
  metadata?: any;
}) => {
  const res = await fetch(`${API_BASE}/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(`Failed to save georeference (${res.status}): ${txt}`);
  }
  return res.json();
};

export const listGeoreferences = async (dossierId: string) => {
  const res = await fetch(`${API_BASE}/list?dossier_id=${encodeURIComponent(dossierId)}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  return res.json();
};

export const getGeoreference = async (dossierId: string, georefId: string) => {
  const res = await fetch(`${API_BASE}/get?dossier_id=${encodeURIComponent(dossierId)}&georef_id=${encodeURIComponent(georefId)}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  return res.json();
};
