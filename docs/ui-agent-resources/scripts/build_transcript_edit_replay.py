"""Build a compact, sanitized agent-run replay fixture for UI development."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


RUN_ID = "practice-row-live-20260619-76"
DOSSIER_ID = "9f5eecb6-cd7e-483c-b691-b76aa7132e8e"
TRANSCRIPTION_ID = "draft_legal_text_image"

DROP_TURN_KEYS = {
    "raw_prompt_text",
    "mission_state_before",
    "resolution_state_before",
}
BINARY_KEYS = {
    "b64",
    "image_b64",
    "image_base64",
    "image_bytes",
    "raw_bytes",
    "binary",
    "binary_payload",
    "pdf_bytes",
    "bytes",
}
REF_PATTERN = re.compile(
    r"(?:artifact://[^\s\"'<>]+|feature_graph:[A-Za-z0-9:_./-]+|"
    r"transcript_edit:[A-Za-z0-9:_./-]+|t0:raw:[A-Za-z0-9:_./-]+|"
    r"image:(?:assoc|derived):[A-Za-z0-9:_./-]+|subtask:[A-Za-z0-9:_./-]+)"
)
WINDOWS_PATH_PATTERN = re.compile(r"[A-Za-z]:\\[^\r\n\"'<>|]+")
UNIX_PATH_PATTERN = re.compile(r"(?<![A-Za-z0-9:/.-])/(?:[^\s\"'<>]+)")
IMAGE_LINK_PATTERN = re.compile(
    r"(?P<prefix>!?\[[^\]]*\]\()(?P<target>[^)]+\.(?:png|jpg|jpeg|webp))(?P<suffix>\))",
    re.IGNORECASE,
)


PLACEHOLDER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1200 800">
  <rect width="1200" height="800" fill="#f4f5f7"/>
  <path d="M0 0L1200 800M1200 0L0 800" stroke="#d5d9df" stroke-width="2"/>
  <rect x="340" y="310" width="520" height="180" fill="#ffffff" stroke="#8b95a5" stroke-width="2"/>
  <text x="600" y="385" text-anchor="middle" font-family="Arial, sans-serif" font-size="30" fill="#273142">Artifact image omitted</text>
  <text x="600" y="430" text-anchor="middle" font-family="Arial, sans-serif" font-size="20" fill="#667085">Use media_catalog.json for ref, role, and dimensions</text>
</svg>
"""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_paths(repo: Path) -> dict[str, Path]:
    workspace = (
        repo
        / "backend/dossiers_data/artifacts/transcript_edit"
        / DOSSIER_ID
        / TRANSCRIPTION_ID
        / RUN_ID
    )
    return {
        "run": repo / "backend/harness/cli_artifacts/cli_runs" / RUN_ID,
        "workspace": workspace,
        "t0": (
            repo
            / "backend/dossiers_data/views/transcriptions"
            / DOSSIER_ID
            / TRANSCRIPTION_ID
            / "raw"
        ),
        "association": repo / "backend/dossiers_data/associations" / f"assoc_{DOSSIER_ID}.json",
        "message": (
            repo
            / "backend/dossiers_data/artifacts/agent_viewer/user_messages/transcript_edit"
            / f"{RUN_ID}.json"
        ),
        "feedback": (
            repo
            / "backend/dossiers_data/artifacts/agent_viewer/feedback/transcript_edit"
            / f"{RUN_ID}.json"
        ),
        "output": repo / "docs/ui-agent-resources/fixtures" / RUN_ID,
    }


def _sanitize_string(value: str, repo: Path) -> str:
    text = value.replace(str(repo), "<REPO_ROOT>").replace(str(repo).replace("\\", "/"), "<REPO_ROOT>")

    def replace_windows(match: re.Match[str]) -> str:
        raw = match.group(0).rstrip(".,;:)")
        name = Path(raw.replace("\\", "/")).name
        suffix = match.group(0)[len(raw) :]
        return f"<LOCAL_PATH>/{name}{suffix}"

    text = WINDOWS_PATH_PATTERN.sub(replace_windows, text)
    text = UNIX_PATH_PATTERN.sub("<LOCAL_PATH>", text)
    return text


def _sanitize(value: Any, repo: Path, *, key: str | None = None) -> Any:
    if key in BINARY_KEYS:
        return "<BINARY_OMITTED>"
    if isinstance(value, dict):
        return {str(k): _sanitize(v, repo, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(item, repo) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item, repo) for item in value]
    if isinstance(value, str):
        return _sanitize_string(value, repo)
    return value


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sanitize_markdown(text: str, repo: Path, placeholder_target: str) -> str:
    cleaned = _sanitize_string(text, repo)
    return IMAGE_LINK_PATTERN.sub(
        lambda match: f"{match.group('prefix')}{placeholder_target}{match.group('suffix')}",
        cleaned,
    )


def _compact_turn(raw: dict[str, Any], repo: Path) -> dict[str, Any]:
    compact = {k: v for k, v in raw.items() if k not in DROP_TURN_KEYS}
    if compact.get("raw_llm_response_text"):
        compact.pop("raw_llm_response_tail", None)
    compact["fixture_omissions"] = {
        "raw_prompt_text": "omitted_for_size_and_prompt_privacy",
        "before_state_snapshots": "derive_from_previous_turn_after_state",
        "binary_payloads": "replaced_with_markers_and_media_catalog",
    }
    return _sanitize(compact, repo)


def _action_rows(plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(plan, dict):
        return []
    actions = plan.get("actions")
    if not isinstance(actions, list):
        action_type = plan.get("action_type")
        return [{"action_type": action_type}] if action_type else []
    rows: list[dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        rows.append(
            {
                "action_type": action.get("action_type"),
                "alias": action.get("alias"),
                "hydrate_next_count": len(action.get("hydrate_next") or []),
            }
        )
    return rows


def _turn_index_row(turn: dict[str, Any], relative_file: str) -> dict[str, Any]:
    plan = turn.get("parsed_action_plan") if isinstance(turn.get("parsed_action_plan"), dict) else {}
    trace = turn.get("llm_call_trace") if isinstance(turn.get("llm_call_trace"), dict) else {}
    result = turn.get("tool_result_raw") if isinstance(turn.get("tool_result_raw"), dict) else {}
    image_summary = result.get("image_evidence_summary")
    if isinstance(image_summary, dict):
        image_evidence_count = int(image_summary.get("count") or 0)
    elif isinstance(image_summary, list):
        image_evidence_count = len(image_summary)
    else:
        image_evidence_count = 0
    started = turn.get("started_at_epoch_seconds")
    finished = turn.get("finished_at_epoch_seconds")
    duration = finished - started if isinstance(started, (int, float)) and isinstance(finished, (int, float)) else None
    return {
        "turn_index": turn.get("turn_index"),
        "file": relative_file,
        "started_at_epoch_seconds": started,
        "finished_at_epoch_seconds": finished,
        "duration_seconds": duration,
        "model": trace.get("api_model") or turn.get("api_model"),
        "provider": trace.get("provider"),
        "token_usage": {
            "prompt": turn.get("provider_prompt_tokens"),
            "completion": turn.get("provider_completion_tokens"),
            "reasoning": turn.get("provider_reasoning_tokens"),
            "total": turn.get("provider_total_tokens"),
        },
        "operator_progress_message": plan.get("operator_progress_message"),
        "rationale": plan.get("rationale"),
        "actions": _action_rows(plan),
        "tool_execution_state": result.get("execution_state"),
        "artifact_refs": list(result.get("artifact_refs") or []),
        "image_evidence_count": image_evidence_count,
        "motion_posture": (turn.get("prompt_observability_summary") or {}).get("motion_posture"),
        "parse_ok": turn.get("parse_ok"),
        "repair_attempted": turn.get("repair_attempted"),
        "terminal_decision": turn.get("terminal_decision"),
    }


def _collect_refs(value: Any, counter: Counter[str]) -> None:
    if isinstance(value, dict):
        for nested in value.values():
            _collect_refs(nested, counter)
        return
    if isinstance(value, list):
        for nested in value:
            _collect_refs(nested, counter)
        return
    if not isinstance(value, str):
        return
    for match in REF_PATTERN.finditer(value):
        counter[match.group(0).rstrip(".,;:)]}")] += 1


def _ref_kind(ref_id: str) -> str:
    if ref_id.startswith("image:"):
        return "image"
    if ref_id.startswith("t0:"):
        return "source_draft"
    if ref_id.startswith("subtask:"):
        return "delegate_result"
    if ref_id.startswith("transcript_edit:"):
        return "domain_artifact"
    if ref_id.startswith("feature_graph:"):
        return "feature_graph_artifact"
    if ref_id.startswith("artifact://"):
        return "artifact"
    return "unknown"


def _copy_json_tree(source: Path, destination: Path, repo: Path) -> list[Path]:
    written: list[Path] = []
    if not source.is_dir():
        return written
    for path in sorted(source.rglob("*.json")):
        relative = path.relative_to(source)
        target = destination / relative
        _write_json(target, _sanitize(_load_json(path), repo))
        written.append(target)
    return written


def _descriptor_media_row(descriptor_path: Path, png_path: Path, fixture_root: Path) -> dict[str, Any]:
    descriptor = _load_json(descriptor_path) if descriptor_path.is_file() else {}
    metadata = descriptor.get("transform_metadata") if isinstance(descriptor, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    ref_id = None
    for key in ("derived_ref_id", "ref_id", "artifact_ref"):
        candidate = descriptor.get(key) if isinstance(descriptor, dict) else None
        if isinstance(candidate, str) and candidate:
            ref_id = candidate
            break
    if ref_id is None:
        ref_id = f"image:derived:{png_path.stem}"
    return {
        "ref_id": ref_id,
        "kind": "derived_image",
        "role": metadata.get("overlay_role") or metadata.get("sub_action") or descriptor.get("sub_action"),
        "width_height": descriptor.get("width_height") or metadata.get("width_height"),
        "original_byte_count": png_path.stat().st_size,
        "descriptor_file": str((fixture_root / "artifacts/transcript_edit/derived_images" / descriptor_path.name).relative_to(fixture_root)).replace("\\", "/"),
        "placeholder_file": "media/placeholder.svg",
    }


def _build_final_state(last_turn: dict[str, Any]) -> dict[str, Any]:
    return {
        "turn_index": last_turn.get("turn_index"),
        "mission_state": last_turn.get("mission_state_after"),
        "resolution_state": last_turn.get("resolution_state_after"),
        "stable_context": last_turn.get("stable_context"),
        "pinned_refs": last_turn.get("pinned_refs"),
        "latest_refs": last_turn.get("latest_refs_after"),
        "terminal_decision": last_turn.get("terminal_decision"),
    }


def _event_rows(turn_index: list[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    sequence = 0
    for row in turn_index:
        sequence += 1
        yield {
            "schema_version": "agent_run_replay_event.v1",
            "event_id": f"event-{sequence:04d}",
            "sequence": sequence,
            "event_type": "turn_completed",
            "occurred_at_epoch_seconds": row.get("finished_at_epoch_seconds"),
            "turn_index": row.get("turn_index"),
            "payload_ref": row.get("file"),
            "summary": {
                "actions": row.get("actions"),
                "motion_posture": row.get("motion_posture"),
                "terminal_decision": row.get("terminal_decision"),
            },
        }


def build_fixture(paths: dict[str, Path], repo: Path) -> Path:
    output = paths["output"]
    staging = output.with_name(output.name + ".building")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    (staging / "media").mkdir()
    (staging / "media/placeholder.svg").write_text(PLACEHOLDER_SVG, encoding="utf-8")

    turn_files = sorted((paths["run"] / "audit").glob("turn_*.json"))
    compact_turns: list[dict[str, Any]] = []
    index_rows: list[dict[str, Any]] = []
    refs: Counter[str] = Counter()
    for source in turn_files:
        compact = _compact_turn(_load_json(source), repo)
        target = staging / "replay/turns" / source.name
        _write_json(target, compact)
        compact_turns.append(compact)
        relative = str(target.relative_to(staging)).replace("\\", "/")
        index_rows.append(_turn_index_row(compact, relative))
        _collect_refs(compact, refs)

    _write_json(staging / "replay/turn_index.json", index_rows)
    events_path = staging / "replay/events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in _event_rows(index_rows)),
        encoding="utf-8",
    )
    if compact_turns:
        _write_json(staging / "replay/final_state.json", _build_final_state(compact_turns[-1]))

    done = _sanitize(_load_json(paths["run"] / "done.json"), repo)
    state = _sanitize(_load_json(paths["run"] / "state.json"), repo)
    retention = _sanitize(_load_json(paths["run"] / "retention.json"), repo)
    _write_json(staging / "replay/run_summary.json", {"done": done, "state": state, "retention": retention})

    timeline = (paths["run"] / "audit/human/timeline.md").read_text(encoding="utf-8")
    review = (paths["run"] / "audit/review.md").read_text(encoding="utf-8")
    (staging / "replay/timeline.md").write_text(
        _sanitize_markdown(timeline, repo, "../media/placeholder.svg"), encoding="utf-8"
    )
    (staging / "replay/review.md").write_text(
        _sanitize_markdown(review, repo, "../media/placeholder.svg"), encoding="utf-8"
    )

    _copy_json_tree(paths["workspace"], staging / "artifacts/transcript_edit", repo)

    startup_dir = staging / "artifacts/startup"
    for name in (
        f"{TRANSCRIPTION_ID}_draft_1.json",
        f"{TRANSCRIPTION_ID}_draft_2.json",
        f"{TRANSCRIPTION_ID}_draft_3.json",
        f"{TRANSCRIPTION_ID}.json",
    ):
        source = paths["t0"] / name
        if source.is_file():
            _write_json(startup_dir / name, _sanitize(_load_json(source), repo))
    if paths["association"].is_file():
        _write_json(startup_dir / "association.json", _sanitize(_load_json(paths["association"]), repo))

    interaction_dir = staging / "interactions"
    for label in ("message", "feedback"):
        source = paths[label]
        if source.is_file():
            _write_json(interaction_dir / f"{label}.json", _sanitize(_load_json(source), repo))

    media_rows: list[dict[str, Any]] = [
        {
            "ref_id": f"image:assoc:{TRANSCRIPTION_ID}:original",
            "kind": "source_image",
            "role": "original_source",
            "width_height": None,
            "original_byte_count": None,
            "descriptor_file": "artifacts/startup/association.json",
            "placeholder_file": "media/placeholder.svg",
        }
    ]
    derived = paths["workspace"] / "derived_images"
    for png in sorted(derived.glob("*.png")):
        descriptor = png.with_suffix(".json")
        media_rows.append(_descriptor_media_row(descriptor, png, staging))
    represented_media_refs = {str(row["ref_id"]) for row in media_rows}
    for ref_id in sorted(ref for ref in refs if _ref_kind(ref) == "image"):
        if ref_id in represented_media_refs:
            continue
        media_rows.append(
            {
                "ref_id": ref_id,
                "kind": "referenced_image_without_local_descriptor",
                "role": "unknown",
                "width_height": None,
                "original_byte_count": None,
                "descriptor_file": None,
                "placeholder_file": "media/placeholder.svg",
            }
        )
    _write_json(staging / "artifacts/media_catalog.json", media_rows)

    for row in media_rows:
        refs[row["ref_id"]] += 0
    artifact_rows = [
        {
            "ref_id": ref_id,
            "kind": _ref_kind(ref_id),
            "occurrence_count": count,
            "media_placeholder": "media/placeholder.svg" if _ref_kind(ref_id) == "image" else None,
        }
        for ref_id, count in sorted(refs.items())
    ]
    _write_json(staging / "artifacts/artifact_catalog.json", artifact_rows)

    original_bytes = sum(path.stat().st_size for path in paths["run"].rglob("*") if path.is_file())
    original_bytes += sum(path.stat().st_size for path in paths["workspace"].rglob("*") if path.is_file())
    manifest = {
        "schema_version": "agent_run_replay.v1",
        "fixture_id": RUN_ID,
        "source": {
            "domain_id": "transcript_edit",
            "run_id": RUN_ID,
            "dossier_id": DOSSIER_ID,
            "transcription_id": TRANSCRIPTION_ID,
            "turn_count": len(index_rows),
            "terminal_status": done.get("status"),
            "terminal_decision": index_rows[-1].get("terminal_decision") if index_rows else None,
        },
        "viewer_contract": {
            "core_is_domain_agnostic": True,
            "unknown_fields_are_preserved": True,
            "domain_payloads_are_optional_extensions": True,
            "event_stream": "replay/events.jsonl",
            "turn_index": "replay/turn_index.json",
            "artifact_catalog": "artifacts/artifact_catalog.json",
            "media_catalog": "artifacts/media_catalog.json",
        },
        "sanitization": {
            "raw_prompts": "omitted",
            "binary_media": "replaced_by_media/placeholder.svg",
            "absolute_paths": "tokenized",
            "before_state_snapshots": "omitted; derive from prior turn",
            "resume_and_execution_session_internals": "omitted",
            "original_source_bytes": original_bytes,
        },
    }
    _write_json(staging / "replay_manifest.json", manifest)
    validate_fixture(staging, expected_turns=len(turn_files))

    if output.exists():
        shutil.rmtree(output)
    staging.replace(output)
    return output


def validate_fixture(root: Path, *, expected_turns: int) -> None:
    turn_files = sorted((root / "replay/turns").glob("turn_*.json"))
    if len(turn_files) != expected_turns:
        raise ValueError(f"turn_count_mismatch:{len(turn_files)}/{expected_turns}")
    binaries = [path for path in root.rglob("*") if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
    if binaries:
        raise ValueError(f"binary_media_present:{binaries[0]}")
    for path in root.rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
    for path in list(root.rglob("*.json")) + list(root.rglob("*.jsonl")) + list(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        # Serialized JSON contains escaped newlines such as ``witnesseth:\\n``;
        # require two encoded backslashes so those are not mistaken for drives.
        if re.search(r"[A-Za-z]:\\\\", text):
            raise ValueError(f"absolute_windows_path_present:{path}")
        if '"b64"' in text or '"image_b64"' in text:
            raise ValueError(f"binary_key_present:{path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = _repo_root()
    paths = _default_paths(repo)
    if args.output is not None:
        paths["output"] = args.output.resolve()
    for key in ("run", "workspace", "t0", "association"):
        if not paths[key].exists():
            raise SystemExit(f"missing fixture source: {key}={paths[key]}")
    output = build_fixture(paths, repo)
    size = sum(path.stat().st_size for path in output.rglob("*") if path.is_file())
    print(f"built {output} ({size} bytes)")


if __name__ == "__main__":
    main()
