"""Mechanical prompt-block descriptor shared by family/domain prompt surfaces."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptBlock:
    block_id: str
    layer: str
    owner: str
    source_path: str
    version: str
    text: str
