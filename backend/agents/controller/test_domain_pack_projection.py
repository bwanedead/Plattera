from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from agents.controller.domain_pack import DeedToIRDomainPack
from harness.orchestration_kernel.contracts import OrchestratorContext
from harness.orchestration_kernel.loop_memory import LoopMemoryState


class _DashboardStub:
    def __init__(self, payload: dict):
        self._payload = payload

    def model_dump(self, *, mode: str = "json") -> dict:
        return dict(self._payload)


def _make_pack(*, snapshot: dict, phase_hint: str = "author_ir") -> DeedToIRDomainPack:
    pack = DeedToIRDomainPack.__new__(DeedToIRDomainPack)
    pack._started = SimpleNamespace(dashboard=_DashboardStub(snapshot))
    pack._latest_refs = {}
    pack._phase_hint = phase_hint
    pack._request_id_prefix = "req:test"
    pack._start_request = SimpleNamespace(objective="deed pressure test")
    return pack


def _make_context(*, active_item_id: str | None) -> OrchestratorContext:
    return OrchestratorContext(
        session_manager=SimpleNamespace(),
        session_id="session:test",
        loop_memory=LoopMemoryState(active_item_id=active_item_id),
        request_id_prefix="req:test",
        dossier_id=None,
    )


def test_deed_projection_leaves_active_item_unauthored_when_only_advisory_candidates_exist() -> None:
    pack = _make_pack(
        snapshot={
            "claimability": {"claimable_ready": False},
            "gap_summary": {"top_gap_kinds": ["ownership", "geometry"]},
        }
    )
    context = _make_context(active_item_id=None)

    projection = pack.project(context)

    assert projection.resolution_state.active_item_id is None
    assert [item["item_id"] for item in projection.advisory_active_items] == [
        "gap:ownership",
        "gap:geometry",
    ]


def test_deed_projection_keeps_active_item_empty_even_when_kernel_has_continuity() -> None:
    pack = _make_pack(
        snapshot={
            "claimability": {"claimable_ready": True},
            "gap_summary": {"top_gap_kinds": ["ownership"]},
        },
        phase_hint="finalize",
    )
    context = _make_context(active_item_id="gap:ownership")

    projection = pack.project(context)

    assert projection.resolution_state.active_item_id is None
    assert projection.advisory_active_items[0]["item_id"] == "phase:declare_candidate"
