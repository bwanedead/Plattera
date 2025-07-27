/**
 * Shared types for Text-to-Schema functionality
 */

export interface ParcelOrigin {
  type: string; // "latlon", "utm", "plss", "local"
  lat?: number;
  lon?: number;
  zone?: number;
  easting_m?: number;
  northing_m?: number;
  t?: number; // Township (PLSS Description)
  r?: number; // Range (PLSS Description)
  section?: number; // Section 1-36 (PLSS Description)
  corner?: string; // "NW", "NE", "SW", "SE" (PLSS Description)
  offset_m?: number;
  offset_bearing_deg?: number;
  note?: string;
}

export interface ParcelLeg {
  bearing_deg: number; // Bearing 0-360 (Metes and Bounds)
  distance: number; // Distance value (Metes and Bounds)
  distance_units: string; // "feet", "meters", "yards", "chains", "rods", "miles", "kilometers"
  distance_sigma?: number;
  raw_text: string; // Exact text describing this boundary segment
  confidence: number; // Confidence 0-1
}

export interface ParcelSchema {
  parcel_id: string;
  plss_description: {
    state?: string | null;
    county?: string | null;
    principal_meridian?: string | null;
    township: string;
    range: string;
    section: number | string;
    quarter_section?: string | null;
    starting_point: {
      description: string;
      reference?: string | null;
      lat?: number | null;
      lon?: number | null;
      raw_text: string;
    };
    stated_area_acres?: number | null;
    raw_text: string;
  };
  metes_and_bounds: {
    boundary_courses: Array<{
      course: string;
      bearing_degrees?: number | null;
      distance?: number | null;
      distance_units?: string | null;
      raw_text: string;
      description?: string | null;
      confidence?: number | null;
    }>;
    closes_to_start: boolean;
    raw_text: string;
  };
  source?: string | null;
}

export interface TextToSchemaResult {
  success: boolean;
  structured_data?: ParcelSchema;
  original_text?: string;
  model_used?: string;
  service_type?: string;
  tokens_used?: number;
  confidence_score?: number;
  validation_warnings?: string[];
  metadata?: any;
  error?: string;
}

export type SchemaTab = 'original' | 'json' | 'fields'; 