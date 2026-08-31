"""Canonical JSON and digest helpers for compiler-owned public outputs."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

from planeon_harness_contracts.errors import CompilationError

CANONICALIZATION = "SORTED_UTF8_JSON_V1"


def _validate_json_value(value: Any, path: tuple[str | int, ...] = ()) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CompilationError(
                "NON_CANONICAL_VALUE",
                "canonical JSON forbids non-finite numbers",
                {"path": list(path)},
            )
        return
    if isinstance(value, Mapping):
        for key in value:
            if not isinstance(key, str):
                raise CompilationError(
                    "NON_CANONICAL_VALUE",
                    "canonical JSON object keys must be strings",
                    {"path": list(path)},
                )
        for key in sorted(value):
            _validate_json_value(value[key], path + (key,))
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _validate_json_value(item, path + (index,))
        return
    raise CompilationError(
        "NON_CANONICAL_VALUE",
        f"canonical JSON does not support {type(value).__name__}",
        {"path": list(path)},
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Encode a JSON-compatible value with stable keys, separators, and UTF-8."""

    _validate_json_value(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"


def canonical_sha256(value: Any) -> str:
    """Return a lower-case SHA-256 reference over canonical JSON bytes."""

    return f"sha256:{hashlib.sha256(canonical_json_bytes(value)).hexdigest()}"


def bytes_sha256(value: bytes) -> str:
    """Return a lower-case SHA-256 reference over exact bytes."""

    return f"sha256:{hashlib.sha256(value).hexdigest()}"
