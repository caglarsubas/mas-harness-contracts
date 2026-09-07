from __future__ import annotations

import copy
import json

import pytest
from jsonschema.exceptions import ValidationError

from tests.model.schema_support import ROOT, load_json
from tests.model_api import contract_checks as checks

FIXTURES = ROOT / "tests/fixtures/model"
SCHEMA_CASES = load_json(FIXTURES / "schema-vectors.json")["cases"]
SEMANTIC_CASES = load_json(FIXTURES / "semantic-vectors.json")["cases"]
STREAM_CASES = load_json(FIXTURES / "stream-vectors.json")["cases"]


@pytest.mark.parametrize("case", SCHEMA_CASES, ids=lambda case: case["id"])
def test_independent_schema_vector(case):
    original = copy.deepcopy(case["value"])
    if case["valid"]:
        checks.check_schema(case["schema"], case["value"])
    else:
        with pytest.raises((ValueError, ValidationError)):
            checks.check_schema(case["schema"], case["value"])
    assert case["value"] == original


def _semantic(case):
    v, kind = case["input"], case["kind"]
    if kind == "request":
        checks.request(v["kind"], v["request"], v.get("capabilities"))
    elif kind == "response":
        checks.response(v["kind"], v["request"], v["response"])
    else:
        functions = {"observation": checks.observation, "lifecycle": checks.lifecycle,
                     "metrics": checks.metrics, "error": checks.error_vector,
                     "binding": checks.binding_vector}
        functions[kind](v)


@pytest.mark.parametrize("case", SEMANTIC_CASES, ids=lambda case: case["id"])
def test_independent_semantic_vector(case):
    original = copy.deepcopy(case["input"])
    if case["valid"]:
        _semantic(case)
    else:
        with pytest.raises((ValueError, ValidationError)):
            _semantic(case)
    assert case["input"] == original


@pytest.mark.parametrize("case", STREAM_CASES, ids=lambda case: case["id"])
def test_independent_stream_vector(case):
    args = (case["kind"], case["raw"], case["requestId"], case["includeUsage"])
    if case["valid"]:
        checks.stream(*args)
    else:
        with pytest.raises((ValueError, ValidationError)):
            checks.stream(*args)


@pytest.mark.parametrize("raw", [
    b'{"model":"a","model":"b"}', b'{"x":NaN}', b'{"x":Infinity}',
    b'{"x":1e309}', b'{"x":"\\ud800"}', b'\xef\xbb\xbf{}', b'\xff',
    b'{}{}', b'', b'[' * 18 + b'0' + b']' * 18, b' ' * 1048577,
])
def test_malformed_and_unbounded_wire_json_is_rejected(raw):
    with pytest.raises((ValueError, UnicodeError)):
        checks.decode(raw)


def test_utf8_and_finite_temperature_are_data_not_signed_payload_floats():
    value = checks.decode('{"model":"local-text","messages":[{"role":"user","content":"你好"}],"temperature":0.5}'.encode())
    checks.request("chat", value)
    assert value["messages"][0]["content"] == "你好"


@pytest.mark.parametrize("name", ["chat", "completion", "response", "embedding", "rerank"])
def test_every_inference_family_rejects_identity_claims(name):
    base = next(c["value"] for c in SCHEMA_CASES if c["id"] == name + "-request")
    for field in ("tenant", "organizationId", "org_id", "admission", "verified", "budgetDigest", "route_id"):
        candidate = {**copy.deepcopy(base), field: "forged"}
        with pytest.raises(ValidationError):
            checks.request(name, candidate)


def test_schema_and_vector_coverage_is_independent_complete_and_nonvacuous():
    expected = {
        "chat-request.schema.json", "chat-response.schema.json", "chat-chunk.schema.json",
        "completion-request.schema.json", "completion-response.schema.json", "completion-chunk.schema.json",
        "response-request.schema.json", "response-response.schema.json", "response-event.schema.json",
        "embedding-request.schema.json", "embedding-response.schema.json",
        "rerank-request.schema.json", "rerank-response.schema.json", "models-response.schema.json",
        "health-response.schema.json", "ready-response.schema.json", "error.schema.json",
        "request-binding.schema.json", "usage-observation.schema.json", "lifecycle-trace.schema.json",
    }
    actual = {p.name for p in (ROOT / "schemas/v1alpha1/model").iterdir()}
    assert actual == expected | {"common.schema.json"}
    for verdict in (True, False):
        assert {c["schema"] for c in SCHEMA_CASES if c["valid"] is verdict} == expected
    for cases in (SCHEMA_CASES, SEMANTIC_CASES, STREAM_CASES):
        assert len({c["id"] for c in cases}) == len(cases)
        assert all(type(c["valid"]) is bool for c in cases)
    assert {c["kind"] for c in SEMANTIC_CASES} == {"request", "response", "observation", "lifecycle", "error", "metrics", "binding"}
    assert {c["kind"] for c in STREAM_CASES if c["valid"]} == {"chat", "completion", "response"}
    assert all(load_json(FIXTURES / name)["provenance"] == "INDEPENDENT_CONTRACT_VECTOR"
               for name in ("schema-vectors.json", "semantic-vectors.json", "stream-vectors.json", "usage-mapping.json"))


def test_mapping_covers_all_observed_fields_without_source_identity_authority():
    mapping = load_json(FIXTURES / "usage-mapping.json")
    report = load_json(ROOT / "contracts/model-inputs/model-usage-v2.json")
    fields = {f["field"] for f in report["facts"] if f["kind"] == "OBJECT_FIELD"}
    rows = mapping["rows"]
    assert len(fields) == len(rows) == 41
    assert {r["field"] for r in rows} == fields
    assert len(report["facts"]) == 162
    assert mapping["originalSourceTests"] == "NOT_RUN_ENV_UNAVAILABLE"
    assert mapping["originalSourceBehavioralParity"] == "NOT_ESTABLISHED"
    assert mapping["mappingMode"] == "DOCUMENTED_DESIGN_DISPOSITION_NOT_SOURCE_CONVERTER"
    assert mapping["reportSha256"] == "aa5488bad4528bd4119dfe9134f517403986b6fd45408f34c508929924e764f9"
    usage = load_json(ROOT / "schemas/v1alpha1/model/usage-observation.schema.json")["properties"]
    doc = (ROOT / "docs/model-usage-compatibility.md").read_text()
    for row in rows:
        assert row["rationale"] and f'| {row["field"]} | {row["disposition"]} |' in doc
        if row["disposition"] == "MAPPED":
            assert row["target"] in usage
        else:
            assert row["disposition"] in {"OMITTED", "UNSUPPORTED"} and row["target"] is None
    disposition = {row["field"]: row["disposition"] for row in rows}
    assert all(disposition[k] == "OMITTED" for k in ("tenant", "org_id", "key_id", "trace_id", "span_id"))
    assert all(disposition[k] == "UNSUPPORTED" for k in ("cost_micros", "pricing_digest", "fallback"))


def test_usage_identity_deduplication_is_not_an_additive_stream_counter():
    original = next(c["input"] for c in SEMANTIC_CASES if c["id"] == "usage-measured")
    checks.observation(original)
    seen = {}
    for event in [original, copy.deepcopy(original)]:
        key = (event["organizationId"], event["requestId"], event["observationId"])
        if key in seen:
            assert seen[key] == event
        else:
            seen[key] = event
    assert len(seen) == 1 and sum(v["totalTokens"] for v in seen.values()) == 6
    conflict = {**original, "totalTokens": 7, "outputTokens": 3}
    checks.observation(conflict)
    assert seen[(conflict["organizationId"], conflict["requestId"], conflict["observationId"])] != conflict


def test_oversize_aggregate_text_rejected_even_when_each_string_is_valid():
    req = {"model": "local-text", "messages": [{"role": "user", "content": "x" * 32768}] * 5}
    checks.check_schema("chat-request.schema.json", req)
    with pytest.raises(ValueError):
        checks.request("chat", req)


@pytest.mark.parametrize("keyword", ["$ref", "$dynamicRef", "$defs", "allOf", "patternProperties", "default"])
def test_structured_schema_extra_keywords_never_resolve_or_execute(keyword):
    source = next(c["value"] for c in SCHEMA_CASES if c["id"] == "structured-chat")
    candidate = copy.deepcopy(source)
    candidate["response_format"]["json_schema"]["schema"][keyword] = "https://invalid.example/never-fetch"
    with pytest.raises(ValidationError):
        checks.request("chat", candidate)
