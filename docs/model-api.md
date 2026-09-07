# Local model API contract — CON-MODEL-001

Phase: Alpha 2. This publication defines a bounded, independently authored
v1alpha1 text profile for MODEL-001. It is not a server, cryptographic verifier,
model artifact, benchmark, native Linux qualification or tenant acceptance.
The source checkpoint has no predeclared local/CI/merge result; exact results
belong to the matching PR and external signed-runner archive.

## Authority and compatibility

The immutable model input lock binds meta f8137eab6acfa8b13051f1c4e548854fc7dc934f,
CON-007, the corrected CON-FIX-001 baseline and the structural observation.
All 758 predecessor test identities and wire bytes are retained. The only
legacy test change is MET-REPAIR-005's exact fixture-copy helper replacement.
No warm checkout, source code, original tests or private keys are consumed.

This is a **partial wire-compatible subset**, not blanket OpenAI SDK or behavioral
equivalence. [Chat fields](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
[stream families](https://developers.openai.com/api/docs/guides/streaming-responses),
[embeddings](https://developers.openai.com/api/reference/resources/embeddings/methods/create)
and [legacy completions](https://developers.openai.com/api/reference/cli/resources/completions)
are research references only. Their retrieval provenance is pinned locally.
Bounds, errors, admission, null usage and rerank below are independently defined
Planeon restrictions/extensions. No referenced website is fetched at generation,
validation or runtime. No OpenAI account, hosted endpoint or API key is needed.

## Endpoints and selected capabilities

| Endpoint | Supported v1alpha1 profile |
| --- | --- |
| GET /v1/models | At most 256 distinct authorized local model IDs, lexically sorted; owned_by=local; no hosted discovery or cross-organization model names |
| POST /v1/chat/completions | Text system/developer/user/assistant messages, single function proposal or tool-result history, one choice; text streaming; optional non-streaming flat structured output |
| POST /v1/completions | One string prompt and one text choice; optional text streaming |
| POST /v1/responses | Stateless text input/output only, one assistant message/one output_text part; store=false; distinct semantic stream events |
| POST /v1/embeddings | One string or 1–128 strings; float vectors only; optional declared dimension |
| POST /v1/rerank | Query, 1–128 strings, top_n; distinct indices ranked by descending score and ascending index on ties; no document echo |
| GET /healthz | Authenticated local liveness only, {status:alive} |
| GET /readyz | Authenticated readiness: 200 ready or 503 not_ready with a closed reason; liveness does not imply readiness |
| GET /metrics | Authorized local operator only; bounded content-free Prometheus text; no external exporter configuration |

All routes require a verified locally managed workload identity over mutual TLS.
Tenant routes additionally require organization/model authorization; metrics
requires a distinct operator permission. No unauthenticated probe exemption is
implicitly introduced. Any deployment-specific probe adapter is a later concern.
Inference also requires the existing CON-007 signed admission below. No activation,
administration, background job, response retrieval, delete or cancellation endpoint
is introduced. Clients cancel by disconnecting; server deadlines also cancel.

Unknown members and explicit nulls fail unless the exact schema permits them.
Omitted stream=false, temperature=1, output-token maximum=1024, n=1,
parallel_tool_calls=false, store=false, encoding_format=float and top_n=1.
Defaults are applied only after validating and binding the original body bytes;
they never silently widen a signed budget. stream_options requires stream=true
and include_usage=true. Omission requests no separate usage chunk.

Limits are hard upper bounds, not capacity or performance promises: raw UTF-8
JSON <=1 MiB, depth <=16, at most 128 messages/inputs/documents, each text <=32768
Unicode scalar values, total input text <=131072 scalar values; output <=262144
scalar values; serialized non-stream output and complete SSE <=8 MiB. Reject
duplicate JSON keys, unpaired surrogates, BOM, non-finite numbers, trailing content
and invalid UTF-8 before schema validation. All nested objects are closed except
the intentionally bounded property-name map in the flat structured schema.
Route tokenization and signed maxModelTokens impose additional lower limits;
input plus reserved output must fit both route context and the signed budget.
Never truncate inputs, clamp a request or downgrade its capabilities silently.

Model capability metadata is derived from an already authorized local release;
it does not authorize a route itself. Requested endpoint, streaming, tools,
structured output and embedding dimension must be supported by that exact model.
All model IDs are tenant-scoped aliases, not filesystem paths or URLs; do not
interpret slash-containing IDs as paths or trigger downloads.

## Structured output and tools

Only a flat closed object with 1–32 named scalar properties is supported. Each
property is string with a required maxLength <=4096, bounded integer within
[-1000000,1000000], or boolean. required must equal the complete property-name
set, without duplicates; integer minimum <= maximum. Remote/local $ref, recursion,
arrays, arbitrary nested schemas and extra keywords are rejected, not fetched.
Validate the final JSON value against the declared schema before publishing a
successful result. Structured output is non-streaming in this profile; reject
stream=true with json_schema before queueing. No partial unvalidated structure
is exposed as a success. Token-limit truncation of structured output fails with
INTERNAL_ERROR rather than returning invalid JSON under a success claim.

Chat may propose at most one function from its single declared strict tool.
tool_choice defaults to auto with a tool, otherwise none. required must produce
that function; none must produce text. Function arguments are bounded JSON text
and must validate against the same flat schema; finish_reason=tool_calls exactly
when a tool proposal is returned. Tool IDs must be unique and a tool-result
message must immediately resolve the preceding matching assistant proposal;
orphan/duplicate/unresolved history is invalid. A tool name must match the declared
tool. Tools and structured output cannot be combined, and tool proposals cannot
stream in this profile. Merely proposing a function never executes it or grants
tool permission. Responses function/file/image/audio/reasoning items, hosted
tools, URLs, storage, previous_response_id, background mode, multimodal content,
logprobs, multiple choices, base64 embeddings and provider fallback are unsupported.

## Admission and request binding

Transport headers X-Harness-Admission and X-Harness-Binding carry unpadded
base64url UTF-8 JSON, each <=32768 characters. They are **untrusted inputs**,
not authority flags. Reject duplicate headers, noncanonical base64url, decoded
oversize data and invalid JSON. The admission value is the unchanged CON-007
SignedAdmissionEnvelope. Binding follows request-binding.schema.json.

For MODEL_INFERENCE, requestDigest = SHA256(RFC8785_JCS(binding)). The binding
contains only bounded ASCII keys/identifiers/digests and an integer deadline;
bodySha256 is SHA256 of the exact received raw JSON body, before normalization
or default application. Thus floats and Unicode in an inference body never
change CON-007's restricted signed-payload profile. There is no new signature
algorithm, envelope or signing domain. Digest equality alone is NOT admission.

Follow docs/runtime-admission.md exactly: authenticate the workload separately;
select its organization trust bundle; validate envelope and verify its real
signature, purpose, revocation and validity; require MODEL_INFERENCE; match
organizationId and subjectDigest to the authenticated identity. Match release,
policy and budget digests to both the signed envelope and the selected immutable
local route. Match method, exact path (no query/alias rewriting), raw body digest,
and the binding digest to the received request and envelope. requestId is an
opaque admission-authority-issued correlation ID bound by that digest, never a
free tenant header. Require deadline after now and no later than envelope expiry,
signed maxTaskSeconds and the 300000 ms hard limit. Apply predecessor atomic
replay/idempotency and projected budget admission before queueing or model access.
A cached admission receipt is not permission to execute inference twice.
Conflicting, unsigned or body-supplied tenant/org/route/budget/identity claims
cannot bypass these checks. Missing verifier, durable reservation or trust fails
closed. This packet's binding vectors exercise relationships only; they do not
pretend to verify signatures or construct new signed interoperability material.

## Request lifecycle and usage

Valid paths are QUEUED -> RUNNING -> COMPLETED/CANCELLED/TIMED_OUT/FAILED;
QUEUED can instead end CANCELLED/TIMED_OUT/REJECTED/FAILED. A request rejected
before queue admission has only REJECTED. Terminal states have no outgoing
transition. Exactly one terminal observation is committed per admitted request.
Queue capacity is <=1024 and <=signed concurrent capacity; full queue rejects
immediately. Queue wait is <=10000 ms and <=remaining deadline. Start only before
both bounds; at exact deadline or queue timeout the outcome is TIMED_OUT. Use a
monotonic clock for elapsed time and a validated UTC clock for signed validity.
Backend completion/deadline/disconnect races use one atomic terminal decision;
at an observed deadline, timeout wins over completion. A disconnect requests
backend cancellation and cannot be reported as successful delivery. Repeated
cancel callbacks cannot create another terminal usage observation. No retries or
provider switching are supported, including before first byte; after first byte
they are always forbidden. Never resume an interrupted stream or silently rerun
it with a fresh request ID or admission nonce.

usage-observation.schema.json is a tenant-neutral, content-free observation,
not authoritative budget consumption or a ledger entry. observationId is stable
for the terminal record; consumers deduplicate by verified organization/request
and observation identity. Repeated same-ID different-content observations are
conflicts, not increments. CON-007 BudgetConsumption stays admission-time
projected usage; only the separately authorized ledger owner can reconcile it.

MEASURED requires inputTokens/outputTokens/totalTokens, sum equality and cached
tokens <=input when known. PARTIAL has at least one known input/output count but
not both; totalTokens=null. UNAVAILABLE has all four token values null. A missing
backend measurement is never zero or an estimate. Bounds are separate fields,
not measured counts. Cached tokens are part of input, not added again. If a wire
API cannot represent partial counters, its usage is null. Embeddings/rerank have
outputTokens=0 only when measured; wire prompt_tokens=total_tokens. Backend
duration/firstByte may be absent; otherwise firstByte<=duration<=deadline limit.
All admitted records require organization and every admission/request/release/
policy/budget digest together; unauthenticated pre-admission REJECTED records have
all those bindings null and no measured model usage. Organization identity is
verified context, never copied from legacy telemetry. Terminal reason is null
only on COMPLETED, CANCELLED requires CANCELLED, timeout requires DEADLINE_EXCEEDED;
REJECTED/FAILED require their appropriate closed reason. No prompt, tool arguments,
backend endpoint, trace labels, secret, cost, price or ledger authority is emitted.

## Streaming

UTF-8 SSE uses LF: optional event line, required id line, and one data line with
compact JSON, then a blank line. id is requestId:sequence, zero-based contiguous
with no duplicates; no retry field, comments, multiline data or reconnection.
Each frame <=1 MiB, complete stream <=8 MiB. Payload model/id/created stay fixed.
A write counts as first byte; subsequent failures cannot change HTTP status or
restart generation. Network truncation/disconnect may prevent delivery of a
terminal frame; record CANCELLED internally and never synthesize a successful
client terminal. Successful and server-error fixture streams require their
defined terminal; missing terminal is an incomplete transport, not success.

Chat: first chunk has assistant role and empty content, then zero or more text
deltas, then exactly one empty delta with stop/length. If include_usage=true,
exactly one choices=[] usage chunk follows; it is a total, never a delta and
may contain null for unavailable usage. All other chunks have usage=null.
The final framing sentinel is data: [DONE], with the next sequence ID. A
post-first-byte error instead sends the closed error object then [DONE], with
no finish or usage success chunk. The sentinel itself is not a second terminal.
Completions use text_completion choices with text instead of chat deltas and
logprobs=null, then empty text with stop/length, optional usage, and [DONE].
Neither family uses Responses event types; tool deltas are unsupported.

Responses: event equals payload.type and sequence_number equals SSE sequence.
For successful text: response.created, response.in_progress,
response.output_item.added, response.content_part.added, zero or more
response.output_text.delta, response.output_text.done,
response.content_part.done, response.output_item.done, then exactly one
response.completed or response.incomplete. Every item_id matches the single
item, all indices are zero, done text equals concatenated deltas, and the final
response embeds that exact item/text. Lifecycle response.id/model/created_at
stay fixed; created/in_progress contain empty output, null error/usage/details.
Added item is in_progress with empty content; added part has empty text.
Completed item/response statuses agree; incomplete uses reason=max_output_tokens
and item.status=incomplete. Terminal usage appears only in the final response.
No [DONE] sentinel is sent for Responses. An error after created/in_progress
may send response.failed with empty output and sanitized nonnull error or one
typed error event, then close; no success terminal can follow it. Cancellation
and transport truncation remain incomplete to the client, with internal terminal
observation. These are explicitly restricted stream shapes, not all upstream events.

## Errors, embeddings and operational safety

| HTTP | code | type |
| --- | --- | --- |
| 400 | MALFORMED_JSON | invalid_request_error |
| 422 | INVALID_REQUEST / UNSUPPORTED_CAPABILITY | invalid_request_error |
| 401 | UNAUTHENTICATED | authentication_error |
| 403 | FORBIDDEN | permission_error |
| 404 | MODEL_NOT_FOUND | not_found_error |
| 429 | QUEUE_FULL | rate_limit_error |
| 503 | BACKEND_UNAVAILABLE | server_error |
| 504 | DEADLINE_EXCEEDED | server_error |
| 500 | INTERNAL_ERROR | server_error |

Authentication/authorization precedes resource lookup to avoid discovery leaks.
Malformed JSON is distinct from parsed schema/semantic invalidity. Unsupported
capabilities never invoke a backend. 429 requires Retry-After integer 1–60
seconds, not permission for an automatic retry. Client disconnect has no fictitious
HTTP 499 response. Errors always use the fixed message and param=null from the
schema; internal detail stays outside the public response and content-free metrics.

Embedding data has exactly one item per input, indices 0..n-1 once in order, each
vector equal to the declared model dimension (or supported requested dimension).
Reject non-finite components and dimension/cardinality mismatches. Rerank top_n
cannot exceed document count; result count equals top_n, each index is distinct
and in range, scores finite in [0,1], sorted by score then index. Neither operation
may invent a measured usage count. Model list capability metadata must agree
with endpoint types; embedding endpoints require a nonnull dimension.

Metrics allows only harness_model_requests_total with endpoint/state labels and
harness_model_queue_depth without labels; numeric values must be finite and
non-negative, counter integral, queue depth integral <=1024, <=256 series and
<=65536 bytes. No organization, model, prompt, request ID, host, trace, custom
label or external telemetry destination. A missing dependency is not ready.

## Release and rollback

Generation adds the model wire files, both model documents, every exact model
fixture, immutable source-free snapshot and lock to the existing manifest. It
requires those inputs unconditionally, verifies the pinned lock and source-free
bytes, and refuses missing/extra/linked inputs. Predecessor APIs remain additive
and every predecessor release entry is retained; only derived index digest changes.
Source contract state remains distinct from artifacts, signatures, deployment,
runtime, assurance and tenant evidence. Linux qualification is still unavailable.
Before consumption revert this additive release as a unit; after consumption
publish a reviewed successor. Never rewrite original evidence or delete model PVCs.

Next: MODEL-001 only after this packet's merge/verification and fresh native Linux
AMD64 baseline PASS. ARM64 and GPU qualification are independent. No phase-end
model-effort transition is due while Alpha 2 remains ongoing.
