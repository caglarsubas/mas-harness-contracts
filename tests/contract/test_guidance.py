from __future__ import annotations

import copy
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from planeon_harness_contracts.models import MANDATORY_READINESS_GATES  # noqa: E402
from planeon_harness_contracts.questionnaire import (  # noqa: E402
    load_guidance_path,
    validate_guidance_bundle,
    validate_guidance_document,
)
from planeon_harness_contracts.validation import validate_command  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "guidance"
VALID = FIXTURES / "valid"
INVALID = FIXTURES / "invalid"


def load(name: str) -> dict[str, object]:
    return json.loads((INVALID / name).read_text(encoding="utf-8"))


def test_guidance_schemas_are_valid_draft_2020_12() -> None:
    paths = sorted((ROOT / "schemas" / "v1alpha1" / "guidance").glob("*.json"))
    paths += sorted((ROOT / "schemas" / "v1alpha1" / "readiness").glob("*.json"))
    assert len(paths) == 7
    for path in paths:
        Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


def test_valid_documents_match_published_schemas_without_retrieval() -> None:
    schema_paths = sorted((ROOT / "schemas" / "v1alpha1" / "guidance").glob("*.json"))
    schema_paths += sorted((ROOT / "schemas" / "v1alpha1" / "readiness").glob("*.json"))
    schemas = [json.loads(path.read_text(encoding="utf-8")) for path in schema_paths]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    by_kind = {schema.get("title"): schema for schema in schemas if schema.get("title")}
    for document in load_guidance_path(VALID):
        validator = Draft202012Validator(by_kind[document["kind"]], registry=registry)
        assert list(validator.iter_errors(document)) == []


def test_valid_questionnaire_bundle_closes_all_contracts() -> None:
    documents = load_guidance_path(VALID)
    result = validate_guidance_bundle(documents)
    assert result.accepted, result.issues
    assert {document["kind"] for document in documents} == {
        "QuestionnaireDefinition",
        "QuestionnaireSession",
        "QuestionnaireAnswerSet",
        "BusinessContext",
        "DataReadinessAssessment",
        "GuidanceRule",
    }
    readiness = next(document for document in documents if document["kind"] == "DataReadinessAssessment")
    assert tuple(gate["gateId"] for gate in readiness["spec"]["gateResults"]) == MANDATORY_READINESS_GATES


def test_executable_rule_fixture_is_rejected() -> None:
    result = validate_guidance_document(load("executable-rule.json"))
    codes = {issue.code for issue in result.issues}
    assert "EXECUTABLE_CONTENT_FORBIDDEN" in codes
    assert "EXECUTABLE_RULE_FORBIDDEN" in codes


def test_incomplete_readiness_fixture_cannot_report_ready() -> None:
    result = validate_guidance_document(load("incomplete-readiness.json"))
    codes = {issue.code for issue in result.issues}
    assert "MANDATORY_GATE_SET_MISMATCH" in codes
    assert "GATE_EVIDENCE_REQUIRED" in codes


def test_business_owner_and_outcome_are_mandatory() -> None:
    result = validate_guidance_document(load("incomplete-business-context.json"))
    codes = {issue.code for issue in result.issues}
    assert "MANDATORY_OWNER_MISSING" in codes
    assert "MANDATORY_OUTCOME_MISSING" in codes


def test_submitted_answer_set_requires_every_mandatory_answer() -> None:
    documents = list(copy.deepcopy(load_guidance_path(VALID)))
    answer_set = next(document for document in documents if document["kind"] == "QuestionnaireAnswerSet")
    answer_set["spec"]["answers"] = answer_set["spec"]["answers"][:-1]
    result = validate_guidance_bundle(documents)
    assert "MANDATORY_ANSWER_MISSING" in {issue.code for issue in result.issues}


def test_cross_document_references_fail_closed() -> None:
    documents = list(copy.deepcopy(load_guidance_path(VALID)))
    session = next(document for document in documents if document["kind"] == "QuestionnaireSession")
    session["spec"]["questionnaireDefinitionId"] = "questionnaire.unknown"
    result = validate_guidance_bundle(documents)
    assert "REFERENCE_MISMATCH" in {issue.code for issue in result.issues}


def test_malformed_members_and_non_finite_answers_fail_closed() -> None:
    documents = list(copy.deepcopy(load_guidance_path(VALID)))
    answer_set = next(document for document in documents if document["kind"] == "QuestionnaireAnswerSet")
    answer_set["spec"]["answers"] = ["not-an-answer"]
    result = validate_guidance_bundle(documents)
    assert "INVALID_ANSWER_LIST" in {issue.code for issue in result.issues}

    answer_set["spec"]["answers"] = [
        {
            "questionId": "question.business-owner",
            "value": float("nan"),
            "source": "TENANT_DECLARATION",
        }
    ]
    result = validate_guidance_bundle(documents)
    assert "INVALID_ANSWER_VALUE" in {issue.code for issue in result.issues}


def test_invalid_metadata_fails_closed() -> None:
    document = copy.deepcopy(load_guidance_path(VALID)[0])
    document["metadata"] = {"id": "../../escape", "version": "latest"}
    result = validate_guidance_document(document)
    assert "INVALID_METADATA" in {issue.code for issue in result.issues}


def test_questionnaire_cli_route_preserves_catalog_handler_and_reports_counts() -> None:
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        assert validate_command(("--kind", "questionnaire", str(VALID))) == 0
    payload = json.loads(stdout.getvalue())
    assert payload["accepted"] is True
    assert payload["resources"] == {
        "BusinessContext": 1,
        "DataReadinessAssessment": 1,
        "GuidanceRule": 2,
        "QuestionnaireAnswerSet": 1,
        "QuestionnaireDefinition": 1,
        "QuestionnaireSession": 1,
    }
    assert payload["mandatoryGates"] == list(MANDATORY_READINESS_GATES)

    stderr = io.StringIO()
    with redirect_stderr(stderr):
        assert validate_command(("--kind", "questionnaire", str(INVALID / "executable-rule.json"))) == 1
    assert "EXECUTABLE_CONTENT_FORBIDDEN" in stderr.getvalue()
