from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

from tests.model.schema_support import ROOT, load_json

INPUTS = ROOT / "contracts/model-inputs"
BASELINE_SHA = "53f528db6e9d3ce00a8c16e8cf24345a992b2b6130cdfb7d5a6dee02dbaed81e"
REQUIRED = ("control-plane.openapi.json", "distribution.openapi.json", "operator.openapi.json",
            "status.openapi.json", "trust.openapi.json")
BEFORE = '''    assert [path.name for path in paths] == [
        "control-plane.openapi.json",
        "distribution.openapi.json",
        "operator.openapi.json",
        "status.openapi.json",
        "trust.openapi.json",
    ]
'''
AFTER = '''    assert {
        "control-plane.openapi.json",
        "distribution.openapi.json",
        "operator.openapi.json",
        "status.openapi.json",
        "trust.openapi.json",
    } <= {path.name for path in paths}
'''


def require_exact_edit(baseline, candidate):
    assert hashlib.sha256(baseline).hexdigest() == BASELINE_SHA
    assert baseline.count(BEFORE.encode()) == 1
    assert candidate == baseline.replace(BEFORE.encode(), AFTER.encode(), 1)


def test_exact_inventory_predicate_and_all_other_legacy_bytes():
    baseline = (INPUTS / "test_lifecycle_contracts.before.txt").read_bytes()
    require_exact_edit(baseline, (ROOT / "tests/model/test_lifecycle_contracts.py").read_bytes())
    amendment = load_json(INPUTS / "api-inventory-amendment.json")
    assert amendment["testChange"]["beforePredicate"] == BEFORE
    assert amendment["testChange"]["afterPredicate"] == AFTER
    assert amendment["testChange"]["requiredApis"] == list(REQUIRED)
    assert amendment["packetDigests"]["CON-MODEL-001"] == "d5f7ccf98a8dfa8862c204bd9be99cbfbc2307b98be00f0112f6e9dcb59abd9e"
    prefix, suffix = baseline.split(BEFORE.encode())
    assert hashlib.sha256(prefix).hexdigest() == "0a5f2f296a083671b69a6927dbfa2bf4d61b017cca16fd4d4ac2911d2c795a79"
    assert hashlib.sha256(suffix).hexdigest() == "78f47b8448f38306e02f88e215e77e6e5161e675d75f8ee4a886479af91d7b8c"


@pytest.mark.parametrize("mutation", ["prefix", "suffix", "fixed-six", "omit-required", "skip-file", "version", "servers", "paths", "refs"])
def test_inventory_authority_rejects_other_changes(mutation):
    baseline = (INPUTS / "test_lifecycle_contracts.before.txt").read_bytes()
    candidate = baseline.replace(BEFORE.encode(), AFTER.encode(), 1)
    if mutation == "prefix":
        candidate = b"# changed\n" + candidate
    elif mutation == "suffix":
        candidate += b"# changed\n"
    elif mutation == "fixed-six":
        candidate = candidate.replace(b"} <= {path.name for path in paths}", b'} == {path.name for path in paths} | {"model.openapi.json"}')
    elif mutation == "omit-required":
        candidate = candidate.replace(b'        "trust.openapi.json",\n', b"")
    elif mutation == "skip-file":
        candidate = candidate.replace(b"for path in paths:", b"for path in paths[:5]:")
    else:
        needle = {"version": b'assert document["openapi"] == "3.1.1"',
                  "servers": b'assert "servers" not in document',
                  "paths": b'assert document["paths"]',
                  "refs": b'assert (path.parent / relative).resolve().is_file()'}[mutation]
        assert needle in candidate
        candidate = candidate.replace(needle, b"assert True", 1)
    with pytest.raises(AssertionError):
        require_exact_edit(baseline, candidate)


def _probe(tmp_path, mutation=None):
    # Copy current approved repository files byte-for-byte. Normal ROOT derivation
    # targets only this fixture tree; never execute the historical text snapshot.
    for name in ("tests/__init__.py", "tests/model/__init__.py", "tests/model/schema_support.py",
                 "tests/model/test_lifecycle_contracts.py"):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    api_dir = tmp_path / "openapi"
    api_dir.mkdir()
    good = {"openapi": "3.1.1", "paths": {"/local": {"get": {}}}}
    for name in (*REQUIRED, "extra-a.openapi.json", "extra-b.openapi.json"):
        (api_dir / name).write_text(json.dumps(good))
    added = {**good, "components": {"schemas": {"local": {"$ref": "../schemas/local.json#/record"}}}}
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas/local.json").write_text('{"record": {"type": "object"}}')
    if mutation in REQUIRED:
        (api_dir / mutation).unlink()
    elif mutation == "version":
        added["openapi"] = "3.0.3"
    elif mutation == "servers":
        added["servers"] = []
    elif mutation == "paths":
        added["paths"] = {}
    elif mutation in {"http", "https", "missing-ref"}:
        added["components"]["schemas"]["local"]["$ref"] = {
            "http": "http://invalid.example/not-fetched.json", "https": "https://invalid.example/not-fetched.json",
            "missing-ref": "absent.json#/record"}[mutation]
    (api_dir / "extra-b.openapi.json").write_text(json.dumps(added))
    env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(tmp_path), str(ROOT / "src"))),
           "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, "-B", str(ROOT / "tests/model_api/inventory_probe.py")],
                          cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)


def test_actual_inventory_accepts_multiple_additions_and_local_ref(tmp_path):
    result = _probe(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "INVENTORY_PROBE_PASS\n"


@pytest.mark.parametrize("mutation", [*REQUIRED, "version", "servers", "paths", "http", "https", "missing-ref"])
def test_actual_inventory_rejects_each_missing_api_and_added_api_safety_failure(tmp_path, mutation):
    result = _probe(tmp_path, mutation)
    assert result.returncode == 1 and "AssertionError" in result.stderr, result.stderr
    assert "INVENTORY_PROBE_PASS" not in result.stdout
