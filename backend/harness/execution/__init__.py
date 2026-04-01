"""Generic execution layer for the harness."""

from .action_ids import ActionId, normalize_action_id
from .contracts import (
    ActionDispatchHandler,
    ActionDispatchResult,
    ExecutionDashboard,
    ExecutionLatestRefs,
    ExecutionPersistence,
    ExecutionRefusal,
    ExecutionSessionStartRequest,
    ExecutionSessionStartResult,
    ExecutionState,
    ExecutionStepRequest,
    ExecutionStepResult,
    SessionExecutionRecord,
)
from .executor import ExecutionExecutor
from .latest_refs import merge_latest_refs, normalize_latest_refs
from .persistence import JsonFileExecutionPersistence
from .run_artifact import ActionHistoryEntry, RunArtifact
from .session import ExecutionSession, ExecutionSessionManager, new_execution_session

__all__ = [
    "ActionDispatchHandler",
    "ActionDispatchResult",
    "ActionHistoryEntry",
    "ActionId",
    "ExecutionDashboard",
    "ExecutionExecutor",
    "ExecutionLatestRefs",
    "ExecutionPersistence",
    "ExecutionRefusal",
    "ExecutionSession",
    "ExecutionSessionManager",
    "ExecutionSessionStartRequest",
    "ExecutionSessionStartResult",
    "ExecutionState",
    "ExecutionStepRequest",
    "ExecutionStepResult",
    "JsonFileExecutionPersistence",
    "RunArtifact",
    "SessionExecutionRecord",
    "merge_latest_refs",
    "new_execution_session",
    "normalize_action_id",
    "normalize_latest_refs",
]
