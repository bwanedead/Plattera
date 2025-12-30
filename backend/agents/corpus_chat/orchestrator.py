from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from agents.common.toolbelt import Toolbelt


@dataclass
class CorpusChatOrchestrator:
    """
    Placeholder orchestrator for user-facing corpus Q&A.
    """

    tools: Toolbelt = Toolbelt()

    def ask(self, question: str) -> Dict[str, Any]:
        # v0 placeholder: no LLM call yet
        return {"success": False, "question": question, "note": "skeleton_only"}


