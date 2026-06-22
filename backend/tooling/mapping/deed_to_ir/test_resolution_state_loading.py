"""Tests for mechanical resolution-state snapshot path loading."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from tooling.mapping.deed_to_ir.resolution_state_loading import (
    load_resolution_state_snapshot_from_path,
    resolve_resolution_state_snapshot,
)
from tooling.mapping.deed_to_ir.resolution_state_projection import ResolutionStateHandoffError

_FIXTURE = Path(__file__).resolve().parents[3] / "domains" / "mapping" / "deed_to_ir" / "test_fixtures"
_RESOLUTION_FIXTURE = _FIXTURE / "resolution_state_snapshot.json"


def test_load_resolution_state_snapshot_from_path_reads_object() -> None:
    loaded = load_resolution_state_snapshot_from_path(_RESOLUTION_FIXTURE)
    assert isinstance(loaded, dict)
    assert isinstance(loaded.get("items"), list)
    assert loaded["items"]


def test_resolve_resolution_state_snapshot_prefers_path_over_inline_absence() -> None:
    loaded = resolve_resolution_state_snapshot(
        resolution_state_snapshot=None,
        resolution_state_snapshot_path=str(_RESOLUTION_FIXTURE),
    )
    assert loaded is not None
    assert loaded["items"]


def test_resolve_resolution_state_snapshot_returns_inline_when_no_path() -> None:
    inline = {"items": [{"item_id": "a"}], "relations": []}
    loaded = resolve_resolution_state_snapshot(
        resolution_state_snapshot=inline,
        resolution_state_snapshot_path=None,
    )
    assert loaded == inline


def test_resolve_resolution_state_snapshot_rejects_both_inline_and_path() -> None:
    with pytest.raises(ResolutionStateHandoffError, match="mutually_exclusive"):
        resolve_resolution_state_snapshot(
            resolution_state_snapshot={"items": [], "relations": []},
            resolution_state_snapshot_path=str(_RESOLUTION_FIXTURE),
        )


def test_load_resolution_state_snapshot_from_path_rejects_missing_file() -> None:
    with pytest.raises(ResolutionStateHandoffError, match="not_found"):
        load_resolution_state_snapshot_from_path(_FIXTURE / "missing_resolution_state.json")


def test_load_resolution_state_snapshot_from_path_rejects_empty_path() -> None:
    with pytest.raises(ResolutionStateHandoffError, match="path_empty"):
        load_resolution_state_snapshot_from_path("")


def test_load_resolution_state_snapshot_from_path_rejects_malformed_json() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        bad_path = Path(tmpdir) / "bad.json"
        bad_path.write_text("{not-json", encoding="utf-8")
        with pytest.raises(ResolutionStateHandoffError, match="unreadable"):
            load_resolution_state_snapshot_from_path(bad_path)


def test_load_resolution_state_snapshot_from_path_rejects_non_object_json() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        array_path = Path(tmpdir) / "array.json"
        array_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        with pytest.raises(ResolutionStateHandoffError, match="not_object"):
            load_resolution_state_snapshot_from_path(array_path)
