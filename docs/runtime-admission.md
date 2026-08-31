# Runtime admission contract profile

`CON-007` publishes source contracts and public interoperability vectors. It does not implement cryptography, persist replay state, make a runtime decision, hold private keys, or produce tenant-acceptance evidence.

## Signed message profile

`RuntimeTrustBundle`, `SignedAdmissionEnvelope`, and `RuntimeAdmissionReceipt` carry a `payload` and a detached `signature`. The signature is Ed25519 over these exact bytes:

```text
UTF8(domain) || 0x00 || RFC8785_JCS(payload)
```

The domains are closed by kind:

| Kind | Domain |
|---|---|
| `RuntimeTrustBundle` | `harness.planeon.ai/runtime-trust-bundle/v1alpha1` |
| `SignedAdmissionEnvelope` | `harness.planeon.ai/runtime-admission/v1alpha1` |
| `RuntimeAdmissionReceipt` | `harness.planeon.ai/runtime-admission-receipt/v1alpha1` |

`signedMessageDigest` is SHA-256 over the complete domain-separated byte string and uses the lower-case `sha256:<hex>` form. The signature value and 32-byte public key use unpadded base64url. The profile is exactly `RFC8785_JCS_ED25519_V1`; algorithm substitution and fallback key search are forbidden.

Signed payloads are the I-JSON subset required by RFC 8785. This version additionally has only ASCII property names, schema-bounded integers, UTC timestamps at whole-second precision, and pattern- or enum-constrained strings. Floats, duplicate properties, non-finite values, Unicode normalization, and unknown members are rejected before signature verification. These restrictions make the committed Python and JavaScript golden bytes identical without weakening RFC 8785.

## Trust and rotation

A bootstrap trust-bundle digest is installed through an out-of-band tenant/platform trust channel. Every later bundle increments `bundleVersion`, names `previousBundleDigest`, and is signed by the exact `TRUST_BUNDLE` key selected by `signature.keyId` from the trusted predecessor bundle. Multiple active keys may overlap for rotation. A verifier never tries another key after the selected key fails.

Each key is Ed25519, time-bounded, purpose-bounded, and in exactly one of `PENDING`, `ACTIVE`, `RETIRED`, or `REVOKED`. Runtime admission requires an `ACTIVE` `RUNTIME_ADMISSION` key. Receipt verification requires the `RUNTIME_RECEIPT` purpose. A revoked key always produces `SIGNER_REVOKED`; it cannot be revived by an older bundle or a still-valid signature. Ordering of timestamps and strictly increasing bundle versions are semantic checks performed by the consuming SDK because JSON Schema cannot compare field values.

## Admission order and denial precedence

Consumers fail closed in this order, returning the first applicable reason:

1. Parse I-JSON and validate the closed schema: `MALFORMED`.
2. Recreate the domain-separated JCS bytes and match `signedMessageDigest`: `DIGEST_MISMATCH`.
3. Select the exact tenant trust bundle and `keyId`: `TENANT_MISMATCH` or `SIGNER_UNKNOWN`.
4. Check key state, purpose, and key validity window: `SIGNER_REVOKED`, `SIGNER_NOT_ACTIVE`, or `KEY_PURPOSE_MISMATCH`.
5. Verify Ed25519: `SIGNATURE_INVALID`.
6. Check envelope `notBefore` and `expiresAt`: `ENVELOPE_NOT_YET_VALID` or `ENVELOPE_EXPIRED`.
7. Apply the atomic idempotency/replay procedure below.
8. Compare every observed budget dimension with its bound: `BUDGET_EXCEEDED`.

An admitted request produces a signed receipt with `reasonCode: null` and immutable budget/replay digests. A denied request produces a signed receipt with one closed reason. A receipt is evidence of the admission decision only; it is not execution, deployment, assurance, or tenant-acceptance evidence.

## Replay and idempotency

Raw idempotency keys and raw nonces never enter `ReplayRecord`. Before storage, the consumer computes:

```text
idempotencyKeyDigest = SHA256(UTF8(raw idempotency key))
nonceDigest          = SHA256(base64url-decoded nonce)
replayKeyDigest      = SHA256(RFC8785_JCS({"nonceDigest": nonceDigest, "organizationId": organizationId}))
```

The persistence adapter must atomically reserve both `(organizationId, idempotencyKeyDigest)` and `(organizationId, replayKeyDigest)`. An existing idempotency record with the same `requestDigest` may return its already committed signed receipt. The same idempotency digest with another request is `IDEMPOTENCY_CONFLICT`. With no idempotency match, an existing replay key is `REPLAY_DETECTED`. Reservation races fail closed; process-local caches are not authoritative.

## Budget consumption

`BudgetConsumption.limits` mirrors the immutable `ExecutionBudget` selected by `budgetDigest`. `observed` is the admission-time projected total, including the proposed operation. Any observed value greater than its matching limit sets `decision: OVER_BUDGET`, lists every exceeded dimension, and denies with `BUDGET_EXCEEDED`. Equality is within budget. No dimension may be omitted, silently clamped, or replenished by retrying with a new nonce.

## Interoperability vectors

`tests/fixtures/runtime/interoperability-vectors.json` contains public test-only Ed25519 material, exact JCS payload bytes, their domain-separated digest, and closed expected outcomes. It intentionally contains no private key or production identifier. The downstream SDK packet must verify the valid trust/envelope/receipt signatures and deny all mutation vectors byte-identically in Python and TypeScript.
