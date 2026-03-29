"""Deterministic validator scaffold for transcription edit loop v0."""

from __future__ import annotations

import re
from typing import Iterable

from .contracts import TranscriptDocumentV0, ValidatorFindingV0, ValidatorReportV0, transcript_text_hash
from .section_adapter import sections_to_text_with_index_map

_BEARING_PATTERN = re.compile(
    r"\b[NS]\.?\s*\d{1,3}(?:\s*°\s*\d{1,2}(?:\s*['’]\s*\d{1,2}(?:\.\d+)?)?(?:\s*['’])?)?"
    r"\s*(?:[EW]\.?|east|west)\b"
    r"|\b[NS]\s*\d{1,2}(?:\.\d+)?\s*[EW]\b",
    re.IGNORECASE,
)
_DISTANCE_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s*(?:ft|feet|chains|ch)\b", re.IGNORECASE)
_PLSS_TOKEN_PATTERN = re.compile(
    r"\b(T(?:ownship)?\s*\d+\s*[NS]|R(?:ange)?\s*\d+\s*[EW]|Sec(?:tion)?\s*\d+)\b",
    re.IGNORECASE,
)
_PLSS_PAREN_PATTERN = re.compile(
    r"\b(?P<kind>township|range|section)\b[^()]{0,60}\((?P<num>\d{1,3})\)\s*(?P<dir>north|south|east|west)?",
    re.IGNORECASE,
)


def run_validators(*, document: TranscriptDocumentV0, source_transcript_ref: str) -> ValidatorReportV0:
    text, spans = sections_to_text_with_index_map(document.sections)
    findings: list[ValidatorFindingV0] = []
    findings.extend(_bearing_findings(text=text, spans=spans))
    findings.extend(_distance_findings(text=text, spans=spans))
    findings.extend(_plss_consistency_findings(text=text))
    findings.extend(_call_chain_findings(text=text))

    summary = {
        "total": len(findings),
        "errors": sum(1 for finding in findings if finding.severity == "error"),
        "warnings": sum(1 for finding in findings if finding.severity == "warning"),
        "infos": sum(1 for finding in findings if finding.severity == "info"),
    }
    return ValidatorReportV0(
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=transcript_text_hash(text),
        findings=findings,
        summary=summary,
    )


def _bearing_findings(*, text: str, spans: list) -> Iterable[ValidatorFindingV0]:
    if not text.strip():
        return []
    findings: list[ValidatorFindingV0] = []
    if "thence" in text.lower() and not _BEARING_PATTERN.search(text):
        findings.append(
            ValidatorFindingV0(
                finding_id="bearing_missing_001",
                finding_type="bearing_parse",
                severity="warning",
                message="No canonical bearings detected despite call-chain language.",
            )
        )
    return findings


def _distance_findings(*, text: str, spans: list) -> Iterable[ValidatorFindingV0]:
    findings: list[ValidatorFindingV0] = []
    if "thence" in text.lower() and not _DISTANCE_PATTERN.search(text):
        findings.append(
            ValidatorFindingV0(
                finding_id="distance_missing_001",
                finding_type="numeric_unit_sanity",
                severity="warning",
                message="No distance units detected in metes-and-bounds style text.",
            )
        )
    return findings


def _plss_consistency_findings(*, text: str) -> Iterable[ValidatorFindingV0]:
    findings: list[ValidatorFindingV0] = []
    normalized: list[str] = []
    tokens = _PLSS_TOKEN_PATTERN.findall(text)
    normalized.extend([re.sub(r"\s+", "", token.lower()) for token in tokens])
    for match in _PLSS_PAREN_PATTERN.finditer(text):
        kind = str(match.group("kind") or "").lower()
        num = str(match.group("num") or "").lower()
        direction = str(match.group("dir") or "").lower()
        if kind == "township":
            suffix = "n" if direction.startswith("n") else ("s" if direction.startswith("s") else "")
            normalized.append(f"t{num}{suffix}")
        elif kind == "range":
            suffix = "e" if direction.startswith("e") else ("w" if direction.startswith("w") else "")
            normalized.append(f"r{num}{suffix}")
        elif kind == "section":
            normalized.append(f"sec{num}")
    townships = sorted({token for token in normalized if token.startswith("t")})
    ranges = sorted({token for token in normalized if token.startswith("r")})
    sections = sorted({token for token in normalized if token.startswith("sec")})

    if len(townships) > 1:
        findings.append(
            ValidatorFindingV0(
                finding_id="plss_township_conflict_001",
                finding_type="plss_consistency",
                severity="warning",
                message=f"Multiple township tokens detected: {', '.join(townships[:4])}",
            )
        )
    if len(ranges) > 1:
        findings.append(
            ValidatorFindingV0(
                finding_id="plss_range_conflict_001",
                finding_type="plss_consistency",
                severity="warning",
                message=f"Multiple range tokens detected: {', '.join(ranges[:4])}",
            )
        )
    if len(sections) > 3:
        findings.append(
            ValidatorFindingV0(
                finding_id="plss_section_many_001",
                finding_type="plss_consistency",
                severity="info",
                message=f"Many section references detected ({len(sections)}).",
            )
        )
    return findings


def _call_chain_findings(*, text: str) -> Iterable[ValidatorFindingV0]:
    findings: list[ValidatorFindingV0] = []
    lower = text.lower()
    has_beginning = "beginning" in lower
    has_thence = "thence" in lower
    has_close = "point of beginning" in lower
    if has_thence and not has_beginning:
        findings.append(
            ValidatorFindingV0(
                finding_id="call_chain_missing_beginning_001",
                finding_type="call_chain_structure",
                severity="warning",
                message="Call chain includes 'thence' but no beginning statement.",
            )
        )
    if has_beginning and not has_close:
        findings.append(
            ValidatorFindingV0(
                finding_id="call_chain_missing_close_001",
                finding_type="call_chain_structure",
                severity="warning",
                message="Beginning statement found but no explicit close to point of beginning.",
            )
        )
    return findings
