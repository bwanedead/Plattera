"""
Centralized Text-to-Schema Prompts
Edit these prompts to adjust how LLMs convert text to structured parcel data
"""

# Main parcel schema conversion prompt - EXACT TRANSCRIPTION FOR PROGRAMMATIC USE
PARCEL_SCHEMA = """
Convert the following legal property description text into structured JSON data following the parcel schema.

CRITICAL RULE: TRANSCRIBE EXACTLY - NO CONVERSIONS
- Extract ONLY the exact text as written in the legal description
- Do NOT convert bearings to degrees
- Do NOT convert units
- Do NOT calculate or compute anything
- Do NOT infer missing information
- If something is not explicitly stated, use null

Return the data in this exact structure:

{
  "parcel_id": "string - unique identifier for this parcel",
  "plss_description": {
    "state": "string - state name (e.g., 'Wyoming')",
    "county": "string - county name (e.g., 'Albany County')", 
    "principal_meridian": "string - principal meridian (e.g., 'Sixth Principal Meridian')",
    "township": "string - township exactly as written (e.g., 'Township Fourteen (14) North')",
    "range": "string - range exactly as written (e.g., 'Range Seventy-five (75) West')", 
    "section": "string - section exactly as written (e.g., 'Section Two (2)')",
    "quarter_section": "string or null - quarter section exactly as written (e.g., 'Southwest Quarter of the Northwest Quarter')",
    "starting_point": {
      "description": "string - starting point exactly as written",
      "reference": "string or null - primary reference exactly as written (e.g., '50 feet S.21°30'E from center line of South Canal')",
      "additional_reference": "string or null - secondary reference exactly as written (e.g., 'whence the Northwest corner bears N. 4°00'W., 1,638 feet distant')",
      "lat": "number or null - latitude only if stated in deed",
      "lon": "number or null - longitude only if stated in deed",
      "raw_text": "string - the full clause about POB from deed"
    },
    "stated_area_acres": "number or null - area in acres only if given in deed",
    "raw_text": "string - all PLSS description text as in deed"
  },
  "metes_and_bounds": {
    "boundary_courses": [
      {
        "course": "string - course exactly as written (e.g., 'N. 68°30'E.')",
        "bearing_degrees": null - DO NOT CONVERT, leave as null,
        "distance": "number - distance value as stated",
        "distance_units": "string - units exactly as written (e.g., 'feet')",
        "raw_text": "string - exact leg text from deed",
        "description": "string or null - context exactly as written (e.g., 'parallel to and 50 feet distant from center line')",
        "confidence": "number or null - extraction confidence (0-1), optional"
      }
    ],
    "closes_to_start": "boolean - whether description closes back to starting point",
    "raw_text": "string - full legal boundary text from deed"
  },
  "source": "string or null - deed reference/citation if stated"
}

EXTRACTION RULES:
1. **Exact Transcription**: Copy text exactly as written, no changes
2. **No Conversions**: Do not convert bearings, units, or any measurements
3. **Required Fields**: state, county, principal_meridian, township, range, section are required
4. **Starting Point**: Extract all reference information for the Point of Beginning
5. **Boundary Courses**: Extract each course with exact bearing, distance, and units
6. **Raw Text Everywhere**: Include exact original text in raw_text fields
7. **Null for Missing**: Use null for anything not explicitly stated
8. **No Inferences**: Do not guess, calculate, or infer anything

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