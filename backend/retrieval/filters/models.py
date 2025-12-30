from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from corpus.models import CorpusView


@dataclass
class RetrievalFilters:
    """
    Standard query scoping for retrieval.

    Keep this stable so agents/UI can evolve without changing lane internals.
    """

    view: Optional[CorpusView] = None
    dossier_id: Optional[str] = None
    transcription_id: Optional[str] = None
    artifact_type: Optional[str] = None  # schema/georef/...
    since_iso: Optional[str] = None
    until_iso: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


