# Migrating `data.harness/v1`

`CON-006` provides a clean-room, optional compatibility boundary between the
deprecated `data.harness/v1` family and `harness.planeon.ai/v1alpha1`. It does
not import, execute, package, or modify the warm-start repository.

## Authority and scope

The mapping was independently implemented from the merged, source-free
`MET-002` observation report whose canonical digest is
`sha256:5c559a6ef3d59fa40e74ab2fb36603752751f523249da884f8e0d8daa06cfe10`.
That report records 29 JSON Schema blobs at source commit
`858281f4b845ffacfe05cdb2c40a402c237d4c54`. Copy authority is `NONE`.

The compatibility layer supports these 29 legacy contract identities:

| Contract | Support |
| --- | --- |
| `action-preview` | `ROUND_TRIP_SUPPORTED` |
| `bounded-query-plan` | `ROUND_TRIP_SUPPORTED` |
| `checkpoint-token` | `ROUND_TRIP_SUPPORTED` |
| `connector-worker-profile` | `ROUND_TRIP_SUPPORTED` |
| `coverage-statement` | `ROUND_TRIP_SUPPORTED` |
| `cross-plane-evidence-set` | `ROUND_TRIP_SUPPORTED` |
| `data-batch` | `ROUND_TRIP_SUPPORTED` |
| `data-source-connector-profile` | `ROUND_TRIP_SUPPORTED` |
| `deployment-profile` | `ROUND_TRIP_SUPPORTED` |
| `disconnected-runtime-readiness` | `ROUND_TRIP_SUPPORTED` |
| `durable-action-record` | `ROUND_TRIP_SUPPORTED` |
| `entity-redirect` | `ROUND_TRIP_SUPPORTED` |
| `freshness-observation` | `ROUND_TRIP_SUPPORTED` |
| `industry-domain-pack-manifest` | `ROUND_TRIP_SUPPORTED` |
| `live-acceptance-campaign` | `ROUND_TRIP_SUPPORTED` |
| `local-cross-plane-evidence` | `ROUND_TRIP_SUPPORTED` |
| `local-harness-runtime-evidence` | `ROUND_TRIP_SUPPORTED` |
| `local-image-lock` | `ROUND_TRIP_SUPPORTED` |
| `local-source-evidence` | `ROUND_TRIP_SUPPORTED` |
| `northbound-tool-catalog` | `ROUND_TRIP_SUPPORTED` |
| `promotion-readiness` | `ROUND_TRIP_SUPPORTED` |
| `protocol-profile-conformance` | `ROUND_TRIP_SUPPORTED` |
| `reference-lab-manifest` | `ROUND_TRIP_SUPPORTED` |
| `route-decision` | `ROUND_TRIP_SUPPORTED` |
| `semantic-assertion` | `ROUND_TRIP_SUPPORTED` |
| `semantic-mapping-candidate` | `ROUND_TRIP_SUPPORTED` |
| `source-action-capability-profile` | `ROUND_TRIP_SUPPORTED` |
| `source-action-plan` | `ROUND_TRIP_SUPPORTED` |
| `source-mutation-receipt` | `ROUND_TRIP_SUPPORTED` |

## Exact field mapping

The conversion profile is `data-harness-v1-lossless-envelope/v1`.

| Legacy location | Canonical location | Direction |
| --- | --- | --- |
| `/schemaVersion` | `/spec/legacySchemaVersion` | `BIDIRECTIONAL_EXACT` |
| `/{topLevelField}` except `schemaVersion` | `/spec/fields/{topLevelField}` | `BIDIRECTIONAL_EXACT` |

The canonical envelope also records the contract identity, source-schema Git
object and digest, observation digest, conversion profile, and legacy document
digest under `/metadata`. Those fields make provenance and tamper checks
deterministic; they are not asserted to be tenant acceptance or runtime proof.

Conversion performs the observed closed top-level field, required-field, JSON
type, constant, and enum checks. It is not a replacement for domain-specific
nested semantic validation at the legacy boundary.

## State views

Legacy state values remain byte-for-byte recoverable in `/spec/fields`. The
adapter additionally publishes these uppercase canonical views where the
observation established a finite state set:

| Contract and observed schema pointer | Legacy to canonical values |
| --- | --- |
| `cross-plane-evidence-set` `/$defs/claim/allOf/0/if/properties/status` | `failed` -> `FAILED`; `passed` -> `PASSED` |
| `cross-plane-evidence-set` `/$defs/claim/allOf/1/if/properties/status` | `missing` -> `MISSING`; `not-applicable` -> `NOT_APPLICABLE` |
| `cross-plane-evidence-set` `/$defs/claim/properties/status` | `failed` -> `FAILED`; `missing` -> `MISSING`; `not-applicable` -> `NOT_APPLICABLE`; `passed` -> `PASSED` |
| `deployment-profile` `/properties/mode` | `air-gapped` -> `AIR_GAPPED`; `connected` -> `CONNECTED`; `local-laptop` -> `LOCAL_LAPTOP`; `self-hosted` -> `SELF_HOSTED` |
| `durable-action-record` `/properties/state` | `executed` -> `EXECUTED`; `executing` -> `EXECUTING`; `failed` -> `FAILED`; `prepared` -> `PREPARED`; `reconciliation-required` -> `RECONCILIATION_REQUIRED` |
| `live-acceptance-campaign` `/$defs/evidence/properties/status` | `failed` -> `FAILED`; `passed` -> `PASSED` |
| `promotion-readiness` `/properties/evidence/items/properties/status` | `failed` -> `FAILED`; `missing` -> `MISSING`; `passed` -> `PASSED` |
| `protocol-profile-conformance` `/properties/upstreamSuite/properties/status` | `failed` -> `FAILED`; `not-run` -> `NOT_RUN`; `passed` -> `PASSED` |
| `route-decision` `/allOf/1/if/properties/status` | `escalation_required` -> `ESCALATION_REQUIRED`; `refused` -> `REFUSED` |
| `route-decision` `/properties/status` | `escalation_required` -> `ESCALATION_REQUIRED`; `refused` -> `REFUSED`; `selected` -> `SELECTED` |
| `semantic-mapping-candidate` `/properties/status` | `approved` -> `APPROVED`; `proposed` -> `PROPOSED`; `quarantined` -> `QUARANTINED`; `rejected` -> `REJECTED` |
| `source-mutation-receipt` `/properties/state` | `already-executed` -> `ALREADY_EXECUTED`; `compensated` -> `COMPENSATED`; `executed` -> `EXECUTED`; `failed` -> `FAILED`; `recovered` -> `RECOVERED` |

Schema pointers under `$defs` document the observed reusable schema location.
Only unambiguous document locations are materialized in
`/spec/normalizedStates`; all state mappings remain published in
`compatibility/data-harness-v1/mappings.json`.

## Deprecation and intentional losses

`data.harness/v1` is supported by release `0.1.0` throughout the `0.x` series.
Removal is not permitted before `1.0.0` and requires at least 180 days' notice.
Every conversion reports both warning codes:

- `LEGACY_DATA_HARNESS_V1_DEPRECATED`
- `MIGRATE_TO_HARNESS_PLANEON_AI_V1ALPHA1`

Canonical-to-legacy restoration reports, rather than hides, two intentional
omissions:

- `CANONICAL_COMPATIBILITY_METADATA_NOT_EMITTED_TO_LEGACY`: `/metadata` is
  canonical provenance, not a legacy field.
- `CANONICAL_STATE_VIEW_NOT_EMITTED_TO_LEGACY`: derived normalized state views
  are not written into legacy JSON.

Neither omission changes the recovered legacy document. Every committed vector
must report `legacyRoundTrip: EXACT`.

## Migration procedure

1. Keep the existing legacy validator at the ingestion boundary for nested and
   domain-specific constraints.
2. Select the exact contract slug from the published mapping document.
3. Call `convert_legacy_document(contract, document)` and persist or transmit
   the canonical envelope, not an unlabelled payload.
4. Treat any `CompatibilityError` as a fail-closed refusal. Do not retry with a
   guessed contract or discard provenance fields.
5. During coexistence, call `restore_legacy_document(envelope)` only for a
   consumer that still requires `data.harness/v1`; record its warnings and
   intentional-loss report.
6. Remove the restore step after all consumers accept the canonical envelope.

Before release, verify the complete committed vector set offline:

```console
harnessctl compatibility check tests/fixtures/compatibility
```

The command emits a canonical digest-only report. It never emits tenant payload
content, contacts a network, downloads a dependency, or asserts deployment,
runtime, assurance, or tenant-acceptance state.

## Rollback

Disable the optional conversion call and continue presenting the unchanged
legacy document to the legacy consumer. Do not alter canonical v1alpha1
contracts, delete legacy data, or weaken validation. A rollback removes only
the adapter path; it does not convert any evidence state into acceptance.
