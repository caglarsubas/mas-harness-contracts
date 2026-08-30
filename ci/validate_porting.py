#!/usr/bin/env python3
"""Validate the exact inert CON-001 destination porting ledger."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Sequence

EXPECTED_VALUES = {
    "schemaVersion": "harness.planeon.ai/porting-record/v1alpha1",
    "destinationRepository": "mas-harness-contracts",
    "records": "[]",
}
FORBIDDEN_CLAIMS = {
    "authorizationId",
    "sourceRepository",
    "sourceCommit",
    "sourcePath",
    "sourceGitObject",
    "destinationPath",
    "destinationGitObject",
    "mapping",
    "COPY_AUTHORIZED",
    "PORT_CANDIDATE",
    "APPLIED",
}


def parse_inert_ledger(path: Path) -> dict[str, str]:
    """Parse the three scalar fields without enabling general YAML features."""

    if not path.is_file() or path.is_symlink():
        raise ValueError("PORTING authority is absent or linked")
    fields: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator or not key or not value.strip():
            raise ValueError("PORTING bootstrap must contain only closed scalar fields")
        if key in fields:
            raise ValueError(f"duplicate PORTING field: {key}")
        fields[key] = value.strip()
    return fields


def validate_inert_ledger(path: Path) -> None:
    """Require zero authorization records and reject every copy claim token."""

    text = path.read_text(encoding="utf-8")
    fields = parse_inert_ledger(path)
    if fields != EXPECTED_VALUES:
        raise ValueError("PORTING bootstrap is not the exact NO_AUTHORIZATION ledger")
    for token in FORBIDDEN_CLAIMS:
        if token in "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#")):
            raise ValueError(f"PORTING bootstrap contains a forbidden copy claim: {token}")


def main(argv: Sequence[str] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print("usage: validate_porting.py PORTING.yaml", file=sys.stderr)
        return 2
    try:
        validate_inert_ledger(Path(arguments[0]))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"PORTING validation refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"authorizationState": "NO_AUTHORIZATION", "records": 0, "status": "PASS"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

