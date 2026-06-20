"""Tests for canonical feature-graph artifact refs."""

from __future__ import annotations

import pytest

from feature_graph.artifact_refs import (
    FeatureGraphArtifactRefError,
    build_feature_graph_artifact_ref,
    parse_feature_graph_artifact_ref,
    validate_artifact_id,
)


def test_build_and_parse_round_trip():
    ref = build_feature_graph_artifact_ref("compile", "compile_chain_001")
    artifact_type, artifact_id = parse_feature_graph_artifact_ref(ref)
    assert artifact_type == "compile"
    assert artifact_id == "compile_chain_001"


def test_unknown_artifact_type_fails():
    with pytest.raises(FeatureGraphArtifactRefError, match="feature_graph_artifact_type_unsupported"):
        build_feature_graph_artifact_ref("mapping", "x1")


def test_malformed_ref_fails():
    with pytest.raises(FeatureGraphArtifactRefError, match="feature_graph_artifact_ref_invalid"):
        parse_feature_graph_artifact_ref("feature_graph:unknown:x1")


def test_blank_artifact_id_fails():
    with pytest.raises(FeatureGraphArtifactRefError, match="feature_graph_artifact_id_invalid"):
        validate_artifact_id("   ")
