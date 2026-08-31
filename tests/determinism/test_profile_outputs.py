from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from planeon_harness_contracts.canonical import bytes_sha256  # noqa: E402
from planeon_harness_contracts.compiler import OUTPUT_NAMES, compile_profile  # noqa: E402
from planeon_harness_contracts.registry import load_catalog  # noqa: E402

VALID = ROOT / "tests" / "fixtures" / "compiler" / "valid"
CATALOG_DIGEST = json.loads(
    (ROOT / "contracts" / "catalog.lock.json").read_text(encoding="utf-8")
)["catalogDigest"]


def test_all_six_outputs_match_golden_digests() -> None:
    request = json.loads((VALID / "compile-request.json").read_text(encoding="utf-8"))
    expected = json.loads((VALID / "expected-digests.json").read_text(encoding="utf-8"))
    outputs = compile_profile(request, load_catalog(ROOT / "catalog"), CATALOG_DIGEST)
    actual = {name: bytes_sha256(outputs[name]) for name in OUTPUT_NAMES}
    assert actual == expected


def test_profile_digest_names_exact_profile_bytes() -> None:
    request = json.loads((VALID / "compile-request.json").read_text(encoding="utf-8"))
    outputs = compile_profile(request, load_catalog(ROOT / "catalog"), CATALOG_DIGEST)
    assert outputs["profile.sha256"] == f"{bytes_sha256(outputs['profile.json'])}\n".encode("ascii")
    assert tuple(outputs) == OUTPUT_NAMES
