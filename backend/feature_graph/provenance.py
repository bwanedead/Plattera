"""
Feature Graph Provenance Models
================================

Models for tracking the provenance and evidence links for feature graph nodes and edges.
All citations must point to text spans and evidence links to ensure full traceability.

Design principles:
- Every assertion can be traced back to source evidence
- Text spans capture exact locations in source documents
- Citations link graph elements to their originating text
- Evidence references provide structured links to corpus documents
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, List


class TextSpan(BaseModel):
    """
    Precise location within a source text document.

    Represents a specific substring in a source document, identified by
    either character offsets or line/column positions.
    """
    document_id: str = Field(..., description="ID of source document (deed, plat, etc)")
    start_offset: Optional[int] = Field(None, description="Character offset start position (0-indexed)")
    end_offset: Optional[int] = Field(None, description="Character offset end position (exclusive)")
    start_line: Optional[int] = Field(None, description="Line number start (1-indexed)")
    start_col: Optional[int] = Field(None, description="Column start position (1-indexed)")
    end_line: Optional[int] = Field(None, description="Line number end (1-indexed)")
    end_col: Optional[int] = Field(None, description="Column end position (1-indexed)")
    text_snippet: Optional[str] = Field(None, description="The actual text content at this span (for human readability)")

    class Config:
        frozen = False


class EvidenceRef(BaseModel):
    """
    Structured reference to evidence in the corpus.

    Links to corpus documents, chunks, or semantic segments that provide
    supporting evidence for a feature or assertion.
    """
    corpus_doc_id: str = Field(..., description="Corpus document ID")
    chunk_id: Optional[str] = Field(None, description="Specific chunk ID within the document")
    segment_id: Optional[str] = Field(None, description="Semantic segment ID if applicable")
    evidence_type: str = Field("textual", description="Type of evidence: textual, visual, derived, etc")
    relevance_note: Optional[str] = Field(None, description="Brief note on why this evidence is relevant")

    class Config:
        frozen = False


class Citation(BaseModel):
    """
    Citation linking a feature graph element to its source evidence.

    Citations provide full traceability from IR nodes/edges back to the
    original source text and supporting evidence.
    """
    text_span: Optional[TextSpan] = Field(None, description="Exact text span in source document")
    evidence_refs: List[EvidenceRef] = Field(default_factory=list, description="Related evidence documents")
    citation_type: str = Field("direct", description="Citation type: direct, inferred, derived, etc")
    confidence_note: Optional[str] = Field(None, description="Note about citation quality (not a score)")

    class Config:
        frozen = False


class ProvenanceAttachment(BaseModel):
    """
    Provenance attachment for FeatureNode or FeatureEdge.

    This model is meant to be embedded in nodes/edges via a 'provenance' field.
    It groups all citation and evidence information for a single graph element.
    """
    citations: List[Citation] = Field(default_factory=list, description="All citations for this element")
    created_by: Optional[str] = Field(None, description="Agent/tool that created this element (LLM, parser, etc)")
    created_at: Optional[str] = Field(None, description="ISO timestamp of creation")
    lineage: List[str] = Field(default_factory=list, description="Parent artifact IDs (for derived features)")

    class Config:
        frozen = False
