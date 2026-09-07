# Model usage compatibility dispositions

Alpha 2 · CON-MODEL-001. This is an independent contract design, not a source
adapter, complete schema reconstruction or compatibility PASS. The source-free
report contains 41 distinct top-level fields plus five conditional observations.
Its exact report bytes and original observation packet are pinned by the model
input lock. All 41 names occur exactly once below and in the independent mapping
fixture. Conditional identity facts are explicitly omitted/unsupported with their
corresponding fields; they confer no tenant identity or signature authority.

MAPPED means conceptual design correspondence only, subject to the destination
rules and verified context in [model-api.md](model-api.md). It never authorizes
copying a legacy value or claims matching source runtime behavior. OMITTED means
no automatic transfer; UNSUPPORTED means the capability itself is unavailable.

| Observed field | Disposition | Destination | Rationale |
| --- | --- | --- | --- |
| backend | OMITTED | — | Backend identities and addresses are operational detail, not public telemetry. |
| cached_tokens | MAPPED | cachedTokens | Known cached count is a subset of measured input; absent remains null. |
| cost_micros | UNSUPPORTED | — | This zero-bill profile has no cost or authoritative financial accounting field. |
| denial_code | MAPPED | reason | Independent closed reasons require verified destination classification; no literal conversion is inferred. |
| duration_ms | MAPPED | durationMs | Independent integer milliseconds, bounded and nullable; source numeric semantics are not assumed. |
| engine_request_id | OMITTED | — | Do not trust a legacy request identity; requestId originates in signed destination binding. |
| error_type | OMITTED | — | Destination reason is sanitized and closed; legacy free text is not exposed. |
| event | MAPPED | event | Destination constant is model.usage.observed.v1, not the historical vendor marker. |
| fallback | UNSUPPORTED | — | Retry and provider switching are not supported in this profile. |
| fallback_from_backend | UNSUPPORTED | — | No provider fallback and no backend identity disclosure. |
| fallback_from_model | UNSUPPORTED | — | No model fallback. |
| fallback_reason | UNSUPPORTED | — | No fallback or free-text operational reason. |
| finish_reason | OMITTED | — | Wire finish reasons and terminal observation state are separate; no source mapping is assumed. |
| http_status | OMITTED | — | HTTP error mapping is transport-specific; disconnect is not an invented response status. |
| input_token_upper_bound | MAPPED | inputTokenUpperBound | Admission bound remains separate from observed measured counts. |
| input_tokens | MAPPED | inputTokens | Only reported measurements; null never becomes an estimate or zero. |
| key_id | OMITTED | — | The unchanged signed admission object carries verifier identity; public usage must not leak keys. |
| model_attempt_id | UNSUPPORTED | — | No retries or source attempt identity import. |
| model_invocation_id | OMITTED | — | Legacy correlation has no authority; signed destination requestId is independent. |
| operation | MAPPED | endpoint | Independent closed inference endpoint; arbitrary legacy operation strings are not accepted. |
| org_id | OMITTED | — | organizationId is established only by destination authentication and signed admission, never telemetry. |
| outcome | MAPPED | state | Independent terminal state; nullable historical outcome does not establish runtime success. |
| output_token_budget | MAPPED | outputTokenLimit | Requested/reserved bound is not measured output. |
| output_tokens | MAPPED | outputTokens | Only known measurements; zero for non-generative operations requires measured semantics. |
| policy_digest | MAPPED | policyDigest | Only the verified admission/selected route digest is emitted; not a copied source assertion. |
| policy_id | OMITTED | — | Digest binding suffices; no mutable policy alias. |
| pricing_digest | UNSUPPORTED | — | No pricing or billable provider integration. |
| request_key_source | OMITTED | — | No raw request key or credential-source data in observations. |
| requested_model | MAPPED | model | Only the verified requested local tenant alias; no external lookup or source equivalence. |
| resolved_model | OMITTED | — | No backend resolution identity or fallback disclosure. |
| route | MAPPED | endpoint | Allowlisted API path only; arbitrary route text is not imported. |
| route_id | OMITTED | — | Verified immutable releaseDigest binds routing; telemetry route IDs are not authority. |
| runtime_request_id | OMITTED | — | Destination correlation comes from request-binding authority, not legacy external identity. |
| schema | MAPPED | schemaVersion | Independent harness.planeon.ai/model-usage-observation/v1alpha1 identifier. |
| span_id | OMITTED | — | No source span identity accepted as destination correlation or metric label. |
| stream | MAPPED | stream | Verified request mode, not inferred from source behavior. |
| tenant | OMITTED | — | No conflicting tenant alias; destination organizationId is authenticated. |
| timestamp | MAPPED | recordedAt | Destination terminal timestamp under its own UTC profile; source format facts are not runtime evidence. |
| trace_id | OMITTED | — | No source trace identity propagation or external telemetry. |
| ttft_ms | MAPPED | firstByteMs | Measured first-byte timing, not assumed first-token equivalence; nullable integer duration. |
| usage_record_id | OMITTED | — | Destination observationId is independently issued for idempotent observation handling. |

Destination-only measurement provenance, request/admission/release/budget digests,
terminal state, deduplication and ledgerAuthority=false are explicit independent
requirements. Nullable source properties do not establish measured values.
Unreported usage stays null, bounds stay separate, stream totals are counted once,
and authoritative budget/ledger changes remain outside this observation schema.

Original source tests: NOT_RUN_ENV_UNAVAILABLE. Original source behavioral parity:
NOT_ESTABLISHED. Source execution: DENIED. Copy authority: NONE. Destination
fixture conformance becomes PASS only after the full declared offline run; source,
CI, merge, native Linux, artifact, deployment, runtime and tenant gates are separate.
