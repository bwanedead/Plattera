"""Quick import validation script - can be deleted after verification."""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.feature_graph.models import (
    FeatureKind,
    FeatureNode,
    FeatureGraph,
)

# Create minimal graph
point = FeatureNode(
    id="test",
    kind=FeatureKind.POINT,
    geometry={"coordinates": [0, 0]}
)

graph = FeatureGraph(
    graph_id="test_001",
    nodes=[point],
    edges=[],
)

# Serialize
json_str = graph.model_dump_json()
print("✓ Import successful")
print("✓ Model creation successful")
print(f"✓ JSON serialization successful ({len(json_str)} bytes)")
print("\nAll basic validations passed!")
