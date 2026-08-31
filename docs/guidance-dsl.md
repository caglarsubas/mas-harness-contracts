# Guidance and readiness contracts

This release defines the deterministic, non-executable input boundary between a
tenant's questionnaire answers and a later profile compiler. It records declared
business context, assesses readiness, and emits recommendations or blocking
guidance. It does not select providers, assemble images, persist sessions, call an
LLM, or execute tenant workloads.

## Resource set

Every resource uses `planeon.io/v1alpha1`, a stable `metadata.id`, a semantic
`metadata.version`, and a closed `spec`.

| Kind | Responsibility |
| --- | --- |
| `QuestionnaireDefinition` | Declares ordered questions and binds every required question to a readiness gate. |
| `QuestionnaireSession` | Carries a declared lifecycle snapshot and revision; persistence remains outside this repository. |
| `QuestionnaireAnswerSet` | Records tenant-declared answers for one session and definition. |
| `BusinessContext` | Records the industry, domain, accountable owners, measurable outcome, regulatory contexts, and technology constraints. |
| `DataReadinessAssessment` | Records evidence-backed outcomes for every mandatory gate and derives `READY` or `BLOCKED`. |
| `GuidanceRule` | Matches declared facts through the closed rule grammar and returns recommendation-only actions. |

Bundle validation requires exactly one resource of every kind except
`GuidanceRule`, for which one or more resources are required. References must
resolve to the one definition and session in the bundle. A submitted answer set
must answer every required question.

## Mandatory readiness gates

Questionnaire definitions and readiness assessments use the following ten gates
in this canonical order:

1. `business.owner`
2. `business.outcome`
3. `data.owner`
4. `data.quality`
5. `data.completeness`
6. `data.freshness`
7. `data.provenance`
8. `data.classification`
9. `integration.readiness`
10. `autonomy.boundary`

Every gate must have at least one required question. Every readiness assessment
must contain exactly these gates. A `PASS` requires at least one evidence ID.
`missingGateIds` is the exact sorted set of gates whose status is not `PASS`.
`READY` is valid only when all gates pass; `BLOCKED` is valid only when at least
one gate does not pass. This assessment is readiness evidence, not deployment,
runtime, assurance, or tenant-acceptance evidence.

## Closed rule grammar

Rules are JSON objects. Each node has exactly the fields shown below.

| Operator | Shape | Meaning |
| --- | --- | --- |
| `all` | `{"op":"all","rules":[RULE,...]}` | Every child matches. |
| `any` | `{"op":"any","rules":[RULE,...]}` | At least one child matches. |
| `not` | `{"op":"not","rule":RULE}` | The child does not match. |
| `eq` | `{"op":"eq","path":PATH,"value":SCALAR_OR_SCALAR_LIST}` | Actual and expected values have the same JSON-compatible runtime type and value. |
| `in` | `{"op":"in","path":PATH,"value":[SCALAR,...]}` | Actual has the same type and value as one unique choice. |
| `exists` | `{"op":"exists","path":PATH}` | The mapping path is present and its value is not null. |
| `gte` | `{"op":"gte","path":PATH,"value":NUMBER}` | Actual is a finite non-boolean number greater than or equal to the threshold. |
| `lte` | `{"op":"lte","path":PATH,"value":NUMBER}` | Actual is a finite non-boolean number less than or equal to the threshold. |

`PATH` is a dotted identifier such as `data.quality.score`. Resolution traverses
mapping keys only. Attribute access, list indexing, brackets, calls, and dynamic
path construction are invalid. Missing paths do not match. Boolean values never
act as numbers. Rule trees are limited to 16 levels and 128 nodes.

The evaluator is pure: it reads the supplied rule and fact mappings and returns a
boolean. It performs no imports, evaluation, templating, filesystem or network
access, LLM calls, secret lookup, persistence, or mutation. Unknown operators and
extra fields are rejected rather than ignored.

## Guidance and lifecycle boundaries

Guidance actions are limited to `ASK_QUESTION`, `REQUIRE_EVIDENCE`,
`RECOMMEND_HARNESS`, and `BLOCK_READINESS`. Harness recommendations must name a
known harness from the catalog. An action is advisory or blocking input for a
later compiler; it cannot execute code or authorize a deployment.

Session states are `DRAFT`, `IN_PROGRESS`, `BLOCKED`,
`READY_FOR_COMPILATION`, and `SUPERSEDED`. They are declared snapshots. This
package neither stores sessions nor treats a session state as proof that a
profile, artifact, deployment, runtime, assurance campaign, or tenant acceptance
exists.

Executable expressions, templates, command arguments, handlers, import targets,
filesystem paths, endpoints, URLs, network instructions, LLM prompts, persistence
instructions, and secret or API-key fields are forbidden throughout a bundle.

## Offline validation

Validate a bundle directory with the packet-owned command:

```text
harnessctl validate --kind questionnaire tests/fixtures/guidance/valid
```

The validator loads only regular `.json` files beneath the supplied
directory, rejects symlinks and unexpected files, validates every resource and
cross-reference, and prints canonical JSON evidence. Rule vectors are evaluated
in lexical ID order and serialized as compact, key-sorted JSON followed by one
newline so repeated runs are byte-identical.
