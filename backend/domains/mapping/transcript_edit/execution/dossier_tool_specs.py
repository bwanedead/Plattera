"""Dossier-mode request contracts for the shared transcript-edit capabilities."""

from __future__ import annotations

from dataclasses import replace

from .tool_specs import SemanticToolSpec, build_transcript_edit_tool_specs

_QUALIFIED_EXAMPLE_PREFIX = "dossier_segment:segment-01:run:tx-01:"


def build_dossier_transcript_edit_tool_specs() -> tuple[SemanticToolSpec, ...]:
    """Apply the dossier transport delta without copying common tool doctrine."""
    return tuple(_project_dossier_contract(spec) for spec in build_transcript_edit_tool_specs())


def _project_dossier_contract(spec: SemanticToolSpec) -> SemanticToolSpec:
    if spec.tool_id == "hydrate_artifact_refs":
        return replace(
            spec,
            purpose=(
                "Load full content for dossier-qualified artifact refs from the bound topology. "
                "Each ref identifies its segment and transcription run; comparison, reconciliation, "
                "and run selection remain the LLM's work."
            ),
            expected_request_shape=(
                "ref_ids: required non-empty array of dossier-qualified ref strings in the form "
                "dossier_segment:<segment_id>:run:<transcription_id>:<leaf_ref>. "
                "max_refs: optional integer cap (default 8, max 32)."
            ),
            expected_request_json_shape=_with_property_description(
                spec.expected_request_json_shape,
                "ref_ids",
                "Dossier-qualified ref IDs from the bound startup inventory or prior tool results.",
            ),
            example_request={
                "ref_ids": [
                    f"{_QUALIFIED_EXAMPLE_PREFIX}t0:raw:pass_1",
                    f"{_QUALIFIED_EXAMPLE_PREFIX}image:assoc:tx-01:original",
                ],
                "max_refs": 4,
            },
            expected_result_shape=(
                "outputs.results preserves request order and returns dossier-qualified ref_id, "
                "segment_id, transcription_id, kind, and bounded kind-specific semantic content. "
                "Source and derived images also return model-visible image evidence. "
                "Host paths and binary fields are not projected in ordinary result rows. "
                "outputs.errors reports per-ref failures; outputs.hydrated_count is exact."
            ),
        )
    if spec.tool_id == "transform_artifact":
        return replace(
            spec,
            purpose=(
                "In dossier mode, the source ref and every returned persistent ref are "
                "dossier-qualified to one segment/transcription lineage. "
                + spec.purpose
            ),
            expected_request_shape=(
                "ref_id must be a dossier-qualified source or derived image ref from the bound "
                "topology. "
                + spec.expected_request_shape
            ),
            expected_request_json_shape=_with_property_description(
                spec.expected_request_json_shape,
                "ref_id",
                "Dossier-qualified source or derived image ref from the bound topology.",
            ),
            example_request={
                "ref_id": f"{_QUALIFIED_EXAMPLE_PREFIX}image:assoc:tx-01:original",
                "sub_action": "crop",
                "params": {"box_norm": [0.1, 0.2, 0.8, 0.6]},
            },
            expected_result_shape=(
                spec.expected_result_shape
                + " Dossier mode qualifies derived_ref_id, artifact_refs, and image-evidence "
                "identity to the source segment/transcription lineage."
            ),
        )
    if spec.tool_id == "save_workspace_artifact":
        return _dossier_save_spec(spec)
    if spec.tool_id == "copy_forward_save_workspace_artifact":
        return _dossier_copy_forward_spec(spec)
    if spec.tool_id == "publish_workspace_artifact":
        return _dossier_publish_spec(spec)
    return spec


def _dossier_save_spec(spec: SemanticToolSpec) -> SemanticToolSpec:
    return replace(
        spec,
        purpose=(
            spec.purpose
            + " In dossier mode, save into exactly one segment/transcription lineage. "
            "Use a dossier-qualified target_ref for the first save; later saves may use the "
            "exact qualified base_revision_ref. Deterministic code validates lineage but never "
            "chooses a segment or transcription run."
        ),
        expected_request_shape=(
            "transcript_text XOR draft_payload: authored content for one segment. "
            "target_ref: dossier-qualified ref identifying the intended segment/transcription "
            "lineage; required for a first save and optional when base_revision_ref identifies "
            "the same lineage. base_revision_ref: optional dossier-qualified exact working "
            "revision; when both refs are present they must resolve to the same lineage. "
            "evidence_refs: optional validated refs grounding this segment revision. "
            "rationale: optional explanation. The domain branch owns the saved payload lanes."
        ),
        expected_request_json_shape={
            "type": "object",
            "properties": {
                "transcript_text": {
                    "type": ["string", "null"],
                    "description": "Full source-faithful transcript text for this segment.",
                },
                "draft_payload": {
                    "type": ["object", "null"],
                    "description": "Structured segment draft payload (XOR with transcript_text).",
                },
                "target_ref": {
                    "type": "string",
                    "description": "Dossier-qualified ref identifying the target segment/run lineage.",
                },
                "base_revision_ref": {
                    "type": ["string", "null"],
                    "description": "Dossier-qualified exact working revision this save continues.",
                },
                "evidence_refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Validated refs grounding this segment revision.",
                },
                "rationale": {
                    "type": ["string", "null"],
                    "description": "Brief explanation of what changed and why.",
                },
            },
            "anyOf": [
                {"required": ["target_ref"]},
                {"required": ["base_revision_ref"]},
            ],
            "additionalProperties": False,
        },
        example_request={
            "target_ref": f"{_QUALIFIED_EXAMPLE_PREFIX}t0:raw:pass_1",
            "draft_payload": {
                "source_transcript_verbatim": "Beginning at the marked corner...",
                "normalized_or_mapping_transcript": "Beginning at the marked corner...",
                "issues": [],
                "evidence_refs": [
                    f"{_QUALIFIED_EXAMPLE_PREFIX}image:assoc:tx-01:original"
                ],
            },
            "evidence_refs": [
                f"{_QUALIFIED_EXAMPLE_PREFIX}image:assoc:tx-01:original"
            ],
            "rationale": "Saved the reviewed transcript for this segment.",
        },
        expected_result_shape=(
            "artifact_refs and outputs use dossier-qualified working aggregate and exact revision "
            "refs, with segment_id and transcription_id identifying the saved lineage. "
            "No other segment is mutated."
        ),
    )


def _dossier_copy_forward_spec(spec: SemanticToolSpec) -> SemanticToolSpec:
    return replace(
        spec,
        purpose=(
            spec.purpose
            + " In dossier mode, base_ref must be a dossier-qualified exact working revision. "
            "An optional target_ref may only confirm the same segment/transcription lineage."
        ),
        expected_request_shape=(
            "base_ref: required dossier-qualified exact working revision. "
            "target_ref: optional dossier-qualified ref that must resolve to the same lineage. "
            "copy_forward_paths: required non-empty payload.* paths copied exactly. "
            "set_paths: required payload.* path-to-authored-value object with no overlap. "
            "evidence_refs: optional validated grounding refs. rationale: optional explanation."
        ),
        expected_request_json_shape={
            "type": "object",
            "required": ["base_ref", "copy_forward_paths", "set_paths"],
            "properties": {
                "base_ref": {
                    "type": "string",
                    "description": "Dossier-qualified exact working revision to continue.",
                },
                "target_ref": {
                    "type": ["string", "null"],
                    "description": "Optional ref confirming the same segment/run lineage.",
                },
                "copy_forward_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "Non-overlapping payload.* paths copied exactly.",
                },
                "set_paths": {
                    "type": "object",
                    "description": "Non-overlapping payload.* paths and authored replacement values.",
                },
                "evidence_refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Validated refs grounding this segment revision.",
                },
                "rationale": {
                    "type": ["string", "null"],
                    "description": "Brief explanation of what changed and why.",
                },
            },
            "additionalProperties": False,
        },
        example_request={
            "base_ref": f"{_QUALIFIED_EXAMPLE_PREFIX}transcript_edit:working:rev:0001",
            "copy_forward_paths": [
                "payload.source_transcript_verbatim",
                "payload.normalized_or_mapping_transcript",
            ],
            "set_paths": {"payload.issues": []},
            "rationale": "Reconciled segment metadata; transcript lanes are unchanged.",
        },
        expected_result_shape=(
            "Same dossier-qualified save result shape as save_workspace_artifact. "
            "The new exact revision remains in the base segment/transcription lineage."
        ),
    )


def _dossier_publish_spec(spec: SemanticToolSpec) -> SemanticToolSpec:
    return replace(
        spec,
        purpose=(
            "Publish one coherent dossier transcript from explicit agent-selected segment revisions. "
            "Pass exactly one dossier-qualified exact working revision per topology segment. "
            "No deterministic best/longest/consensus or latest-revision selection is performed."
        ),
        expected_request_shape=(
            "source_revision_refs: required array containing exactly one dossier-qualified "
            "transcript_edit:working:rev:NNNN ref per topology segment. "
            "The singular source_revision_ref field is not accepted."
        ),
        expected_request_json_shape={
            "type": "object",
            "required": ["source_revision_refs"],
            "properties": {
                "source_revision_refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "One chosen exact qualified working revision per topology segment.",
                },
            },
            "additionalProperties": False,
        },
        example_request={
            "source_revision_refs": [
                f"{_QUALIFIED_EXAMPLE_PREFIX}transcript_edit:working:rev:0003",
                "dossier_segment:segment-02:run:tx-02:"
                "transcript_edit:working:rev:0002",
            ]
        },
        expected_result_shape=(
            "artifact_refs include transcript_edit:output and the immutable "
            "transcript_edit:dossier_output:sha256:<fingerprint> ref. outputs report the topology "
            "fingerprint, selected segment/revision count, evidence count, publication timestamp, "
            "and idempotent replay/recovery posture."
        ),
    )


def _with_property_description(
    schema: dict[str, object],
    property_name: str,
    description: str,
) -> dict[str, object]:
    """Copy one JSON-schema property before applying a mode-specific description."""
    projected = dict(schema)
    raw_properties = schema.get("properties")
    properties = dict(raw_properties) if isinstance(raw_properties, dict) else {}
    raw_property = properties.get(property_name)
    property_schema = dict(raw_property) if isinstance(raw_property, dict) else {}
    property_schema["description"] = description
    properties[property_name] = property_schema
    projected["properties"] = properties
    return projected
