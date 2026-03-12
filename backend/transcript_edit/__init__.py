"""Preferred transcript-edit capability import surface.

This package is the stable, deterministic transcript-edit capability surface.
Legacy imports from ``transcription_edit_loop`` remain supported for compatibility.
New feature work should target this package, not compatibility aliases.
"""

from .apply import apply_plan, apply_plan_to_sections, materialize_canonical_input
from .contracts import *  # noqa: F403
from .persistence import TranscriptionEditPersistenceService
from .run_registry import TranscriptionEditRunRegistry
from .run_service import TranscriptionEditRunService
from .section_adapter import *  # noqa: F403
from .validators import run_validators
