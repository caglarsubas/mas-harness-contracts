#!/usr/bin/env python3
"""Fail-closed zero-bill scanner for the CON-001 repository surface."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable, Sequence

FORBIDDEN_WORKFLOW_TOKENS = {
    "actions/cache",
    "actions/upload-artifact",
    "schedule:",
    "ubuntu-latest",
    "ubuntu-24.04",
    "windows-latest",
    "macos-latest",
    "ghcr.io",
}
FORBIDDEN_SOURCE_IMPORTS = re.compile(
    r"^(?:from|import)\s+(?:aiohttp|boto3|google\.cloud|httpx|requests|urllib3)(?:\s|\.|$)",
    re.MULTILINE,
)
FORBIDDEN_MANIFEST_TOKENS = {
    "api_key",
    "api-key",
    "client_secret",
    "terraform",
    "pulumi",
    "remote-cache",
}
PINNED_ACTION = re.compile(r"^\s*uses:\s*([^@\s]+)@([0-9a-f]{40})\s*$", re.MULTILINE)
ANY_ACTION = re.compile(r"^\s*uses:\s*([^@\s]+)@([^\s]+)\s*$", re.MULTILINE)


def _files(root: Path, paths: Iterable[str]) -> Iterable[Path]:
    for relative in paths:
        path = root / relative
        if path.is_file():
            yield path
        elif path.is_dir():
            yield from sorted(
                (item for item in path.rglob("*") if item.is_file() and not item.is_symlink()),
                key=lambda item: item.as_posix(),
            )


def scan(root: Path) -> list[str]:
    """Return stable violations for workflows, source imports, and manifests."""

    violations: list[str] = []
    workflow = root / ".github/workflows/verify.yml"
    if not workflow.is_file() or workflow.is_symlink():
        return ["required workflow is absent or linked"]
    workflow_text = workflow.read_text(encoding="utf-8")
    folded_workflow = workflow_text.casefold()
    for token in sorted(FORBIDDEN_WORKFLOW_TOKENS):
        if token in folded_workflow:
            violations.append(f"workflow contains forbidden token: {token}")
    required_labels = "runs-on: [self-hosted, harness-engineering, ephemeral, credential-free]"
    if workflow_text.count(required_labels) != 1:
        violations.append("workflow must use the exact closed self-hosted runner labels")
    if "permissions:\n  contents: read" not in workflow_text:
        violations.append("workflow permissions must be contents-read only")
    if "persist-credentials: false" not in workflow_text:
        violations.append("checkout credentials must not persist")
    if workflow_text.count("run: /opt/planeon/bin/harness-offline-launch") != 1:
        violations.append("workflow must invoke exactly the trusted host launcher")
    actions = ANY_ACTION.findall(workflow_text)
    pinned = PINNED_ACTION.findall(workflow_text)
    if actions != pinned or any(action != "actions/checkout" for action, _digest in pinned):
        violations.append("workflow actions must be the pinned checkout action only")

    for path in _files(root, ("src", "ci")):
        if path.suffix != ".py" or path.name == "network_canary.py":
            continue
        text = path.read_text(encoding="utf-8")
        if FORBIDDEN_SOURCE_IMPORTS.search(text):
            violations.append(f"network/provider import is forbidden: {path.relative_to(root)}")

    for path in _files(root, ("pyproject.toml", "uv.lock", "Makefile", "ci/targets")):
        text = path.read_text(encoding="utf-8").casefold()
        for token in sorted(FORBIDDEN_MANIFEST_TOKENS):
            if token in text:
                violations.append(f"manifest contains a billing or secret vector: {path.relative_to(root)}:{token}")
    return sorted(set(violations))


def main(argv: Sequence[str] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print("usage: zero_bill_scan.py REPOSITORY", file=sys.stderr)
        return 2
    root = Path(arguments[0]).resolve()
    violations = scan(root)
    report = {
        "externalTelemetry": False,
        "githubArtifactStorage": False,
        "hostedRunner": False,
        "paidProvider": False,
        "runtimeDownloads": False,
        "status": "FAIL" if violations else "PASS",
        "thirdPartyApiKey": False,
        "violations": violations,
    }
    print(json.dumps(report, sort_keys=True))
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())

