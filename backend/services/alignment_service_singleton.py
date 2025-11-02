"""
Alignment Service Singleton
===========================

Provides a lazy-initialized singleton for `AlignmentService` and a lightweight
readiness flag. By default, alignment is initialized only on first use to
ensure API startup is instant. Optional background warm-up can be enabled in
the future without blocking the event loop.
"""

from __future__ import annotations

import asyncio
from typing import Optional

_alignment_instance: Optional["AlignmentService"] = None
_ready: bool = False
_warmup_started: bool = False


def is_ready() -> bool:
    """Return whether the alignment service has been initialized."""
    return _ready


def _make_service():
    # Import inside function to avoid heavy imports during API startup
    from services.alignment_service import AlignmentService  # type: ignore
    return AlignmentService()


async def warm_up_async() -> None:
    """
    Non-blocking warm-up to initialize the alignment service in the background.
    This should be scheduled with `asyncio.create_task()` on app startup.
    """
    global _warmup_started, _alignment_instance, _ready
    if _warmup_started:
        return
    _warmup_started = True
    try:
        # Initialize in a worker thread to avoid blocking the event loop
        _alignment_instance = await asyncio.to_thread(_make_service)
        _ready = True
    except Exception:
        # If warm-up fails we will attempt lazy initialization on first use
        _ready = False


def get_alignment():
    """
    Lazily construct and return the singleton AlignmentService instance.
    Marks readiness on successful construction.
    """
    global _alignment_instance, _ready
    if _alignment_instance is None:
        _alignment_instance = _make_service()
        _ready = True
    return _alignment_instance


