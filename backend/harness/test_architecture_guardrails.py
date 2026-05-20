from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from harness.observability.summary.models import RequestSummary, VerificationSummary
from harness.runtime.orchestration.contracts import OrchestratorContext


REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_ROOT = REPO_ROOT / "backend" / "harness"
TRANSCRIPT_EDIT_ROOT = REPO_ROOT / "backend" / "domains" / "mapping" / "transcript_edit"


def _python_source_files() -> list[Path]:
    files: list[Path] = []
    for path in HARNESS_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if path.name.startswith("test_"):
            continue
        files.append(path)
    return files


def _find_literal_occurrences(needle: str) -> list[str]:
    matches: list[str] = []
    for path in _python_source_files():
        lines = path.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, start=1):
            if needle in line:
                rel_path = path.relative_to(REPO_ROOT)
                matches.append(f"{rel_path}:{lineno}: {line.strip()}")
    return matches


def test_harness_source_has_no_banned_architecture_terms() -> None:
    banned_terms = [
        "domain_payload",
        "family_coordination",
        "mapping_ready",
        "dossier_id",
        "run_progress_frame",
        "mission_runtime_ref",
        '.get("domain")',
        "focus_selection",
        "move_resolution",
        "plan_compilation",
        "classify_controller_terminal",
        "progress_cb",
        "wire_identity_trace_cb",
        "wire_raw_io_cb",
        "wire_turn_result_cb",
        "run_continuity_pre_choose_action",
    ]
    failures: list[str] = []
    for term in banned_terms:
        occurrences = _find_literal_occurrences(term)
        if occurrences:
            failures.append(f"{term}:\n  " + "\n  ".join(occurrences))
    assert not failures, "Banned harness architecture terms returned:\n" + "\n\n".join(failures)


def test_removed_harness_paths_do_not_return() -> None:
    removed_paths = [
        HARNESS_ROOT / "orchestration_kernel",
        HARNESS_ROOT / "mission_runtime",
        HARNESS_ROOT / "run_summary.py",
        HARNESS_ROOT / "run_state.py",
        HARNESS_ROOT / "runtime" / "mission" / "family_adapters",
    ]
    found = [str(path.relative_to(REPO_ROOT)) for path in removed_paths if path.exists()]
    assert not found, "Removed harness paths returned:\n" + "\n".join(found)


def test_current_runtime_layout_exists() -> None:
    required_paths = [
        HARNESS_ROOT / "runtime" / "orchestration" / "orchestrator.py",
        HARNESS_ROOT / "runtime" / "orchestration" / "mission_orchestrator.py",
        HARNESS_ROOT / "runtime" / "orchestration" / "llm_prompt_builder.py",
        HARNESS_ROOT / "runtime" / "orchestration" / "lifecycle.py",
        HARNESS_ROOT / "runtime" / "orchestration" / "llm_turn_lifecycle.py",
        HARNESS_ROOT / "runtime" / "orchestration" / "action_plan_parser.py",
        HARNESS_ROOT / "runtime" / "memory" / "continuity.py",
        HARNESS_ROOT / "runtime" / "memory" / "continuity_compaction.py",
        HARNESS_ROOT / "mission_state" / "contracts.py",
        HARNESS_ROOT / "observability" / "summary" / "models.py",
        HARNESS_ROOT / "review" / "tool.py",
        HARNESS_ROOT / "tracing" / "service.py",
    ]
    missing = [str(path.relative_to(REPO_ROOT)) for path in required_paths if not path.exists()]
    assert not missing, "Required harness paths missing:\n" + "\n".join(missing)


def test_transcript_edit_runtime_compiles_declared_pack_surface() -> None:
    adapter_source = (TRANSCRIPT_EDIT_ROOT / "runtime_adapter" / "adapter.py").read_text(encoding="utf-8")
    composition_source = (TRANSCRIPT_EDIT_ROOT / "runtime_adapter" / "composition.py").read_text(
        encoding="utf-8"
    )

    assert "build_transcript_edit_domain_pack" in adapter_source
    for banned in (
        "build_mapping_family_branch_blocks",
        "build_transcript_edit_branch_blocks",
        "build_transcript_edit_procedural_guidance_blocks",
    ):
        assert banned not in adapter_source, f"runtime adapter reintroduced prompt truth via {banned}"

    assert "domain_pack.build_runtime_prompt_blocks" in composition_source
    assert "domain_pack.build_surface_payload()" in composition_source
    assert "build_transcript_edit_tool_specs" not in composition_source


def test_prompt_assembly_stays_harness_owned_and_surface_driven() -> None:
    builder_source = (HARNESS_ROOT / "runtime" / "orchestration" / "llm_prompt_builder.py").read_text(
        encoding="utf-8"
    )
    packet_builder_source = (HARNESS_ROOT / "runtime" / "orchestration" / "prompt_packet_builder.py").read_text(
        encoding="utf-8"
    )
    adapter_source = (HARNESS_ROOT / "runtime" / "orchestration" / "llm_turn_adapter.py").read_text(
        encoding="utf-8"
    )
    repair_lane_source = (HARNESS_ROOT / "runtime" / "orchestration" / "repair_lane.py").read_text(
        encoding="utf-8"
    )
    compaction_source = (HARNESS_ROOT / "runtime" / "memory" / "continuity_compaction.py").read_text(
        encoding="utf-8"
    )

    assert "from .prompt_packet_builder import (" in builder_source
    assert "build_turn_prompt_document" in builder_source
    assert "build_compaction_prompt_document" in builder_source
    assert '"prompt_mode": mode' not in builder_source
    assert "json.dumps(prompt_body" in packet_builder_source
    assert "doctrine_blocks_document(composed_input)" in packet_builder_source
    assert "surface_packet_document(composed_input)" in packet_builder_source
    assert "attempt_repair" in adapter_source
    assert "build_repair_prompt_document" in repair_lane_source
    assert "Previous response failed action-plan parsing." not in adapter_source
    assert "build_compaction_prompt_document" in compaction_source
    assert "journal_entries_to_fold, kernel_step_records_to_fold" not in compaction_source
    assert "from domains." not in builder_source


def test_orchestration_lifecycle_stays_explicit_and_semantic_adapter_minimal() -> None:
    contracts_source = (HARNESS_ROOT / "runtime" / "orchestration" / "contracts.py").read_text(
        encoding="utf-8"
    )
    lifecycle_source = (HARNESS_ROOT / "runtime" / "orchestration" / "lifecycle.py").read_text(
        encoding="utf-8"
    )
    llm_lifecycle_source = (
        HARNESS_ROOT / "runtime" / "orchestration" / "llm_turn_lifecycle.py"
    ).read_text(encoding="utf-8")
    orchestrator_source = (HARNESS_ROOT / "runtime" / "orchestration" / "orchestrator.py").read_text(
        encoding="utf-8"
    )
    adapter_source = (HARNESS_ROOT / "runtime" / "orchestration" / "llm_turn_adapter.py").read_text(
        encoding="utf-8"
    )
    runner_source = (HARNESS_ROOT / "runtime" / "runner" / "runner.py").read_text(
        encoding="utf-8"
    )

    for required in ("def initialize", "def sync", "def choose_action", "def evaluate_terminal"):
        assert required in contracts_source
    for forbidden in (
        "observe_llm_io",
        "observe_turn_completed",
        "observe_prompt_event",
        "before_choose_action",
    ):
        assert forbidden not in contracts_source

    for required in (
        "class OrchestrationLifecycle",
        "class PreChooseActionParticipant",
        "class PromptEventObserver",
        "class RawLlmIoObserver",
        "class TurnCompletionObserver",
    ):
        assert required in lifecycle_source

    assert "class LlmTurnPreChooseActionParticipant" in llm_lifecycle_source
    assert "prompt_event_observer" in llm_lifecycle_source
    assert "pre_choose_action_participant" in orchestrator_source
    assert "turn_completion_observer" in orchestrator_source
    assert "prompt_event_observer=active_lifecycle.prompt_event_observer" in orchestrator_source
    assert "raw_llm_io_observer=active_lifecycle.raw_llm_io_observer" in orchestrator_source
    assert "context.prompt_event_observer" in adapter_source
    assert "context.raw_llm_io_observer" in adapter_source
    assert "KernelPromptEventTraceObserver" in runner_source
    assert "OrchestrationLifecycle" not in adapter_source
    assert runner_source.count("lifecycle=lifecycle") == 1
    for forbidden in (
        "wire_identity_trace_cb",
        "wire_raw_io_cb",
        "wire_turn_result_cb",
        "run_continuity_pre_choose_action",
        "on_turn_completed(",
    ):
        assert forbidden not in adapter_source
        assert forbidden not in orchestrator_source
        assert forbidden not in runner_source


def test_shared_surface_fields_stay_generic() -> None:
    assert set(RequestSummary.model_fields) == {"objective", "mode", "trigger"}
    assert set(VerificationSummary.model_fields) == {"status", "last_verification_kind"}

    context_field_names = {field.name for field in fields(OrchestratorContext)}
    assert "opaque_run_context" in context_field_names
    assert "dossier_id" not in context_field_names


def test_canonical_event_identity_ownership() -> None:
    """Phase 4 guardrail: trace collector is the single canonical owner of run_id in event lineage.

    Enforced invariants:
    - KernelTraceCollector exposes run_id as a property (canonical owner)
    - RunAuditWriter accepts run_id, session_id, request_id at construction (carries lineage)
    - Summary orchestration uses _run_id_from_trace_events (explicit over heuristic)
    - _build_audit_writer in runner accepts run_id, session_id, request_id
    """
    trace_source = (HARNESS_ROOT / "runtime" / "orchestration" / "trace_collector.py").read_text(encoding="utf-8")
    audit_source = (HARNESS_ROOT / "audit" / "run_audit_writer.py").read_text(encoding="utf-8")
    runner_source = (HARNESS_ROOT / "runtime" / "runner" / "runner.py").read_text(encoding="utf-8")
    orchestration_summary_source = (HARNESS_ROOT / "observability" / "summary" / "orchestration.py").read_text(encoding="utf-8")

    # Trace collector owns run_id and embeds it in the request_start payload
    assert "self._run_id = run_id" in trace_source, "trace_collector must store run_id"
    assert '"run_id": self._run_id' in trace_source, "trace_collector must embed run_id in request_start payload"
    assert "def run_id" in trace_source, "trace_collector must expose run_id as a property"

    # Audit writer carries canonical lineage from constructor
    assert "run_id: str" in audit_source, "RunAuditWriter must accept run_id param"
    assert "session_id: str" in audit_source, "RunAuditWriter must accept session_id param"
    assert "request_id: str" in audit_source, "RunAuditWriter must accept request_id param"
    assert "_stamp_canonical_identity" in audit_source, "RunAuditWriter must stamp identity into turn records"
    assert "_canonicalize_payload_identity" in audit_source, "RunAuditWriter must normalize payload identity for JSONL to prevent split lineage"
    assert "_canonical_meta" in audit_source, "RunAuditWriter must propagate identity to event_log"

    # Runner passes canonical IDs to both tracer and audit writer
    assert "run_id=run_id" in runner_source, "runner must pass run_id to KernelTraceCollector and audit writer"
    assert "session_id=session_id" in runner_source, "runner must pass session_id to audit writer"

    # Summary orchestration uses explicit trace-derived run_id before heuristic
    assert "_run_id_from_trace_events" in orchestration_summary_source, \
        "summary orchestration must use explicit run_id from trace events"


def test_hotspot_files_do_not_grow_past_budget() -> None:
    budgets = {
        HARNESS_ROOT / "observability" / "summary" / "build.py": 120,
        HARNESS_ROOT / "observability" / "summary" / "orchestration.py": 400,
        HARNESS_ROOT / "observability" / "summary" / "payload.py": 220,
        HARNESS_ROOT / "observability" / "summary" / "state_projection.py": 130,
        HARNESS_ROOT / "observability" / "summary" / "prompt_observability.py": 115,
        HARNESS_ROOT / "observability" / "summary" / "common.py": 100,
        HARNESS_ROOT / "runtime" / "orchestration" / "orchestrator.py": 760,
        HARNESS_ROOT / "runtime" / "orchestration" / "llm_turn_adapter.py": 390,
        HARNESS_ROOT / "runtime" / "orchestration" / "lifecycle.py": 120,
        HARNESS_ROOT / "runtime" / "orchestration" / "llm_turn_lifecycle.py": 220,
        HARNESS_ROOT / "runtime" / "orchestration" / "llm_prompt_builder.py": 165,
        HARNESS_ROOT / "runtime" / "orchestration" / "action_plan_parser.py": 300,
        HARNESS_ROOT / "runtime" / "memory" / "continuity_compaction.py": 340,
        HARNESS_ROOT / "review" / "reporting.py": 360,
        HARNESS_ROOT / "review" / "tool.py": 340,
        HARNESS_ROOT / "observability" / "payload.py": 350,
    }
    failures: list[str] = []
    for path, budget in budgets.items():
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > budget:
            rel_path = path.relative_to(REPO_ROOT)
            failures.append(f"{rel_path}: {line_count} lines (budget {budget})")
    assert not failures, "Harness hotspot files exceeded size budgets:\n" + "\n".join(failures)
