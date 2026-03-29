"""Phase 30: ``agent_kernel`` package init must not eager-import transcript-edit orient (cycle guard)."""


def test_import_kernel_session_manager_without_orient_cycle() -> None:
    from agent_kernel import KernelSessionManager  # noqa: PLC0415

    assert KernelSessionManager is not None


def test_transcript_orient_tool_imports_from_domain_module() -> None:
    from domains.mapping.transcript_edit.orient_tool import TranscriptOrientBaselineTool  # noqa: PLC0415

    assert TranscriptOrientBaselineTool.__name__ == "TranscriptOrientBaselineTool"


def test_tooling_transcript_orient_lazy_reexport() -> None:
    from importlib import import_module

    m = import_module("agent_kernel.tooling_transcript_orient")
    Cls = m.TranscriptOrientBaselineTool
    assert Cls.__name__ == "TranscriptOrientBaselineTool"

