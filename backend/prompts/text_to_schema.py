"""
Centralized Text-to-Schema Prompts
Edit these prompts to adjust how LLMs convert text to structured parcel data
"""

# Main parcel schema conversion prompt using the exact parcel_v0.1.json structure
PARCEL_SCHEMA = """
Convert the following legal property description text into structured JSON data following the PlatteraParcel schema.

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
    "t": "integer or null - township number",
    "r": "integer or null - range number", 
    "section": "integer or null - section number 1-36",
    "corner": "string or null - NW, NE, SW, SE, or null",
    "offset_m": "number or null - offset distance in meters",
    "offset_bearing_deg": "number or null - offset bearing 0-360 degrees",
    "note": "string or null - additional notes about origin"
  },
  "legs": [
    {
      "bearing_deg": "number - bearing in degrees 0-360",
      "distance": "number - distance value as stated",
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
1. Extract each boundary segment (leg) from the legal description with bearing and distance
2. Convert all bearings to degrees (0-360), distances to their stated units
3. Set confidence scores based on clarity of the text (0.9+ for clear, 0.7-0.8 for somewhat clear, <0.7 for unclear)
4. Use the raw_text field to capture the exact words describing each boundary segment
5. Determine coordinate reference system from context (PLSS for township/range, UTM for coordinates, etc.)
6. If information is missing or unclear, use null for optional fields
7. Generate a meaningful parcel_id if not provided in the text
8. Return only valid JSON without any additional commentary

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