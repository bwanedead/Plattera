"""
Tests for Feature Graph Provenance Models
==========================================

Tests for provenance, citation, and evidence tracking models.
Validates JSON round-trip serialization and attachment to nodes/edges.
"""

import pytest
import json
from .provenance import TextSpan, EvidenceRef, Citation, ProvenanceAttachment
from .models import FeatureNode, FeatureEdge, FeatureKind


class TestTextSpan:
    """Tests for TextSpan model."""

    def test_text_span_with_offsets(self):
        """Test TextSpan with character offsets."""
        span = TextSpan(
            document_id="deed_123",
            start_offset=100,
            end_offset=150,
            text_snippet="North 45 degrees East for 100 feet"
        )
        assert span.document_id == "deed_123"
        assert span.start_offset == 100
        assert span.end_offset == 150
        assert span.text_snippet == "North 45 degrees East for 100 feet"

    def test_text_span_with_line_col(self):
        """Test TextSpan with line/column positions."""
        span = TextSpan(
            document_id="deed_456",
            start_line=10,
            start_col=5,
            end_line=10,
            end_col=42,
            text_snippet="thence North 45 degrees East"
        )
        assert span.start_line == 10
        assert span.start_col == 5
        assert span.end_line == 10
        assert span.end_col == 42

    def test_text_span_json_roundtrip(self):
        """Test TextSpan JSON serialization round-trip."""
        span = TextSpan(
            document_id="deed_789",
            start_offset=200,
            end_offset=250,
            start_line=5,
            start_col=1,
            end_line=6,
            end_col=10,
            text_snippet="beginning at the northeast corner"
        )
        json_str = span.model_dump_json()
        roundtrip = TextSpan.model_validate_json(json_str)
        assert roundtrip.document_id == span.document_id
        assert roundtrip.start_offset == span.start_offset
        assert roundtrip.end_offset == span.end_offset
        assert roundtrip.text_snippet == span.text_snippet


class TestEvidenceRef:
    """Tests for EvidenceRef model."""

    def test_evidence_ref_basic(self):
        """Test basic EvidenceRef creation."""
        evidence = EvidenceRef(
            corpus_doc_id="doc_001",
            chunk_id="chunk_42",
            evidence_type="textual",
            relevance_note="Contains bearing information"
        )
        assert evidence.corpus_doc_id == "doc_001"
        assert evidence.chunk_id == "chunk_42"
        assert evidence.evidence_type == "textual"

    def test_evidence_ref_with_segment(self):
        """Test EvidenceRef with semantic segment ID."""
        evidence = EvidenceRef(
            corpus_doc_id="doc_002",
            segment_id="seg_traverse_1",
            evidence_type="derived",
            relevance_note="Parsed traverse operation"
        )
        assert evidence.segment_id == "seg_traverse_1"
        assert evidence.evidence_type == "derived"

    def test_evidence_ref_json_roundtrip(self):
        """Test EvidenceRef JSON round-trip."""
        evidence = EvidenceRef(
            corpus_doc_id="doc_003",
            chunk_id="chunk_10",
            segment_id="seg_5",
            evidence_type="visual",
            relevance_note="Diagram showing parcel boundary"
        )
        json_str = evidence.model_dump_json()
        roundtrip = EvidenceRef.model_validate_json(json_str)
        assert roundtrip.corpus_doc_id == evidence.corpus_doc_id
        assert roundtrip.chunk_id == evidence.chunk_id
        assert roundtrip.segment_id == evidence.segment_id


class TestCitation:
    """Tests for Citation model."""

    def test_citation_with_text_span(self):
        """Test Citation with text span."""
        text_span = TextSpan(
            document_id="deed_100",
            start_offset=50,
            end_offset=100,
            text_snippet="North 0 degrees 15 minutes East"
        )
        citation = Citation(
            text_span=text_span,
            citation_type="direct"
        )
        assert citation.text_span is not None
        assert citation.text_span.document_id == "deed_100"
        assert citation.citation_type == "direct"

    def test_citation_with_evidence_refs(self):
        """Test Citation with multiple evidence references."""
        evidence1 = EvidenceRef(
            corpus_doc_id="doc_010",
            evidence_type="textual"
        )
        evidence2 = EvidenceRef(
            corpus_doc_id="doc_011",
            evidence_type="visual"
        )
        citation = Citation(
            evidence_refs=[evidence1, evidence2],
            citation_type="inferred",
            confidence_note="Inferred from context and diagram"
        )
        assert len(citation.evidence_refs) == 2
        assert citation.citation_type == "inferred"
        assert citation.confidence_note is not None

    def test_citation_json_roundtrip(self):
        """Test Citation JSON round-trip with full data."""
        text_span = TextSpan(
            document_id="deed_200",
            start_offset=300,
            end_offset=350,
            text_snippet="along the north boundary"
        )
        evidence = EvidenceRef(
            corpus_doc_id="doc_020",
            chunk_id="chunk_5",
            evidence_type="textual"
        )
        citation = Citation(
            text_span=text_span,
            evidence_refs=[evidence],
            citation_type="direct",
            confidence_note="High confidence direct quote"
        )
        json_str = citation.model_dump_json()
        roundtrip = Citation.model_validate_json(json_str)
        assert roundtrip.text_span.document_id == "deed_200"
        assert len(roundtrip.evidence_refs) == 1
        assert roundtrip.citation_type == "direct"


class TestProvenanceAttachment:
    """Tests for ProvenanceAttachment model."""

    def test_provenance_attachment_basic(self):
        """Test basic ProvenanceAttachment creation."""
        citation = Citation(citation_type="direct")
        prov = ProvenanceAttachment(
            citations=[citation],
            created_by="llm_parser_v1",
            created_at="2026-02-04T10:00:00Z"
        )
        assert len(prov.citations) == 1
        assert prov.created_by == "llm_parser_v1"
        assert prov.created_at == "2026-02-04T10:00:00Z"

    def test_provenance_attachment_with_lineage(self):
        """Test ProvenanceAttachment with lineage tracking."""
        prov = ProvenanceAttachment(
            citations=[],
            created_by="derive_compiler",
            lineage=["artifact_001", "artifact_002"]
        )
        assert len(prov.lineage) == 2
        assert "artifact_001" in prov.lineage

    def test_provenance_attachment_json_roundtrip(self):
        """Test ProvenanceAttachment JSON round-trip."""
        text_span = TextSpan(
            document_id="deed_300",
            start_offset=0,
            end_offset=50,
            text_snippet="Commencing at the point of beginning"
        )
        citation = Citation(
            text_span=text_span,
            citation_type="direct"
        )
        prov = ProvenanceAttachment(
            citations=[citation],
            created_by="ocr_parser",
            created_at="2026-02-04T12:00:00Z",
            lineage=["source_image_001"]
        )
        json_str = prov.model_dump_json()
        roundtrip = ProvenanceAttachment.model_validate_json(json_str)
        assert len(roundtrip.citations) == 1
        assert roundtrip.created_by == "ocr_parser"
        assert len(roundtrip.lineage) == 1


class TestProvenanceAttachedToNodes:
    """Tests for provenance attached to FeatureNode."""

    def test_node_with_provenance(self):
        """Test FeatureNode with provenance attachment."""
        text_span = TextSpan(
            document_id="deed_400",
            start_offset=100,
            end_offset=200,
            text_snippet="point A at the northeast corner"
        )
        citation = Citation(text_span=text_span, citation_type="direct")
        prov = ProvenanceAttachment(
            citations=[citation],
            created_by="deed_parser"
        )

        node = FeatureNode(
            id="point_a",
            kind=FeatureKind.POINT,
            label="Point A",
            geometry={"type": "Point", "coordinates": [0.0, 0.0]},
            provenance=prov
        )

        assert node.provenance is not None
        assert len(node.provenance.citations) == 1
        assert node.provenance.created_by == "deed_parser"

    def test_node_with_provenance_json_roundtrip(self):
        """Test FeatureNode with provenance JSON round-trip."""
        text_span = TextSpan(
            document_id="deed_500",
            start_offset=50,
            end_offset=150,
            text_snippet="traverse north 100 feet"
        )
        evidence = EvidenceRef(
            corpus_doc_id="doc_030",
            evidence_type="textual"
        )
        citation = Citation(
            text_span=text_span,
            evidence_refs=[evidence],
            citation_type="direct"
        )
        prov = ProvenanceAttachment(
            citations=[citation],
            created_by="llm_extractor",
            created_at="2026-02-04T14:00:00Z"
        )

        node = FeatureNode(
            id="traverse_1",
            kind=FeatureKind.CURVE,
            label="North Traverse",
            provenance=prov
        )

        # Serialize to JSON
        json_str = node.model_dump_json()
        # Deserialize back
        roundtrip = FeatureNode.model_validate_json(json_str)

        assert roundtrip.id == "traverse_1"
        assert roundtrip.provenance is not None
        assert roundtrip.provenance["created_by"] == "llm_extractor"
        assert len(roundtrip.provenance["citations"]) == 1


class TestProvenanceAttachedToEdges:
    """Tests for provenance attached to FeatureEdge."""

    def test_edge_with_provenance(self):
        """Test FeatureEdge with provenance attachment."""
        citation = Citation(
            citation_type="inferred",
            confidence_note="Sequencing inferred from text order"
        )
        prov = ProvenanceAttachment(
            citations=[citation],
            created_by="sequence_analyzer"
        )

        edge = FeatureEdge(
            source_id="step_1",
            target_id="step_2",
            edge_type="next_step",
            label="Sequential step",
            provenance=prov
        )

        assert edge.provenance is not None
        assert edge.provenance.created_by == "sequence_analyzer"

    def test_edge_with_provenance_json_roundtrip(self):
        """Test FeatureEdge with provenance JSON round-trip."""
        text_span = TextSpan(
            document_id="deed_600",
            start_offset=200,
            end_offset=220,
            text_snippet="thence continuing"
        )
        citation = Citation(text_span=text_span, citation_type="direct")
        prov = ProvenanceAttachment(citations=[citation])

        edge = FeatureEdge(
            source_id="curve_1",
            target_id="curve_2",
            edge_type="depends_on",
            provenance=prov
        )

        json_str = edge.model_dump_json()
        roundtrip = FeatureEdge.model_validate_json(json_str)

        assert roundtrip.source_id == "curve_1"
        assert roundtrip.provenance is not None
        assert len(roundtrip.provenance["citations"]) == 1


class TestComplexProvenanceScenarios:
    """Tests for complex provenance scenarios."""

    def test_multiple_citations_on_node(self):
        """Test node with multiple citations from different sources."""
        citation1 = Citation(
            text_span=TextSpan(
                document_id="deed_700",
                start_offset=0,
                end_offset=50,
                text_snippet="beginning at monument A"
            ),
            citation_type="direct"
        )
        citation2 = Citation(
            text_span=TextSpan(
                document_id="survey_700",
                start_offset=100,
                end_offset=150,
                text_snippet="point A marked by iron pin"
            ),
            citation_type="corroborating"
        )
        prov = ProvenanceAttachment(
            citations=[citation1, citation2],
            created_by="multi_source_merger"
        )

        node = FeatureNode(
            id="monument_a",
            kind=FeatureKind.POINT,
            provenance=prov
        )

        json_str = node.model_dump_json()
        roundtrip = FeatureNode.model_validate_json(json_str)
        assert len(roundtrip.provenance["citations"]) == 2

    def test_provenance_with_empty_citations(self):
        """Test provenance with no citations (derived feature)."""
        prov = ProvenanceAttachment(
            citations=[],
            created_by="geometric_compiler",
            created_at="2026-02-04T16:00:00Z",
            lineage=["ir_artifact_123", "compile_artifact_456"]
        )

        node = FeatureNode(
            id="derived_region",
            kind=FeatureKind.REGION,
            provenance=prov
        )

        assert len(node.provenance.citations) == 0
        assert len(node.provenance.lineage) == 2

    def test_node_without_provenance(self):
        """Test that nodes can exist without provenance (optional field)."""
        node = FeatureNode(
            id="simple_point",
            kind=FeatureKind.POINT,
            geometry={"type": "Point", "coordinates": [1.0, 2.0]}
        )
        assert node.provenance is None

        json_str = node.model_dump_json()
        roundtrip = FeatureNode.model_validate_json(json_str)
        assert roundtrip.provenance is None
