"""
Centralized Text-to-Schema Prompts
Edit these prompts to adjust how LLMs convert text to structured parcel data
"""

# Main parcel schema conversion prompt - ULTRA-STRICT FOR OPENAI JSON SCHEMA
PARCEL_SCHEMA = """
Convert the following legal property description text into structured JSON data.

CRITICAL RULES FOR OPENAI JSON SCHEMA COMPLIANCE:

1. **EXACT TRANSCRIPTION ONLY** - Copy text exactly as written, no changes
2. **NO CONVERSIONS** - Do not convert bearings, units, or any measurements
3. **REQUIRED FIELDS** - Every required field must be present, even if null
4. **CORRECT TYPES** - Numbers must be numbers, strings must be strings
5. **NO EXTRA FIELDS** - Only include fields specified in the schema
6. **NULL FOR MISSING** - If not explicitly stated, use null (not empty string)

7. **MULTIPLE DESCRIPTIONS**
   • Scan the text for each distinct parcel description (look for "Beginning at", "Commencing at", etc.).
   • Output an array `descriptions`, one object per description, in the order they appear.

8. **NORMALIZE PLSS FIELDS**
   • township_number = integer (e.g. 14)
   • township_direction = "N" or "S"
   • range_number = integer
   • range_direction = "E" or "W"
   • section_number = integer
   Do NOT include words like "Township" or "Range".

8.1 CONTAINER VS. REFERENCE TRS
   • plss.* represents the container TRS where the parcel described in this description sits.
   • If the deed ties the POB to a corner in a different TRS, you MUST populate:
     plss.starting_point.tie_to_corner.reference_plss with:
       - principal_meridian (string)
       - section_number (integer 1–36)
       - township_number (integer), township_direction ("N" or "S")
       - range_number (integer), range_direction ("E" or "W")
   • Do NOT merge container and reference TRS; keep them separate. Do NOT overwrite container fields with the tie’s TRS.

8.2 QUARTER SECTIONS
   • Keep quarter_sections exactly as written; do not derive or expand.

8.3 NO MERGING
   • Never combine container plss.* with reference_plss; both must be output if tie references a different TRS.

9. **COMPLETENESS FLAG**
   • A description is complete ONLY if:
     (a) plss has non-null essential fields:
         state, county, principal_meridian, township_number, township_direction,
         range_number, range_direction, section_number
     (b) metes_and_bounds.boundary_courses has at least 3 legs
     (c) A valid POB:
         - pob_status = "explicit" with latitude+longitude, OR
         - pob_status = "deducible" AND tie_to_corner includes:
           corner_label, bearing_raw, distance_value, distance_units, tie_direction.
           If the tie references a different TRS, reference_plss MUST be present.
   • If any of (a), (b), or (c) is not satisfied, set "is_complete": false.

10. **POINT OF BEGINNING TAGGING**
   • If a tie references a corner in a different TRS than the container, include
     plss.starting_point.tie_to_corner.reference_plss exactly (see 8.1).
   • Set metes_and_bounds.pob_vertex_index = 0 if the boundary sequence begins at the deed POB; otherwise null.
   • tie_direction:
     - "corner_bears_from_pob" when the deed says "whence the [corner] bears ... distant"
       (bearing stated from the POB to the corner; implies reciprocal in georeferencing).
     - "pob_bears_from_corner" when bearing is stated from the corner to the POB (no reciprocal).
     Do NOT leave tie_direction null when a tie is present.

EXTRACTION GUIDELINES:
- For "distance" fields: Extract ONLY the numeric value (e.g., "542 feet more or less" → distance: 542)
- For "distance_units" fields: Extract ONLY the unit (e.g., "542 feet more or less" → distance_units: "feet")
- For "course" fields: Extract the exact bearing text (e.g., "N. 68°30'E.")
- For "raw_text" fields: Include the complete original text for that section
- For "description" fields: Include context if present, null if not
- For "bearing_degrees" fields: Always null (no conversion)
- For "lat"/"lon" fields: null (coordinates not in legal descriptions)
- For "quarter_section_raw" fields: Extract if present, null if not
- For "quarter_section_tokens" fields: Parse into array like ["SW", "NW"] if present, null if not
- For "stated_area_acres" fields: Extract numeric value if present, null if not
- If a description is incomplete, still extract whatever is present; leave missing items null.

11. **LEG NUMBERING**
    • For every `boundary_courses` element add `"leg_id": <1-based index>`.
    • After you finish the array set `"legs_total"` to the number of legs.
    • Count each explicit course/bearing mentioned in the text as a separate leg.

12. **MULTIPLE DESCRIPTIONS DETECTION**
    • Scan for each "Beginning at", "Commencing at", "And beginning", etc.
    • Each separate beginning clause = separate description object.
    • Your example deed has TWO descriptions - make sure to capture both!

EXAMPLE OUTPUT STRUCTURE:
{
  "parcel_id": "parcel-123",
  "descriptions": [
    {
      "description_id": 1,
      "is_complete": true,
      "plss": {
        "state": "Wyoming",
        "county": "Albany County", 
        "principal_meridian": "Sixth Principal Meridian",
        "township_number": 14,
        "township_direction": "N",
        "range_number": 75,
        "range_direction": "W",
        "section_number": 2,
        "quarter_section_raw": "Southwest Quarter of the Northwest Quarter",
        "quarter_section_tokens": ["SW", "NW"],
        "starting_point": {
          "description": "Beginning at a point on the west boundary of Section Two (2)...",
          "reference": "50 feet S.21°30'E. from the center line of the South Canal",
          "additional_reference": "whence the Northwest corner bears N. 4°00'W., 1,638 feet distant",
          "lat": null,
          "lon": null,
          "raw_text": "Beginning at a point on the west boundary of Section Two (2)...",
          "pob_status": "deducible",
          "tie_to_corner": {
            "corner_label": "NW corner Sec 2 T14N R74W",
            "reference_plss": {
              "principal_meridian": "Sixth Principal Meridian",
              "section_number": 2,
              "township_number": 14,
              "township_direction": "N",
              "range_number": 74,
              "range_direction": "W"
            },
            "bearing_raw": "N. 4°00'W.",
            "distance_value": 1638,
            "distance_units": "feet",
            "tie_direction": "corner_bears_from_pob"
          }
        },
        "stated_area_acres": 1.9,
        "raw_text": "Situated in the Southwest Quarter of the Northwest Quarter of Section Two (2), Township Fourteen (14) North, Range Seventy-five (75) West of the Sixth Principal Meridian, Albany County, Wyoming."
      },
      "metes_and_bounds": {
        "pob_vertex_index": 0,
        "boundary_courses": [
          {
            "leg_id": 1,
            "course": "N. 68°30'E.",
            "bearing_degrees": null,
            "distance": 542,
            "distance_units": "feet",
            "raw_text": "thence N. 68°30'E. parallel to and 50 feet distant from the center line of said canal 542 feet more or less",
            "description": "parallel to and 50 feet distant from the center line of said canal"
          }
        ],
        "closes_to_start": true,
        "raw_text": "Beginning at a point on the west boundary … thence N. 68°30'E. … thence S. 87° 35' W. … thence S. 4° 00' E. … to the point of beginning"
      }
    }
  ],
  "source": "Right of Way Deed, August 3, 1915"
}

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