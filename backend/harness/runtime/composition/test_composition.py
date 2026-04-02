from __future__ import annotations

from harness.runtime.composition import DefaultTurnComposer, ToolBinding, TurnBlock, TurnSurface


def test_compose_preserves_surface_block_order() -> None:
    composer = DefaultTurnComposer()
    result = composer.compose(
        TurnSurface(
            surface_id="harness",
            blocks=(TurnBlock(content="h-1"), TurnBlock(content="h-2")),
            payload={"scope": "h"},
        ),
        TurnSurface(
            surface_id="domain",
            blocks=(TurnBlock(content="d-1"),),
            payload={"scope": "d"},
        ),
    )

    assert [block.content for block in result.blocks] == ["h-1", "h-2", "d-1"]
    assert result.surface_payloads["harness"] == {"scope": "h"}
    assert result.surface_payloads["domain"] == {"scope": "d"}


def test_compose_passthrough_tool_handler_by_opaque_id() -> None:
    def handler(request: object) -> dict[str, object]:
        return {"request": request}

    composer = DefaultTurnComposer()
    result = composer.compose(
        TurnSurface(
            surface_id="surface",
            tool_bindings=(ToolBinding(tool_id="opaque-tool-id", handler=handler),),
        )
    )

    assert result.get_tool_handler("opaque-tool-id") is handler
    assert result.tool_handlers["opaque-tool-id"] is handler
