#!/usr/bin/env python3
"""Normalize only uv build flags that are semantic no-ops for uv 0.12.7."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping, Sequence

REAL_UV = Path("/opt/planeon/bin/uv")
REQUIRED_BUILD_FLAGS = ("--offline", "--frozen", "--no-sync")


class UvCompatibilityError(ValueError):
    """The uv command is outside the packet's closed compatibility surface."""


def normalized_argv(arguments: Sequence[str]) -> tuple[str, ...]:
    """Remove only unsupported build-only flags after proving exact presence."""

    values = tuple(arguments)
    if not values:
        raise UvCompatibilityError("uv command is required")
    if values[0] != "build":
        return values
    for flag in REQUIRED_BUILD_FLAGS:
        if values.count(flag) != 1:
            raise UvCompatibilityError(f"uv build requires exactly one {flag}")
    return tuple(value for value in values if value not in {"--frozen", "--no-sync"})


def execution_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """Require the outer runner's frozen, no-sync, offline environment."""

    result = dict(environment)
    for name in ("UV_OFFLINE", "UV_FROZEN", "UV_NO_SYNC"):
        if result.get(name) != "1":
            raise UvCompatibilityError(f"{name}=1 is required")
    result["UV_PYTHON_DOWNLOADS"] = "never"
    return result


def main(arguments: Sequence[str]) -> int:
    """Replace this process with the pinned root-owned uv binary."""

    try:
        normalized = normalized_argv(arguments)
        environment = execution_environment(os.environ)
        if not REAL_UV.is_file() or REAL_UV.is_symlink() or not os.access(REAL_UV, os.X_OK):
            raise UvCompatibilityError("pinned root-owned uv executable is unavailable")
    except UvCompatibilityError as exc:
        print(f"uv compatibility refused: {exc}", file=sys.stderr)
        return 2
    os.execve(REAL_UV, (str(REAL_UV), *normalized), environment)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(tuple(sys.argv[1:])))
