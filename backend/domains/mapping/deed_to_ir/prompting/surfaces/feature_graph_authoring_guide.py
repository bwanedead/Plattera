"""FeatureGraph authoring guide for deed-to-IR agents."""

from __future__ import annotations

from domains.prompting import PromptBlock

from ..branch import DEED_TO_IR_DOMAIN_ID

DEED_TO_IR_FEATURE_GRAPH_AUTHORING_GUIDE_SOURCE_REF = (
    "backend/domains/mapping/deed_to_ir/prompting/surfaces/feature_graph_authoring_guide.py"
)
DEED_TO_IR_FEATURE_GRAPH_AUTHORING_GUIDE_VERSION = "v1"

DEED_TO_IR_FEATURE_GRAPH_AUTHORING_GUIDE_TEXT = """\
Use this as the mental model for authoring FeatureGraph IR. FeatureGraph is the computer-readable IR, but it has layers. Do not blur them.

## The layer model
- **Deed meaning** is what the source says: a point of beginning, a call, a boundary, a parcel, a blocked continuation, a governing range choice.
- **FeatureGraph node kind** classifies what an entity is: `frame`, `point`, `curve`, `region`, `annotation`, `constraint`, or `unknown`.
- **Compiler operation (`op_expr.op_name`)** says how a node is constructed. Operation names are exact registered compiler vocabulary, not deed prose.
- **Operation params** are literal compiler fields. They are not synonyms. If the operation contract says `courses`, do not write `calls`. If it says `distance`, do not write `distance_feet`.
- **Operands** connect constructed nodes by exact feature id. A traverse usually uses the start anchor as an operand; `Close` uses the curve/traverse node as its operand.
- **Rendered geometry** is compiler output. A schema-valid graph can still fail compile if operation params or operands are wrong.

## Node kind vs operation name
`kind` and `op_expr.op_name` are different languages.

- `kind=frame` + `op_name=ReferenceFrame` = survey/frame context such as PLSS, stationing, plat grid, or local frame.
- `kind=point` + `op_name=TiedPoint` = local/schematic anchor point.
- `kind=curve` + `op_name=CourseTraverse` = ordered bearing/distance legs compiled into a curve/LineString.
- `kind=region` + `op_name=Close` = region/polygon derived from one curve operand.
- `kind=annotation` usually has no `op_expr`; use it for blocked/incomplete scope notes without fake geometry.

`annotation` is a FeatureKind, not an operation. `deed_call_sequence`, `public_land_survey_frame`, and `region_from_boundary` are not supported operation names.

## Literal supported-op grammar
The compiler is literal. These names are load-bearing.

### CourseTraverse
Use this exact shape for a mapped ordered deed-call chain:

```json
{
  "id": "example_boundary_chain",
  "kind": "curve",
  "op_expr": {
    "op_name": "CourseTraverse",
    "operands": ["example_start_anchor"],
    "params": {
      "courses": [
        {
          "bearing": 123.25,
          "distance": 250.0,
          "bearing_raw": "S. 56° 45' E.",
          "distance_raw": "250 feet"
        }
      ]
    }
  }
}
```

Rules:
- `params.courses` is required. Do not use `params.calls`.
- Each course requires numeric `bearing` in azimuth degrees and numeric `distance` in feet.
- `bearing_raw` and `distance_raw` preserve source text only. Raw-only rows do not compile.
- Use parsed operand-suite fields (`bearing`, `distance`) when available; keep raw fields beside them for traceability.

### Close
Use this exact shape to make a region from a traverse:

```json
{
  "id": "example_closed_area",
  "kind": "region",
  "op_expr": {
    "op_name": "Close",
    "operands": ["example_boundary_chain"],
    "params": {
      "closure_mode": "snap_to_start",
      "closure_tolerance": 2.0
    }
  }
}
```

Rules:
- `Close` requires exactly one operand: the curve/traverse feature id.
- Closure policy is agent-authored. Deterministic code does not decide whether to snap.
- If the source is incomplete, do not fabricate a close; represent the blocked scope separately.

### ReferenceFrame and TiedPoint
- `ReferenceFrame` is non-rendered context. It helps record the survey basis; it does not by itself place all geometry globally.
- `TiedPoint` is a schematic/local anchor. Put descriptive tie facts in params and cite source links; do not expect it to solve global coordinates unless an external frame/dependency supports that.

## Canonical deed pattern
For an ordinary mappable parcel:
1. `frame` / `ReferenceFrame` for the survey context when relevant.
2. `point` / `TiedPoint` for the point of beginning or local anchor.
3. `curve` / `CourseTraverse` for the ordered call legs.
4. `region` / `Close` for the parcel/area when closure is honest.
5. `annotation` for incomplete or dependency-pending scopes.

This is still computer-readable IR. It is not prose. But do not invent a more natural JSON dialect inside `op_expr.params`; the compiler only reads the registered operation grammar.

## Provenance
Attach `ProvenanceAttachment.source_entity_links` on the node or edge that uses the inherited fact.
- Use exact transcript-edit resolution ids or operand ids as `entity_id`.
- Use the operand-suite or resolution-state ref as `source_ref`.
- Metadata notes are not a substitute for source links on the actual feature that consumes the value.
"""


def build_deed_to_ir_feature_graph_authoring_guide_blocks() -> tuple[PromptBlock, ...]:
    return (
        PromptBlock(
            block_id="deed_to_ir_feature_graph_authoring_guide",
            layer="domain_guidance",
            owner=DEED_TO_IR_DOMAIN_ID,
            source_path=DEED_TO_IR_FEATURE_GRAPH_AUTHORING_GUIDE_SOURCE_REF,
            version=DEED_TO_IR_FEATURE_GRAPH_AUTHORING_GUIDE_VERSION,
            text=DEED_TO_IR_FEATURE_GRAPH_AUTHORING_GUIDE_TEXT,
        ),
    )
