"""
Centralized Text-to-Schema Prompts
Edit these prompts to adjust how LLMs convert text to structured data
"""

# Main parcel schema conversion prompt
PARCEL_SCHEMA = """
Convert the following legal property description text into a structured JSON format.

The output should follow this schema structure:
{
  "parcel_id": "string",
  "legal_description": "string", 
  "property_type": "string",
  "location": {
    "address": "string",
    "city": "string",
    "county": "string", 
    "state": "string"
  },
  "boundaries": {
    "north": "string",
    "south": "string", 
    "east": "string",
    "west": "string"
  },
  "measurements": {
    "acreage": "number",
    "square_feet": "number",
    "frontage": "string"
  },
  "parties": {
    "grantor": "string",
    "grantee": "string"
  },
  "dates": {
    "deed_date": "string",
    "recording_date": "string"
  },
  "references": {
    "deed_book": "string",
    "page": "string",
    "prior_deeds": ["string"]
  }
}

Extract information from the text and format it according to this schema.
If information is not available, use null values.
Return only valid JSON without any additional text or commentary.

Legal Description Text:
"""

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