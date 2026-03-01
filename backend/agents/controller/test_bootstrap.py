from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import config.paths as legacy_paths
from backend.agents.controller.bootstrap import (
    hydrate_and_persist_finalized_dossier_text,
    load_transcript_span_seeds_for_mapping,
    materialize_seed_spans_from_text,
    persist_deed_text_artifact,
)
from backend.agents.controller.controller import _bootstrap_deed_span_index_from_transcript_seeds
from backend.agent_kernel.models import ActionType, KernelDashboard, KernelStepResult, StepExecutionState


class _FakeEntry:
    def __init__(self, text: str, provenance: dict[str, str] | None = None) -> None:
        self.text = text
        self.provenance = provenance or {}


class _FakeProvider:
    def __init__(self, text: str, *, error: str | None = None) -> None:
        self._text = text
        self._error = error

    def hydrate_entry(self, ref):  # type: ignore[no-untyped-def]
        del ref
        provenance = {"error": self._error} if self._error else {}
        return _FakeEntry(self._text, provenance=provenance)


def test_persist_deed_text_artifact_writes_full_text_and_excerpt() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            text = "A" * 1500
            out = persist_deed_text_artifact(request_id="req1", deed_text=text, dossier_id="D1")
            payload = json.loads(Path(out.artifact_path).read_text(encoding="utf-8"))
            assert payload["artifact_type"] == "deed_text"
            assert payload["text"] == text
            assert len(out.excerpt) == 1000
        finally:
            legacy_paths.dossiers_root = original  # type: ignore[assignment]


def test_hydrate_and_persist_finalized_dossier_text_returns_none_on_error() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            result = hydrate_and_persist_finalized_dossier_text(
                request_id="req-x",
                dossier_id="D1",
                provider=_FakeProvider("x", error="missing"),
            )
            assert result is None
        finally:
            legacy_paths.dossiers_root = original  # type: ignore[assignment]


def test_hydrate_and_persist_finalized_dossier_text_persists_payload() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            out = hydrate_and_persist_finalized_dossier_text(
                request_id="req-y",
                dossier_id="D1",
                provider=_FakeProvider("Final deed text"),
            )
            assert out is not None
            payload = json.loads(Path(out.artifact_path).read_text(encoding="utf-8"))
            assert payload["text"] == "Final deed text"
            assert payload["dossier_id"] == "D1"
        finally:
            legacy_paths.dossiers_root = original  # type: ignore[assignment]


def test_hydrate_prefers_promoted_transcript_for_mapping_when_pointer_exists() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            tx_root = _patched_root() / "artifacts" / "transcription_edit" / "D1"
            tx_root.mkdir(parents=True, exist_ok=True)
            transcript_path = tx_root / "edited_transcript_x.json"
            transcript_path.write_text(
                json.dumps(
                    {
                        "sections": [
                            {"id": "s1", "body": "Promoted section one."},
                            {"id": "s2", "body": "Promoted section two."},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (tx_root / "latest_transcript_for_mapping.json").write_text(
                json.dumps({"transcript_ref": str(transcript_path)}),
                encoding="utf-8",
            )
            out = hydrate_and_persist_finalized_dossier_text(
                request_id="req-promoted",
                dossier_id="D1",
                provider=_FakeProvider("Finalized fallback text"),
            )
            assert out is not None
            payload = json.loads(Path(out.artifact_path).read_text(encoding="utf-8"))
            assert payload["text"] == "Promoted section one.\n\nPromoted section two."
        finally:
            legacy_paths.dossiers_root = original  # type: ignore[assignment]


def test_load_transcript_span_seeds_for_mapping_skips_hash_mismatch() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            tx_root = _patched_root() / "artifacts" / "transcription_edit" / "D1"
            tx_root.mkdir(parents=True, exist_ok=True)
            (tx_root / "latest_transcript_for_mapping.json").write_text(
                json.dumps({"transcript_ref": "x.json", "transcript_hash": "sha256:abc"}),
                encoding="utf-8",
            )
            seeds_ref = tx_root / "transcript_span_seeds_x.json"
            seeds_ref.write_text(
                json.dumps(
                    {
                        "artifact_type": "transcript_span_seeds_v1",
                        "source_transcript_ref": "x.json",
                        "source_transcript_hash": "sha256:def",
                        "seeds": [],
                    }
                ),
                encoding="utf-8",
            )
            (tx_root / "latest_transcript_span_seeds.json").write_text(
                json.dumps({"seeds_ref": str(seeds_ref), "source_transcript_hash": "sha256:def"}),
                encoding="utf-8",
            )
            assert load_transcript_span_seeds_for_mapping(dossier_id="D1") is None
        finally:
            legacy_paths.dossiers_root = original  # type: ignore[assignment]


def test_materialize_seed_spans_from_text_returns_offsets_for_matching_anchors() -> None:
    deed_text = "Beginning at NW corner of Section 2.\n\nThence east 100 feet to the point of beginning."
    bundle = type(
        "SeedBundle",
        (),
        {
            "source_transcript_ref": "x",
            "source_transcript_hash": "sha256:abc",
            "seeds": [
                {
                    "seed_id": "seed_01",
                    "label": "pob",
                    "locator": {
                        "locator_type": "anchors",
                        "start_anchor": "Beginning at",
                        "end_anchor": "Section 2.",
                        "occurrence": 1,
                    },
                }
            ],
        },
    )()
    spans = materialize_seed_spans_from_text(deed_text=deed_text, seed_bundle=bundle)
    assert spans
    assert spans[0]["seed_id"] == "seed_01"
    assert isinstance(spans[0]["start_char"], int)
    assert isinstance(spans[0]["end_char"], int)


def test_bootstrap_deed_span_index_from_seeds_upserts_when_hash_matches(monkeypatch) -> None:
    class _SessionStub:
        def __init__(self) -> None:
            self.requests: list[object] = []

        def step(self, request):  # type: ignore[no-untyped-def]
            self.requests.append(request)
            return KernelStepResult(
                session_id=request.session_id,
                idempotency_key=request.idempotency_key,
                execution_state=StepExecutionState.EXECUTED,
                step_record={"outputs_inline": {"deed_span_index_ref": {"artifact_path": "artifacts/seeds/index.json"}}},
                dashboard=KernelDashboard.model_validate(
                    {
                        "latest_refs": {"deed_span_index_ref": {"artifact_path": "artifacts/seeds/index.json"}},
                        "gap_summary": {"top_gap_kinds": [], "gap_counts_by_kind": {}, "top_reason_codes": []},
                        "claimability": {"claimable_ready": False, "missing_claimability": []},
                        "budgets_remaining": {},
                        "failure_classification": {},
                        "no_progress_risk": {},
                    }
                ),
            )

    seed_bundle = type(
        "SeedBundle",
        (),
        {
            "source_transcript_ref": "x",
            "source_transcript_hash": "sha256:abc",
            "seeds": [
                {
                    "seed_id": "seed_pob_01",
                    "label": "pob",
                    "locator": {
                        "locator_type": "anchors",
                        "start_anchor": "Beginning at",
                        "end_anchor": "Section 2.",
                        "occurrence": 1,
                    },
                }
            ],
        },
    )()
    monkeypatch.setattr(
        "backend.agents.controller.controller.load_transcript_span_seeds_for_mapping",
        lambda dossier_id: seed_bundle,
    )
    session = _SessionStub()
    step = _bootstrap_deed_span_index_from_transcript_seeds(
        session_manager=session,  # type: ignore[arg-type]
        session_id="sid-1",
        request_id="req-1",
        bootstrap_context={
            "dossier_id": "D1",
            "deed_text_artifact_ref": "artifacts/deed/d1.json",
            "deed_text_full": "Beginning at NW corner of Section 2.\n\nThence east 100 feet.",
            "deed_fingerprint": {"sha256_12": "1234567890ab", "length_chars": 64},
        },
    )
    assert step is not None
    assert len(session.requests) == 1
    req = session.requests[0]
    assert req.action_type == ActionType.UPSERT_DEED_SPAN_INDEX
    assert req.inputs["upserts"][0]["labels"] == ["pob"]


def test_bootstrap_deed_span_index_from_seeds_is_noop_when_no_seeds(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.agents.controller.controller.load_transcript_span_seeds_for_mapping",
        lambda dossier_id: None,
    )

    class _SessionStub:
        def step(self, request):  # type: ignore[no-untyped-def]
            raise AssertionError("step should not be called when no seeds exist")

    step = _bootstrap_deed_span_index_from_transcript_seeds(
        session_manager=_SessionStub(),  # type: ignore[arg-type]
        session_id="sid-2",
        request_id="req-2",
        bootstrap_context={
            "dossier_id": "D1",
            "deed_text_artifact_ref": "artifacts/deed/d1.json",
            "deed_text_full": "Beginning at NW corner of Section 2.",
            "deed_fingerprint": {"sha256_12": "1234567890ab", "length_chars": 35},
        },
    )
    assert step is None
