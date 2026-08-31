# Lifecycle and event contracts

`CON-005` publishes state machines and wire contracts only. It does not host an
API, connect a broker, create a database, reconcile Kubernetes, execute an
operation, approve a request, or produce runtime or tenant-acceptance evidence.

## Canonical entities

The machine authority is generated from
`planeon_harness_contracts.state_machine.TRANSITIONS` into
`generated/lifecycle-transitions.json`. Unknown entities, unknown states, self
transitions, skipped transitions, and transitions from a terminal state fail
closed.

- `Operation`: `PENDING`, `RUNNING`, `CANCELLING`, then one terminal result:
  `SUCCEEDED`, `FAILED`, or `CANCELLED`.
- `ApprovalRequest`: one `PENDING` request becomes `APPROVED`, `REJECTED`,
  `EXPIRED`, or `CANCELLED`. Decisions are authenticated records; an approval is
  never inferred from operation success.
- `BundleRelease`: `DRAFT` through resolution, build, scan, signature, and
  release. `REVOKED` is terminal and cannot be cleared by a later recovery.
- `HarnessInstallation`: the exact sixteen-state installation lifecycle used by
  status projections. Upgrade, rollback, uninstall, retirement, and revocation
  are explicit states rather than booleans.
- `EvidenceRecord`: intake becomes `VERIFIED` or `REJECTED`; verified evidence
  may later be `SUPERSEDED` or `REVOKED`. Evidence bytes remain external and are
  referenced only by immutable digest.
- `PolicyBundle`: validation, signature, activation, retirement, and revocation
  are separate transitions.

Retry creates a new operation or uses an explicitly authorized transition such
as `HarnessInstallation.FAILED -> PENDING`. It never edits a terminal operation.
Lifecycle correction creates a new revision/event; audit history is append-only.

## Evidence separation

The contracts preserve these independent axes: source, contract/unit, PR check,
merge, artifact/SBOM, signature/release, deployment, runtime, security,
assurance, and tenant acceptance. A state transition on one entity does not
promote another axis. In particular:

- compilation and a green PR do not prove an artifact or deployment;
- release does not prove runtime health;
- assurance does not manufacture tenant acceptance;
- `NOT_RUN_ENV_UNAVAILABLE` is retained and cannot become pass;
- an `EvidenceRecord` on `TENANT_ACCEPTANCE` requires `TENANT` producer
  authority and `campaignGenerated=false`.

## CloudEvents and audit semantics

`HarnessCloudEvent` is a closed CloudEvents 1.0 JSON envelope. Event types are
versioned and limited to the six lifecycle families plus status projection
updates. Every event carries:

- an immutable UUID, source, type, subject, timestamp, and schema URI;
- matching `organizationid` and `partitionkey` extensions;
- a strictly increasing per-organization/per-subject sequence;
- an aggregate kind, ID, version, correlation and optional causation ID;
- an actor type and opaque stable actor reference;
- one stable reason code, an authorized transition or `null` for projection
  updates, and digest-only resource/evidence references.

The envelope rejects arbitrary members and secret, credential, token, raw
payload, prompt, model-output, and business-payload fields. Event data is audit
metadata, not a transport for tenant business content. Producers authenticate
before publication; consumers authorize the source, enforce the tenant
partition, deduplicate by event ID, order by aggregate sequence, and retain the
original envelope. The AsyncAPI document intentionally names no server or
broker. A deployment chooses a local, open-source transport separately.

The existing generic CLI validates a regular JSON file or a flat directory:

```text
harnessctl validate --kind event PATH
```

Directories are processed lexically. Links, non-JSON entries, duplicate event
IDs, non-increasing aggregate sequences, cross-tenant partition keys, illegal
transitions, and payload-policy violations fail closed.

## API descriptions and compatibility

The repository describes five OpenAPI 3.1.1 surfaces—control lifecycle, tenant
status, distribution release, operator installation, and trust evidence—and one
broker-neutral AsyncAPI 3.0.0 surface. They contain no hosted server URL. Tenant
status routes derive organization identity from the authenticated session;
operator portfolio routes require the independent
`organization:portfolio:view` scope and use indistinguishable not-found
responses.

Within `v1alpha1`, new optional fields may be added only when old consumers can
ignore them and golden vectors prove both directions. Removing or changing a
required field, enum meaning, transition, identity/tenant binding, evidence
axis, or aggregation rule requires a new API version and a dual-read migration
period. Event type versions are immutable.

## Generated release evidence

`scripts/generate_contracts.py` canonicalizes all CON-005 JSON sources and
emits the transition table, status-semantics table, contract index, and release
manifest. `--check` performs no write and fails on a missing, linked, extra, or
byte-stale output. The release manifest state is
`SOURCE_CONTRACT_ONLY`; it explicitly excludes runtime evidence and tenant
acceptance.

Rollback reverts the unconsumed contract release as a unit. Already-consumed
event types and required fields are not silently removed.
