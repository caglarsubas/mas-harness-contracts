# Harness taxonomy v1alpha1

This taxonomy is the closed public authority for the sixteen logical Planeon
harness classes. It separates logical harness selection from repository
ownership: several harnesses can be implemented by one plane repository while
remaining independently selectable and independently releasable install units.

The catalog is declarative. It does not install software, contact a provider,
download a model, provision infrastructure, or establish tenant acceptance.
Every listed framework provider is `PLANNED` and blocked from release until its
upstream license evidence and immutable artifacts are separately approved.

## Canonical harness map

| Plane | Harness ID | Display name | Owning product repository |
| --- | --- | --- | --- |
| Runtime | `runtime.infrastructure` | Infrastructure and Runtime | `mas-harness-operator` |
| Runtime | `runtime.model-inference` | Model and Inference | `mas-harness-model-plane` |
| Runtime | `runtime.ai-gateway` | AI Gateway | `mas-harness-runtime-plane` |
| Runtime | `runtime.experience` | Experience and Interaction | `mas-harness-runtime-plane` |
| Knowledge | `knowledge.domain-semantic` | Domain and Semantic | `mas-harness-knowledge-plane` |
| Knowledge | `knowledge.data-integration` | Data Integration and Provenance | `mas-harness-knowledge-plane` |
| Knowledge | `knowledge.retrieval-context` | Retrieval and Context Engineering | `mas-harness-knowledge-plane` |
| Knowledge | `knowledge.memory-state` | Memory and State | `mas-harness-knowledge-plane` |
| Execution | `execution.protocol-interoperability` | Protocol and Interoperability | `mas-harness-execution-plane` |
| Execution | `execution.orchestration` | Orchestration and Durable Execution | `mas-harness-execution-plane` |
| Execution | `execution.tool-skill-sandbox` | Tool, Skill and Sandbox | `mas-harness-execution-plane` |
| Execution | `execution.ml-decision` | ML and Decision Intelligence | `mas-harness-execution-plane` |
| Trust | `trust.security-safety` | Security, Safety and Guardrails | `mas-harness-trust-plane` |
| Trust | `trust.governance-agentops` | Governance, Oversight and AgentOps | `mas-harness-trust-plane` |
| Trust | `trust.observability-finops` | Observability and FinOps | `mas-harness-trust-plane` |
| Trust | `trust.evaluation-assurance` | Evaluation and Assurance | `mas-harness-trust-plane` |

The four-per-plane cardinality and the IDs above are validated as an exact set.
A taxonomy revision is required to add, remove, rename, or move a harness.

## Capability admission roles

Every input capability has exactly one role:

- `PUBLIC_DEMAND` is an answer a tenant may intentionally request.
- `ENVIRONMENT_FACT` is discovered by a trusted environment probe and requires
  a signed attestation. It is never accepted as a questionnaire answer.
- Provider selectors are declared only by `FrameworkProviderDefinition` and
  choose one implementation within an active selector group.
- Every unregistered capability is `INTERNAL_ONLY` by default and is rejected
  at the public admission boundary.

The three registries are disjoint. When public demand activates a provider
group, exactly one selector is required. A selector for an inactive group is an
invalid combination; zero choices is `NEEDS_INPUT`; multiple choices is
`AMBIGUOUS_PROVIDER`.

The initial groups are infrastructure distribution, local model backend,
protocol adapter, native sandbox provider, and deterministic decision provider.
Provider credentials, external telemetry, runtime downloads, metered APIs, and
cloud provisioning are all forbidden in these declarations.

## Dependencies and conflicts

Harness dependencies use four explicit meanings:

- `ALWAYS` is selected whenever the source harness is selected.
- `WHEN_CAPABILITY` is selected only when one of its named internal conditions
  becomes active.
- `PRODUCTION_GATE` is evidence required for production admission; it is not a
  runtime dependency edge.
- `SUBJECT_UNDER_EVALUATION` names what assurance evaluates and cannot create an
  installation dependency.

All referenced harness and module IDs must exist. Self-dependencies, cycles,
dangling references, self-conflicts, and asymmetric conflicts fail closed.
Conflicts are evaluated again against a selected harness set before compilation.

## Modules, install units, and releases

Each harness currently declares one core `HarnessModuleDefinition`. This is a
minimum catalog shape, not a monolithic-image requirement: later taxonomy
revisions may introduce more independently selectable modules without changing
the sixteen logical harness boundaries.

Every install unit is independent, forbids runtime downloads, and requires an
immutable digest at release. Module declarations also forbid external egress by
default, declare compatibility and resource envelopes, carry an SPDX license
disposition, and require health, rollback, and uninstall behavior.

`ModuleRelease` separates intent from published evidence:

- `PLANNED` requires every artifact, SBOM, license, and signature digest to be
  absent with `MISSING_PLANNED` status.
- `RELEASED` requires all four SHA-256 digests to be locked, an upgrade
  preflight, and digest-bound rollback.

A catalog entry therefore does not imply that an image exists, is deployed,
runs correctly, is assured, or has been accepted by a tenant.

## Deployment and evidence boundaries

Compatibility is explicit for operator-hosted SaaS, tenant public cloud,
self-managed Kubernetes or VMs, and air-gapped installations. An entry can
support only a subset. Architecture, operating system, and Kubernetes
distribution constraints are evaluated later against signed environment facts.

Source, CI, artifact, deployment, runtime, security, assurance, and tenant
acceptance remain independent evidence states. This catalog can establish only
source-level contract validity and its own deterministic lock.

## Canonical catalog lock

`harnessctl catalog lock --check` loads regular, non-linked JSON files beneath
`catalog/` in lexical path order. Each document is encoded as UTF-8 JSON with
sorted keys and no insignificant whitespace (`SORTED_UTF8_JSON_V1`) before its
SHA-256 digest is calculated. The ordered entry list is encoded the same way to
produce the catalog digest in `contracts/catalog.lock.json`.

The command is read-only. A missing, linked, malformed, or stale lock fails
closed. `harnessctl validate --kind catalog catalog/` validates all resources,
the exact harness and provider sets, role separation, dependency closure, and
the packet's negative admission vectors entirely offline.
