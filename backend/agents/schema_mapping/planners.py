from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class SchemaMappingPlanner:
    """
    v0 placeholder planner.

    Later: decides which gaps to address first and builds retrieval query packs.
    """

    def plan_queries(self, gaps: List[Dict[str, Any]]) -> List[str]:
        return [g.get("message", "") for g in gaps if isinstance(g, dict) and g.get("message")]


