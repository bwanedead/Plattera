from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from harness.observability.summary.models import RequestSummary, VerificationSummary
from harness.runtime.orchestration.contracts import OrchestratorContext


REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_ROOT = REPO_ROOT / "backend" / "harness"


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


def test_shared_surface_fields_stay_generic() -> None:
    assert set(RequestSummary.model_fields) == {"objective", "mode", "trigger"}
    assert set(VerificationSummary.model_fields) == {"status", "last_verification_kind"}

    context_field_names = {field.name for field in fields(OrchestratorContext)}
    assert "opaque_run_context" in context_field_names
    assert "dossier_id" not in context_field_names


def test_hotspot_files_do_not_grow_past_budget() -> None:
    budgets = {
        HARNESS_ROOT / "observability" / "summary" / "build.py": 120,
        HARNESS_ROOT / "observability" / "summary" / "orchestration.py": 400,
        HARNESS_ROOT / "observability" / "summary" / "payload.py": 220,
        HARNESS_ROOT / "observability" / "summary" / "state_projection.py": 130,
        HARNESS_ROOT / "observability" / "summary" / "prompt_observability.py": 90,
        HARNESS_ROOT / "observability" / "summary" / "common.py": 100,
        HARNESS_ROOT / "runtime" / "orchestration" / "orchestrator.py": 560,
        HARNESS_ROOT / "runtime" / "orchestration" / "llm_turn_adapter.py": 310,
        HARNESS_ROOT / "runtime" / "orchestration" / "llm_prompt_builder.py": 155,
        HARNESS_ROOT / "runtime" / "orchestration" / "action_plan_parser.py": 220,
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
