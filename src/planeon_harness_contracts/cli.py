"""Generic harnessctl shell with packet-owned command registrations."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from planeon_harness_contracts import __version__
from planeon_harness_contracts.command_registry import load_command_registry
from planeon_harness_contracts.errors import CommandRegistryError


def _parser(command_names: Sequence[str]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harnessctl",
        description="Validate and compile Planeon harness contracts entirely offline.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--self-check", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("command", nargs="?", choices=tuple(command_names))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch a validated command without a shell or network fallback."""

    arguments = tuple(sys.argv[1:] if argv is None else argv)
    try:
        registry = load_command_registry()
    except CommandRegistryError as exc:
        print(f"harnessctl registry refused: {exc}", file=sys.stderr)
        return 2
    parser = _parser(tuple(registry))
    namespace = parser.parse_args(arguments)
    if namespace.self_check:
        if namespace.command is not None or namespace.arguments:
            parser.error("--self-check accepts no command")
        print(f"harnessctl {__version__}: registry={len(registry)} status=PASS")
        return 0
    if namespace.command is None:
        parser.print_help(sys.stderr)
        return 2
    try:
        handler = registry[namespace.command].resolve()
        return int(handler(tuple(namespace.arguments)))
    except CommandRegistryError as exc:
        print(f"harnessctl command refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

