#!/usr/bin/env python3
"""Compatibility entry point for deterministic generated-contract checking."""

from __future__ import annotations

from generate_contracts import main


if __name__ == "__main__":
    raise SystemExit(main(("--check",)))
