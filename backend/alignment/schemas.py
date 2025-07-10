from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class AlignmentRequest(BaseModel):
    """
    Defines the shape of the request body for the /align-drafts endpoint.
    It expects a list of drafts, where each draft is a dictionary.
    This uses Dict[str, Any] to flexibly handle the legacy JSON format
    that comes from the frontend.
    """
    drafts: List[Dict[str, Any]]
