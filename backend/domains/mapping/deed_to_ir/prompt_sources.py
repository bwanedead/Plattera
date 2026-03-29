"""Deed-to-IR compatibility branch prompt source blocks.

This module owns the branch text used by the deed-to-IR adapter seam. It stays
small on purpose so prompt source ownership remains obvious: shared harness
trunk text lives in ``domains.common.prompt_sources`` and domain-branch text
here is strictly deed-to-IR compatibility doctrine.
"""

from __future__ import annotations

from hashlib import sha256

from domains.common.prompt_sources import PromptSourceBlock


_PROMPT_SOURCE_OWNER = "deed_to_ir"
_PROMPT_SOURCE_PATH = "backend/domains/mapping/deed_to_ir/prompt_sources.py"

_BRANCH_DEED_FULL_TMPL = (
    "Domain: deed-to-IR FeatureGraph mapping loop.\n"
    "Faithful representation of deed semantics takes priority over forcing a convenient graph.\n"
    "Structural gates (compile/judge) are necessary but not sufficient for done.\n"
    "Do not finalize placeholder or sketch geometry as a mapped result.\n"
)

_BRANCH_DEED_LIGHT_TMPL = "Domain: deed-to-IR mapping. Faithfulness to deed semantics is required.\n"


def _render_block_text(*, text: str, version: str, light: bool) -> str:
    prefix = f"[BRANCH:deed_to_ir_{version} mode=light]\n" if light else f"[BRANCH:deed_to_ir_{version}]\n"
    return f"{prefix}{text}"


def _make_block(*, block_id: str, text: str, version: str = "v1", light: bool = False) -> PromptSourceBlock:
    rendered = _render_block_text(text=text, version=version, light=light)
    return PromptSourceBlock(
        block_id=block_id,
        layer="domain_branch",
        owner=_PROMPT_SOURCE_OWNER,
        source_path=_PROMPT_SOURCE_PATH,
        version=version,
        text=rendered,
        content_hash=sha256(rendered.encode("utf-8")).hexdigest(),
    )


def build_deed_to_ir_branch_blocks(*, inheritance_mode: str, version: str = "v2") -> tuple[PromptSourceBlock, ...]:
    """Return deed-to-IR branch blocks for identity composition."""
    light = str(inheritance_mode or "").strip().lower() == "light"
    text = _BRANCH_DEED_LIGHT_TMPL if light else _BRANCH_DEED_FULL_TMPL
    return (_make_block(block_id="deed_to_ir_branch", text=text, version=version, light=light),)

