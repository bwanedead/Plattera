"""Small typed errors for delegated subtask mechanics."""

from __future__ import annotations


class SubtaskValidationError(ValueError):
    """Raised when a parent-authored delegate_subtask action is mechanically invalid."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class SubtaskRegistryError(LookupError):
    """Raised when a requested profile is not registered."""

    def __init__(self, profile_id: str) -> None:
        super().__init__(f"unknown subtask profile: {profile_id}")
        self.profile_id = profile_id
