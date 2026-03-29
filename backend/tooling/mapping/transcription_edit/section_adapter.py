"""Section-preserving adapters for transcription edit loop v0."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import TranscriptDocumentV0, TranscriptSectionV0

_SECTION_SEPARATOR = "\n\n"


@dataclass(frozen=True)
class SectionSpan:
    section_id: str
    section_index: int
    start_char: int
    end_char: int


def normalize_transcript_payload_to_document(
    *,
    payload: Any,
    source_transcript_ref: str | None = None,
    source_transcript_hash: str | None = None,
) -> TranscriptDocumentV0:
    if isinstance(payload, str):
        sections = [TranscriptSectionV0(id="section_001", body=payload)]
        return TranscriptDocumentV0(
            source_transcript_ref=source_transcript_ref,
            source_transcript_hash=source_transcript_hash,
            sections=sections,
        )
    if not isinstance(payload, dict):
        raise ValueError("unsupported_transcript_payload")

    sections = payload.get("sections")
    if isinstance(sections, list):
        normalized: list[TranscriptSectionV0] = []
        for idx, raw_section in enumerate(sections):
            if not isinstance(raw_section, dict):
                continue
            section_id = str(raw_section.get("id") or f"section_{idx + 1:03d}")
            body = raw_section.get("body")
            if not isinstance(body, str):
                body = raw_section.get("text")
            if not isinstance(body, str):
                body = ""
            metadata = raw_section.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            normalized.append(TranscriptSectionV0(id=section_id, body=body, metadata=metadata))
        if normalized:
            return TranscriptDocumentV0(
                source_transcript_ref=source_transcript_ref,
                source_transcript_hash=source_transcript_hash,
                sections=normalized,
                metadata=(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}),
            )

    text = payload.get("text")
    if isinstance(text, str):
        return TranscriptDocumentV0(
            source_transcript_ref=source_transcript_ref,
            source_transcript_hash=source_transcript_hash,
            sections=[TranscriptSectionV0(id="section_001", body=text)],
            metadata=(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}),
        )

    raise ValueError("transcript_payload_missing_text")


def sections_to_text_with_index_map(
    sections: list[TranscriptSectionV0],
) -> tuple[str, list[SectionSpan]]:
    parts: list[str] = []
    spans: list[SectionSpan] = []
    cursor = 0
    for idx, section in enumerate(sections):
        if idx > 0:
            parts.append(_SECTION_SEPARATOR)
            cursor += len(_SECTION_SEPARATOR)
        body = section.body or ""
        start = cursor
        end = start + len(body)
        spans.append(
            SectionSpan(
                section_id=section.id,
                section_index=idx,
                start_char=start,
                end_char=end,
            )
        )
        parts.append(body)
        cursor = end
    return "".join(parts), spans


def locate_section_for_absolute_span(
    spans: list[SectionSpan],
    *,
    abs_start: int,
    abs_end: int,
) -> SectionSpan | None:
    for span in spans:
        if abs_start >= span.start_char and abs_end <= span.end_char:
            return span
    return None

