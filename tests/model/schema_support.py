"""Local Draft 2020-12 registry for repository contract tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def schema_registry() -> Registry:
    resources: list[tuple[str, Resource[Any]]] = []
    for path in sorted((ROOT / "schemas").rglob("*.json")):
        schema = load_json(path)
        schema_id = schema.get("$id")
        if isinstance(schema_id, str):
            resources.append((schema_id, Resource.from_contents(schema)))
    return Registry().with_resources(resources)


def validator(relative_path: str) -> Draft202012Validator:
    schema = load_json(ROOT / relative_path)
    return Draft202012Validator(schema, registry=schema_registry())
