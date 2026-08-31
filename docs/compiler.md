# Deterministic profile compiler

`CON-004` converts one submitted questionnaire answer set, one fully passing
readiness assessment, and one closed tenant demand declaration into an explicit
planned harness profile. Compilation is pure with respect to selection: it does
not call an LLM, rank a provider into a profile, fetch an artifact, install a
module, provision infrastructure, or contact a network service.

## Admission sequence

The compiler applies the following order and fails closed at the first boundary:

1. Validate the compile request, `QuestionnaireAnswerSet`, and
   `DataReadinessAssessment`. All ten readiness gates must pass.
2. Admit only registered `PUBLIC_DEMAND` capabilities and explicit provider
   selectors in `requestedCapabilities`. Signed environment facts have a
   separate input and cannot be tenant demand.
3. Require a verified, SHA-256-bound environment attestation for the same
   `tenantId` as the compile request and check the
   declared deployment mode, architecture, operating system, Kubernetes
   distribution, and connectivity facts.
4. Identify active provider groups from accepted public demand. Compatible
   members are emitted as `PROPOSED_SELECTOR_ONLY`; they never become profile
   selections. The tenant must accept exactly one selector for every active
   group.
5. Derive directly requested harnesses, conditional and subject-applicable
   prerequisites, and the transitive fixed point. Every non-direct prerequisite
   must appear in `acceptedPrerequisiteHarnessIds` exactly.
6. Resolve module prerequisites, reject conflicts or cycles, check module and
   provider compatibility, and create dependency-first lexical installation
   waves.
7. Emit canonical UTF-8 JSON, an explanation, and a SHA-256 over the exact
   `profile.json` bytes.

`assurance.local-model-judge` never infers a backend. It requires an explicitly
accepted `model.local-cpu` or `model.local-gpu` class and one explicit
`group.model-backend` selector. Assurance subjects are an immutable declared
set. Subject capabilities must already be accepted public demand; environment
facts and selectors cannot be smuggled into the subject set.

## Public resources and exact outputs

The compiler produces six public resource kinds: `TenantDemand`,
`HarnessProfile`, `BillOfMaterials`, `InstallPlan`, `EvidencePlan`, and
`ExecutionBudget`. To preserve the six-file compiler interface, `profile.json`
is a closed compiled-profile document containing `TenantDemand`,
`HarnessProfile`, and `ExecutionBudget` resources.

The output set is exactly:

- `profile.json`
- `bom.json`
- `install-plan.json`
- `evidence-plan.json`
- `explanation.md`
- `profile.sha256`

JSON uses `SORTED_UTF8_JSON_V1`: UTF-8, lexical object keys, compact separators,
no non-finite numbers, and one trailing newline. `profile.sha256` contains the
lower-case SHA-256 reference for the exact `profile.json` bytes.

The compiler structurally requires the upstream verifier's `VERIFIED` signature
status and tenant-bound digest; cryptographic trust-store verification remains an
upstream admission responsibility rather than a self-assertion generated here.

All emitted profiles, BOMs, plans, providers, modules, and install-unit digests
remain `PLANNED` or `MISSING_PLANNED`. Compilation is source-level contract
evidence only. It is not artifact, deployment, runtime, security, assurance, or
tenant-acceptance evidence, and the evidence plan explicitly excludes tenant
acceptance.

## Stable errors

Important admission results include:

- `NEEDS_INPUT`: an active provider group lacks a selector, or local judging
  lacks an explicit model class.
- `INVALID_CAPABILITY_ROLE`: a capability appears in the wrong public,
  environment, selector, or assurance-subject input.
- `INVALID_COMBINATION`: an inactive selector or surplus accepted prerequisite
  is present.
- `AMBIGUOUS_PROVIDER`: an active group has multiple accepted selectors.
- `PROVIDER_UNAVAILABLE`: the accepted provider is incompatible; no fallback is
  substituted.
- `PREREQUISITE_NOT_ACCEPTED`: derived prerequisites have not been explicitly
  accepted.
- `DEPENDENCY_CYCLE`, `CLOSURE_INCOMPLETE`, and `HARNESS_CONFLICT`: graph closure
  is unsafe.
- `EXECUTION_BUDGET_INVALID`: an execution dimension is unbounded or outside its
  closed integer range.

## Offline determinism verification

`harnessctl verify-determinism FIXTURE_DIRECTORY` requires a regular fixture
directory containing `compile-request.json` and `expected-digests.json`. It
checks the repository catalog lock, compiles once in catalog order and once in
reverse order, writes both results into separate clean temporary directories,
byte-compares all six outputs, and checks every golden digest. The command uses
no network, provider credential, external telemetry, cache, or artifact store.
