from __future__ import annotations

import ast
from pathlib import Path


def test_runtime_package_does_not_import_transcript_edit_domain() -> None:
    runtime_root = Path(__file__).resolve().parent
    forbidden_prefix = "domains.mapping.transcript_edit"

    violations: list[str] = []
    for path in sorted(runtime_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == forbidden_prefix or alias.name.startswith(f"{forbidden_prefix}."):
                        violations.append(f"{path}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == forbidden_prefix or module.startswith(f"{forbidden_prefix}."):
                    violations.append(f"{path}: from {module} import ...")
                if module == "domains.mapping":
                    for alias in node.names:
                        if alias.name == "transcript_edit" or alias.name.startswith("transcript_edit."):
                            violations.append(f"{path}: from {module} import {alias.name}")

    assert violations == [], "runtime package imported transcript_edit domain:\n" + "\n".join(violations)
