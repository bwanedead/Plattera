"""
Centralized Text-to-Schema Prompts
Edit these prompts to adjust how LLMs convert text to structured parcel data
"""

# Main parcel schema conversion prompt using the exact parcel_v0.1.json structure
PARCEL_SCHEMA = """
Convert the following legal property description text into structured JSON data following the PlatteraParcel schema.

The legal description contains two main types of information:

1. **PLSS Description** (Public Land Survey System): Location reference information including township, range, section, and corner data
2. **Metes and Bounds**: Boundary course information with bearings, distances, and traverse descriptions

You must extract and organize the information into this exact structure:

{
  "parcel_id": "string - unique identifier for this parcel",
  "crs": "string - coordinate reference system: LOCAL, EPSG:4326, UTM, or PLSS",
  "origin": {
    "type": "string - latlon, utm, plss, or local",
    "lat": "number or null - latitude if available",
    "lon": "number or null - longitude if available", 
    "zone": "integer or null - UTM zone 1-60",
    "easting_m": "number or null - easting in meters",
    "northing_m": "number or null - northing in meters",
    "t": "integer or null - township number (PLSS Description)",
    "r": "integer or null - range number (PLSS Description)", 
    "section": "integer or null - section number 1-36 (PLSS Description)",
    "corner": "string or null - NW, NE, SW, SE, or null (PLSS Description)",
    "offset_m": "number or null - offset distance in meters",
    "offset_bearing_deg": "number or null - offset bearing 0-360 degrees",
    "note": "string or null - additional notes about origin"
  },
  "legs": [
    {
      "bearing_deg": "number - bearing in degrees 0-360 (Metes and Bounds)",
      "distance": "number - distance value as stated (Metes and Bounds)",
      "distance_units": "string - feet, meters, yards, chains, rods, miles, or kilometers",
      "distance_sigma": "number or null - uncertainty in measurement",
      "raw_text": "string - exact text describing this boundary segment",
      "confidence": "number - your confidence in this extraction 0-1"
    }
  ],
  "close": "boolean - does the description close back to starting point",
  "stated_area_ac": "number or null - area in acres if mentioned",
  "source": "string or null - source document reference"
}

IMPORTANT INSTRUCTIONS:
1. **PLSS Description Extraction**: Look for township (T), range (R), section numbers, and corner references (NW, NE, SW, SE)
2. **Metes and Bounds Extraction**: Extract each boundary segment with precise bearings and distances
3. Convert all bearings to degrees (0-360), distances to their stated units
4. Set confidence scores based on clarity of the text (0.9+ for clear, 0.7-0.8 for somewhat clear, <0.7 for unclear)
5. Use the raw_text field to capture the exact words describing each boundary segment
6. Determine coordinate reference system from context (PLSS for township/range, UTM for coordinates, etc.)
7. If information is missing or unclear, use null for optional fields
8. Generate a meaningful parcel_id if not provided in the text
9. Return only valid JSON without any additional commentary

Legal Description Text:
"""

def get_text_to_schema_prompt(schema_type: str, model: str = None) -> str:
    """
    Get the appropriate prompt for schema extraction
    
    Args:
        schema_type: The type of schema extraction (currently only "parcel" supported)
        model: The model being used (optional, for model-specific prompts)
        
    Returns:
        str: The prompt text for parcel schema extraction
    """
    
    # For now, we only support parcel schema
    return PARCEL_SCHEMA

# Simple property extraction
SIMPLE_PROPERTY = """
Extract basic property information from this text and return as JSON:

{
  "address": "string",
  "owner": "string", 
  "property_type": "string",
  "description": "string"
}

Text to process:
"""

# Contract terms extraction
CONTRACT_TERMS = """
Extract key contract terms from this legal text and structure as JSON:

{
  "parties": ["string"],
  "effective_date": "string",
  "expiration_date": "string", 
  "key_terms": ["string"],
  "obligations": {
    "party1": ["string"],
    "party2": ["string"]
  },
  "payment_terms": "string",
  "termination_clauses": ["string"]
}

Contract text:
""" 