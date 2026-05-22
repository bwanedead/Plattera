from __future__ import annotations

import json

from harness.runtime.orchestration.prompt_budget import (
    BUDGET_BUCKET_KEYS,
    build_prompt_budget_report,
    measure_json_chars,
    top_prompt_budget_buckets,
)


def test_budget_buckets_present_and_total_plausible() -> None:
    instruction = "Choose the next action."
    prompt_body = {
        "prompt_mode": "full_choose_action",
        "doctrine_blocks": [{"text": "generic doctrine"}],
        "surface_packet": {"tool_ids": ["read_artifact"]},
        "run_context": {
            "iteration": 3,
            "latest_refs": {"final": "artifact://final"},
            "projection": {
                "mission_state": {"mission_id": "m1"},
                "resolution_state": {"items": []},
            },
        },
        "structured_state": {
            "recent_tool_result_slices": [{"kernel_turn_index": 2, "action_type": "noop"}],
            "prompt_observability_summary": {"resolution_item_count": 1},
        },
    }
    report = build_prompt_budget_report(
        instruction_text=instruction,
        prompt_body=prompt_body,
    )
    buckets = report["buckets"]
    for key in BUDGET_BUCKET_KEYS:
        assert key in buckets
    assert buckets["instruction_text"] == len(instruction)
    assert buckets["total_prompt_chars"] >= buckets["instruction_text"]
    assert buckets["generic_doctrine"] > 0
    assert buckets["tool_specs_or_surface_payloads"] > 0


def test_top_buckets_sorted_by_chars() -> None:
    buckets = {
        "instruction_text": 10,
        "resolution_state": 500,
        "latest_refs": 50,
        "total_prompt_chars": 560,
    }
    top = top_prompt_budget_buckets(buckets, limit=3)
    assert top[0]["bucket"] == "resolution_state"
    assert top[0]["chars"] == 500
    assert top[1]["bucket"] == "latest_refs"


def test_domain_doctrine_bucket_uses_nested_layer_metadata() -> None:
    report = build_prompt_budget_report(
        instruction_text="x",
        prompt_body={
            "doctrine_blocks": [
                {
                    "content": "trunk",
                    "metadata": {"bootstrap": {"layer": "harness_trunk"}},
                },
                {
                    "content": "DOMAIN_BRANCH_UNIQUE_MARKER " * 12,
                    "metadata": {"bootstrap": {"layer": "domain_branch"}},
                },
            ]
        },
    )
    buckets = report["buckets"]
    assert buckets["domain_doctrine"] > buckets["generic_doctrine"]
    assert buckets["generic_doctrine"] > 0


def test_report_has_no_raw_payload_or_b64() -> None:
    instruction = "x" * 200
    prompt_body = {
        "structured_state": {
            "recent_tool_result_slices": [
                {
                    "outputs_excerpt": {"text": "sensitive payload " * 50},
                    "artifact_refs": ["artifact://a"],
                }
            ]
        }
    }
    report = build_prompt_budget_report(
        instruction_text=instruction,
        prompt_body=prompt_body,
    )
    serialized = json.dumps(report)
    assert "sensitive payload" not in serialized
    assert "b64" not in serialized.lower()
    assert measure_json_chars({"a": 1}) > 0
