# Alpha 2 model prerequisites

Authority: `MET-A2-001`, approved following the 2026-09-04 entry review.
This publishes work boundaries, not model contracts, observed facts, or test
results. No new repository, source access, signing key, runner, model download,
license disposition, or live campaign is authorized by this publication alone.

## Execution order

| Phase | Packet | Owner | Delivery gate |
|---|---|---|---|
| Alpha 2 | `MET-A2-001` | Meta | Publish this correction; green offline PR and merge |
| Alpha 2 | `MET-OBS-MODEL-001` | Meta / separate observer identity | One signed structural report, validated offline |
| Alpha 2 entry | `MET-REPAIR-001` | Meta | Publish R01–R06 repair authority |
| Foundation correction | `CON-FIX-001` | Contracts | Full-suite baseline, additive tests and independent status vectors |
| Alpha 1 correction | `CTRL-FIX-003` | Control | Freshness, portfolio and canonical status parity |
| Alpha 2 | `CON-MODEL-001` | Contracts | Additive model API/usage release and independent vectors after both corrections, MET-REPAIR-005 and MET-REPAIR-006 |
| Alpha 2 | `MODEL-001` | Model plane | Clean-room inference core against the pinned contract release |
| Alpha 2 | `MODEL-002` | Model plane | Model custody and signed route activation |

The original three-packet publication brought its catalog to 110. The approved
R01–R06 correction brings the current catalog to 114; see
[READINESS_REPAIRS.md](READINESS_REPAIRS.md). The Phase-0 back-test
and reuse index remain historical 107-packet snapshots; their source inventory
is unchanged. None of these steps satisfies a live release or tenant gate.

## Observation: one blob, no source execution

`MET-OBS-MODEL-001` may observe only
`contracts/prometa-model-usage-v2.schema.json` at source commit
`6815c21cb10a4d7dc0b4804f6bb223afb4321e97`, Git blob
`c3ac327e2989ffbbc2452209e2a32f76be911534`. These are existing public provenance
bindings, not paths to an implementation-accessible checkout.

The operator installs the reviewed observer artifacts and independently signs
the exact packet/source authority. The external observer runs under its separate
identity with network and source-write/execute denial. Only the seven existing
structural fact kinds are permitted. Prose, examples, raw JSON/source text,
Python files, source tests, imports and additional blobs remain forbidden.
The report is `architecture/observations/model-usage-v2.json` and uses observation
ID `model-usage-v2-structural-facts`. Its validator must bind the real report
digest, packet bytes, source Git object/SHA-256, canonical order, allowed facts,
and isolation evidence. Synthetic report fixtures are tests, never observations.

## Contract packet development plan

`CON-MODEL-001` owns the wire format; `MODEL-001` implements it. Stop on unresolved
public-format, tenant-isolation or usage-accounting decisions rather than letting
the product invent a divergent format. Use the frozen existing dependencies.

1. Pin the merged meta authority, validated structural report and CON-007 release
   in `contracts/model-inputs.lock.json`; retain source-free inputs under
   `contracts/model-inputs/`. Record provenance for any normative public API
   references. References are research inputs only: no online schema resolution
   during generation, validation or runtime.
2. Add `openapi/model.openapi.json` and Draft 2020-12 schemas under
   `schemas/v1alpha1/model/`. Define the supported subset explicitly:

   | Method / path | Required contract coverage |
   |---|---|
   | `GET /v1/models` | Local model identity, capabilities, visibility; no hosted discovery |
   | `POST /v1/chat/completions` | Messages, supported tools/structured output, bounded tokens, streaming |
   | `POST /v1/completions` | Bounded text input, completion and streaming subset |
   | `POST /v1/responses` | Supported input/output items, stateless response and stream events |
   | `POST /v1/embeddings` | Bounded input, indexed vectors, dimension and usage validation |
   | `POST /v1/rerank` | Bounded query/documents, ranking indices, scores and top-n |
   | `GET /healthz`, `GET /readyz` | Liveness distinct from dependency/route readiness |
   | `GET /metrics` | Content-free local metrics; no external exporter configuration |

   Model-001 does not own activation/admin APIs. No route activation endpoint is
   introduced here; MODEL-002 must reconcile any older descriptive endpoint
   wording with its signed-artifact activation contract before implementation.
3. Specify closed request/response/error/usage/stream schemas with local refs;
   explicitly declare defaults, optional/null distinctions, finite numeric
   bounds, count/size limits, supported capabilities and unsupported-field
   behavior. Stable failures cover malformed input (400/422 as explicitly
   mapped), authentication/authorization (401/403), unknown model (404),
   saturation (429 plus Retry-After), unavailable backend (503), deadline (504)
   and sanitized internal failure (500). Never expose prompts, raw backend
   errors, secrets or cross-tenant identifiers in errors/metrics.
4. Bind trusted tenant, route, correlation and budget context to the existing
   CON-007 admission contract. Client JSON or unsigned tenant headers cannot
   establish identity. Keep authentication versus authorization, transport
   metadata versus request content, and usage observations versus authoritative
   ledger entries distinct. No new signing primitive or auth bypass is permitted.
5. Define request states QUEUED/RUNNING and COMPLETED/CANCELLED/TIMED_OUT/REJECTED/
   FAILED terminals, exactly one terminal result, bounded queue/deadline rules,
   disconnect cancellation and zero retries/provider switching after first byte.
   Specify per-endpoint SSE framing, event IDs/order, finish/error/cancel behavior
   and terminal usage semantics; do not silently mix different API stream shapes.
6. Produce `docs/model-usage-compatibility.md`: map every observed field to a
   tenant-neutral public field, deliberate omission or explicit unsupported
   disposition, with rationale and tests. Observed schema constraints do not
   establish source runtime behavior. Never estimate unreported token usage as
   measured usage, silently double-count stream totals, or mint ledger authority.
7. Author fixtures under `tests/fixtures/model/` and tests under `tests/model_api/`
   independently, before downstream implementation. Cover each endpoint with
   positive/negative vectors, stream ordering and terminal invariants, queue
   rejection/deadline/cancel outcomes, capability mismatch, structured-output
   validation, embedding/rerank boundaries, tenant spoofing, and redaction.
   Mark every fixture `INDEPENDENT_CONTRACT_VECTOR`, not a captured source result.
8. Extend generation/index/release-manifest handling additively. Preserve all
   CON-007 and predecessor entries and golden/compatibility behavior. Pin the
   release manifest, actual source commit and every consumed vector digest;
   never insert invented artifact digests. Run the packet's full offline argv
   list, including the entire contracts test suite, PR checks, merge and
   exact-main replay separately. Pin CON-FIX-001 in addition to the original
   CON-007 provenance; preserve its status vectors. The model packet cannot weaken
   predecessor checks. MET-REPAIR-005 supplies the sole helper-copy exception
   below. MET-REPAIR-006 adds only the exact inventory predicate exception in its
   separate legacy file; all other predecessor test edits remain forbidden.

## Original baseline versus destination conformance

The old MODEL-001 wording required an original-source test baseline that was
never supplied and could not be acquired under its no-source-execution boundary.
The approved correction replaces that impossible implementation prerequisite
with independently authored, pinned contract conformance. This is an explicit
scope change, not evidence that original tests ran or that compatibility passed.

`architecture/model-evidence-boundary.json` keeps these dimensions closed:

- Structural observation: schema facts only, after the observation packet runs.
- Original source tests: `NOT_RUN_ENV_UNAVAILABLE`.
- Original source behavioral parity: `NOT_ESTABLISHED`.
- Destination tests: independent contract vectors; PASS only when executed.
- Live deployment/runtime/assurance/acceptance: separately unproven.

MODEL-001 must emit separate statuses and coverage for every dimension. Its
existing `make source-parity` target name is retained for dispatcher compatibility,
but cannot report original-source parity PASS. It runs destination conformance
and explicitly records the unavailable source baseline. Source-equivalence claims
remain prohibited until separately authorized behavioral evidence exists; a
future change needs its own packet and authority. No source-test execution,
observation expansion or copy authorization is silently added here.

## Runner and execution handoff

No root-owned host files are part of any repository PR. A previously installed
packet pin is not authority for another packet. Before each CI run, the
operator must supply the reviewed exact packet YAML/digest, signed launcher
manifest/version/hash, passing isolation preflight and complete offline cache
on the existing localhost runner. Maintain all canonical warm-root denials and
credential/socket exclusion; do not pass roots to product children. Preserve
the pinned checkout and absolute launcher-only workflow. Missing authority or
cache blocks execution with no hosted or online fallback.

Observation needs a separate source authority and identity, not the CI runner.
No new private key is fabricated to self-approve either boundary. Each packet
requires its own branch/PR, green matching checks, merge and exact-main result.
Product bootstrap happens only after the two new prerequisites have merged.

## Rollback

Before consumers run, revert the authority publication as one unit. After a
consumer exists, supersede contracts/evidence through a new bounded packet;
never rewrite historical source reports or lower signature, billing or copying
gates. Rolling back model implementation must not delete tenant model volumes.

## Linux release prerequisite

The [early Linux amendment](LINUX_READINESS.md) adds CONF-LINUX-001 to MODEL-001
without removing any existing prerequisite. Model API contract-only work retains
its correction gates. Model runtime coding requires fresh native Linux AMD64
baseline PASS; every new model artifact then needs its own target-specific
Linux evidence. ARM64 and GPU/driver claims require independent qualification.
macOS/MLX development evidence does not qualify the Linux Kubernetes runtime.

## Superseding exact fixture-copy exception — MET-REPAIR-005

The [approved fixture amendment](MODEL_FIXTURE_SCOPE_REPAIR.md) adds one merged
predecessor and one exact legacy-test path to CON-MODEL-001. Only the pinned
_copy_generation_inputs helper may add the required model vector/snapshot
copies and input-lock file copy. Every other byte and assertion stays unchanged.
This supersedes only the earlier blanket test-edit exclusion, not the full-suite
or strict release-input requirements. The original 758-test baseline passed;
the missing temporary-input inventory is SOURCE_INSPECTION_ONLY. Native runtime
qualification remains independent and unproven.

## Superseding exact API inventory exception — MET-REPAIR-006

[The inventory amendment](MODEL_API_INVENTORY_REPAIR.md) supersedes the blanket
legacy assertion exclusion only for the pinned required-five membership predicate.
All safety checks and other bytes remain immutable, as does the separate fixture
helper grant. Unlike the earlier fixture finding, this failure was reproduced:
1048 passed, one failed, zero skipped on draft head 47c416676b3fba105d7631c1957b9d729daa592e.
Do not mark the draft complete after the predicate change alone. Remaining normal
conformance review covers verified route dimensions when public dimensions are
omitted, sorted unique model-list/capability consistency, Responses errors after
partial output, and admission-header transport vectors without crypto claims.
