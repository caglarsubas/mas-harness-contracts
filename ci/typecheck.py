#!/usr/bin/env python3
"""Offline annotation-completeness and syntax gate for the dependency-free shell."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Iterable, Sequence


def _python_files(roots: Iterable[Path]) -> tuple[Path, ...]:
    files: list[Path] = []
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            raise ValueError(f"type-check root is absent or linked: {root}")
        files.extend(path for path in root.rglob("*.py") if path.is_file() and not path.is_symlink())
    return tuple(sorted(files, key=lambda path: path.as_posix()))


def _public_functions(tree: ast.AST) -> Iterable[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            yield node


def _annotation_errors(path: Path, tree: ast.AST) -> list[str]:
    errors: list[str] = []
    for node in _public_functions(tree):
        if node.returns is None:
            errors.append(f"{path}:{node.lineno}: public function {node.name} lacks a return annotation")
        arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        if node.args.vararg is not None:
            arguments.append(node.args.vararg)
        if node.args.kwarg is not None:
            arguments.append(node.args.kwarg)
        for argument in arguments:
            if argument.arg not in {"self", "cls"} and argument.annotation is None:
                errors.append(
                    f"{path}:{node.lineno}: public function {node.name} argument "
                    f"{argument.arg} lacks an annotation"
                )
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if not arguments:
        print("at least one source root is required", file=sys.stderr)
        return 2
    try:
        files = _python_files(Path(argument) for argument in arguments)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    errors: list[str] = []
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path), type_comments=True)
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append(f"{path}: parse failure: {exc}")
            continue
        errors.extend(_annotation_errors(path, tree))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(json.dumps({"files": len(files), "mode": "ANNOTATION_COMPLETE_AST_V1", "status": "PASS"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

