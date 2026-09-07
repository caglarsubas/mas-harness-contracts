"""Independent normative-vector checks, not a runtime service or auth verifier."""
from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from typing import Any

from tests.model.schema_support import validator

PREFIX = "schemas/v1alpha1/model/"
ENDPOINTS = {
    "chat": "/v1/chat/completions", "completion": "/v1/completions",
    "response": "/v1/responses", "embedding": "/v1/embeddings", "rerank": "/v1/rerank",
}
ERRORS = {
    "MALFORMED_JSON": (400, "invalid_request_error"),
    "INVALID_REQUEST": (422, "invalid_request_error"),
    "UNSUPPORTED_CAPABILITY": (422, "invalid_request_error"),
    "UNAUTHENTICATED": (401, "authentication_error"),
    "FORBIDDEN": (403, "permission_error"), "MODEL_NOT_FOUND": (404, "not_found_error"),
    "QUEUE_FULL": (429, "rate_limit_error"), "BACKEND_UNAVAILABLE": (503, "server_error"),
    "DEADLINE_EXCEEDED": (504, "server_error"), "INTERNAL_ERROR": (500, "server_error"),
    "CANCELLED": (None, "cancelled_error"),
}


def require(condition: bool) -> None:
    if not condition:
        raise ValueError("contract vector rejected")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def bounded(value: Any, depth: int = 0) -> None:
    require(depth <= 16)
    if isinstance(value, float):
        require(math.isfinite(value))
    if isinstance(value, str):
        value.encode("utf-8", errors="strict")
    if isinstance(value, dict):
        for key, child in value.items():
            bounded(key, depth + 1)
            bounded(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            bounded(child, depth + 1)


def decode(raw: bytes) -> Any:
    require(type(raw) is bytes and 0 < len(raw) <= 1048576 and not raw.startswith(b"\xef\xbb\xbf"))
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    bounded(value)
    return value


@lru_cache(maxsize=None)
def schema(name: str):
    return validator(PREFIX + name)


def check_schema(name: str, value: Any) -> None:
    bounded(value)
    schema(name).validate(value)


def flat_schema(value: dict) -> None:
    require(set(value["required"]) == set(value["properties"]))
    require(len(value["required"]) == len(set(value["required"])))
    for prop in value["properties"].values():
        if prop["type"] == "integer":
            require(prop["minimum"] <= prop["maximum"])


def structured_value(spec: dict, raw: str) -> None:
    from jsonschema import Draft202012Validator
    flat_schema(spec)
    Draft202012Validator(spec).validate(decode(raw.encode("utf-8")))


def request(kind: str, value: dict, capabilities: dict | None = None) -> None:
    check_schema(kind + "-request.schema.json", value)
    texts = []
    if kind == "chat":
        pending = None
        seen = set()
        for msg in value["messages"]:
            if msg["role"] == "tool":
                require(pending == msg["tool_call_id"])
                pending = None
            else:
                require(pending is None)
                if "tool_calls" in msg:
                    call = msg["tool_calls"][0]
                    require(call["id"] not in seen)
                    seen.add(call["id"])
                    pending = call["id"]
            if msg.get("content") is not None:
                texts.append(msg["content"])
        require(pending is None)
        fmt = value.get("response_format", {"type": "text"})
        if fmt["type"] == "json_schema":
            require(not value.get("stream", False))
            flat_schema(fmt["json_schema"]["schema"])
        for tool in value.get("tools", []):
            flat_schema(tool["function"]["parameters"])
    elif kind == "completion":
        texts = [value["prompt"]]
    elif kind == "response":
        texts = ([value["input"]] if isinstance(value["input"], str)
                 else [p["text"] for item in value["input"] for p in item["content"]])
        fmt = value.get("text", {}).get("format", {"type": "text"})
        if fmt["type"] == "json_schema":
            require(not value.get("stream", False))
            flat_schema(fmt["schema"])
    elif kind == "embedding":
        texts = [value["input"]] if isinstance(value["input"], str) else value["input"]
    elif kind == "rerank":
        texts = [value["query"], *value["documents"]]
        require(value.get("top_n", 1) <= len(value["documents"]))
    require(sum(len(t) for t in texts) <= 131072)
    if capabilities is not None:
        require(ENDPOINTS[kind] in capabilities["endpoints"])
        require(not value.get("stream", False) or capabilities["streaming"])
        require(not value.get("tools") or capabilities["tools"])
        fmt = value.get("response_format", value.get("text", {}).get("format", {"type": "text"}))
        require(fmt["type"] != "json_schema" or capabilities["structured_output"])
        limit = value.get("max_completion_tokens", value.get("max_tokens", value.get("max_output_tokens", 1024)))
        if kind in {"chat", "completion", "response"}:
            require(limit <= capabilities["max_output_tokens"])
        if kind == "embedding":
            require(capabilities["embedding_dimensions"] is not None)
            require(value.get("dimensions", capabilities["embedding_dimensions"]) == capabilities["embedding_dimensions"])


def totals(value: dict | None, kind: str = "chat") -> None:
    if value is None:
        return
    if kind in {"embedding", "rerank"}:
        require(value["prompt_tokens"] == value["total_tokens"])
    elif kind == "response":
        require(value["input_tokens"] + value["output_tokens"] == value["total_tokens"])
    else:
        require(value["prompt_tokens"] + value["completion_tokens"] == value["total_tokens"])


def response(kind: str, req: dict, value: dict) -> None:
    request(kind, req)
    check_schema(kind + "-response.schema.json", value)
    require(value["model"] == req["model"])
    totals(value["usage"], kind)
    if kind == "embedding":
        size = 1 if isinstance(req["input"], str) else len(req["input"])
        require([r["index"] for r in value["data"]] == list(range(size)))
        # Fixture context explicitly supplies the already validated route dimension.
        require("dimensions" in req)
        require(all(len(row["embedding"]) == req["dimensions"] for row in value["data"]))
    elif kind == "rerank":
        rows = value["results"]
        require(len(rows) == req.get("top_n", 1))
        require(len({r["index"] for r in rows}) == len(rows))
        require(all(r["index"] < len(req["documents"]) for r in rows))
        require(rows == sorted(rows, key=lambda r: (-r["relevance_score"], r["index"])))
    elif kind == "chat":
        choice = value["choices"][0]
        msg = choice["message"]
        require((choice["finish_reason"] == "tool_calls") == ("tool_calls" in msg))
        mode = req.get("tool_choice", "auto" if req.get("tools") else "none")
        if "tool_calls" in msg:
            require(mode != "none" and len(req.get("tools", [])) == 1)
            tool = req["tools"][0]["function"]
            call = msg["tool_calls"][0]["function"]
            require(call["name"] == tool["name"])
            structured_value(tool["parameters"], call["arguments"])
        else:
            require(mode != "required")
        fmt = req.get("response_format", {"type": "text"})
        if fmt["type"] == "json_schema":
            require(choice["finish_reason"] == "stop")
            structured_value(fmt["json_schema"]["schema"], msg["content"])
    elif kind == "response":
        status = value["status"]
        if status in {"completed", "incomplete"}:
            require(len(value["output"]) == 1 and len(value["output"][0]["content"]) == 1)
            require(value["output"][0]["status"] == status)
            require(value["error"] is None)
            require(value["incomplete_details"] == (None if status == "completed" else {"reason": "max_output_tokens"}))
            fmt = req.get("text", {}).get("format", {"type": "text"})
            if fmt["type"] == "json_schema":
                require(status == "completed")
                structured_value(fmt["schema"], value["output"][0]["content"][0]["text"])
        elif status == "failed":
            require(not value["output"] and value["error"] is not None and value["incomplete_details"] is None)
        elif status == "in_progress":
            require(not value["output"] and value["usage"] is value["error"] is value["incomplete_details"] is None)
        else:
            require(not value["output"] and value["error"] is None and value["incomplete_details"] is None)


def observation(v: dict) -> None:
    check_schema("usage-observation.schema.json", v)
    fields = [v[k] for k in ("organizationId", "admissionDigest", "requestDigest", "releaseDigest", "policyDigest", "budgetDigest")]
    require(all(x is None for x in fields) or all(x is not None for x in fields))
    if all(x is None for x in fields):
        require(v["state"] == "REJECTED" and v["measurement"] == "UNAVAILABLE" and v["model"] is None)
    else:
        require(v["model"] is not None)
    known = [v["inputTokens"] is not None, v["outputTokens"] is not None]
    if v["measurement"] == "MEASURED":
        require(all(known) and v["totalTokens"] == v["inputTokens"] + v["outputTokens"])
    elif v["measurement"] == "PARTIAL":
        require(sum(known) == 1 and v["totalTokens"] is None)
    else:
        require(not any(known) and v["totalTokens"] is None and v["cachedTokens"] is None)
    if v["cachedTokens"] is not None:
        require(v["inputTokens"] is not None and v["cachedTokens"] <= v["inputTokens"])
    if v["firstByteMs"] is not None:
        require(v["durationMs"] is not None and v["firstByteMs"] <= v["durationMs"])
    state, reason = v["state"], v["reason"]
    require((state == "COMPLETED") == (reason is None))
    if state == "CANCELLED":
        require(reason == "CANCELLED")
    elif state == "TIMED_OUT":
        require(reason == "DEADLINE_EXCEEDED")
    elif state == "FAILED":
        require(reason in {"INTERNAL_ERROR", "BACKEND_UNAVAILABLE"})
    elif state == "REJECTED":
        require(reason in set(ERRORS) - {"CANCELLED", "DEADLINE_EXCEEDED", "INTERNAL_ERROR"})
    if v["endpoint"] in {"/v1/embeddings", "/v1/rerank"} and v["outputTokens"] is not None:
        require(v["outputTokens"] == 0)


def lifecycle(v: dict) -> None:
    check_schema("lifecycle-trace.schema.json", v)
    state, first_byte, previous, queue_start = None, False, -1, None
    terminal = {"COMPLETED", "CANCELLED", "TIMED_OUT", "REJECTED", "FAILED"}
    for e in v["events"]:
        require(e["requestId"] == v["requestId"] and e["atMs"] >= previous and state not in terminal)
        action = e["action"]
        require(action not in {"RETRY", "SWITCH_PROVIDER"})
        elapsed = e["atMs"]
        expired = elapsed >= v["timeoutMs"] or (state == "QUEUED" and elapsed - queue_start >= 10000)
        if expired:
            require(action == "TIMEOUT")
        if action == "QUEUE":
            require(state is None and v["queuedAhead"] < v["queueCapacity"])
            state, queue_start = "QUEUED", elapsed
        elif action == "START":
            require(state == "QUEUED" and not expired)
            state = "RUNNING"
        elif action == "FIRST_BYTE":
            require(state == "RUNNING" and not first_byte)
            first_byte = True
        elif action == "COMPLETE":
            require(state == "RUNNING" and not expired)
            state = "COMPLETED"
        elif action == "REJECT":
            require(state in {None, "QUEUED"})
            state = "REJECTED"
        elif action == "TIMEOUT":
            require(state in {"QUEUED", "RUNNING"} and expired)
            state = "TIMED_OUT"
        elif action in {"CANCEL", "FAIL"}:
            require(state in {"QUEUED", "RUNNING"})
            state = "CANCELLED" if action == "CANCEL" else "FAILED"
        else:
            raise ValueError("unknown lifecycle action")
        require(e["state"] == state)
        previous = elapsed
    require(state in terminal)


def frames(raw: str, request_id: str, named: bool) -> list:
    require(len(raw.encode("utf-8")) <= 8388608 and raw.endswith("\n\n") and "\r" not in raw)
    result = []
    for i, frame in enumerate(raw[:-2].split("\n\n")):
        require(len(frame.encode("utf-8")) <= 1048576)
        lines = frame.split("\n")
        require(len(lines) == (3 if named else 2))
        offset = 1 if named else 0
        require(lines[offset] == f"id: {request_id}:{i}" and lines[offset + 1].startswith("data: "))
        data = lines[offset + 1][6:]
        value = data if data == "[DONE]" else decode(data.encode("utf-8"))
        if named:
            require(isinstance(value, dict) and lines[0] == "event: " + value["type"])
            require(value["sequence_number"] == i)
        result.append(value)
    return result


def stream(kind: str, raw: str, request_id: str, include_usage: bool = True) -> None:
    values = frames(raw, request_id, kind == "response")
    if kind == "response":
        response_stream(values, request_id)
        return
    require(kind in {"chat", "completion"} and values[-1] == "[DONE]" and values.count("[DONE]") == 1)
    content = values[:-1]
    require(bool(content))
    finished = error_seen = usage_seen = False
    identity = None
    for i, v in enumerate(content):
        if "error" in v:
            check_schema("error.schema.json", v)
            require(not finished and not error_seen and i == len(content) - 1)
            error_seen = True
            continue
        check_schema(kind + "-chunk.schema.json", v)
        require(not error_seen and not usage_seen and v["id"] == request_id)
        current = (v["model"], v["created"])
        identity = current if identity is None else identity
        require(current == identity)
        if not v["choices"]:
            require(finished and include_usage and i == len(content) - 1)
            totals(v["usage"])
            usage_seen = True
            continue
        require(not finished)
        choice = v["choices"][0]
        if choice["finish_reason"] is not None:
            require(kind != "chat" or i > 0)
            finished = True
        elif kind == "chat":
            if i == 0:
                require(choice["delta"] == {"role": "assistant", "content": ""})
            else:
                require(set(choice["delta"]) == {"content"})
    require(error_seen or (finished and usage_seen == include_usage))


def response_stream(values: list, request_id: str) -> None:
    require(len(values) >= 2)
    for v in values:
        check_schema("response-event.schema.json", v)
    require(values[0]["type"] == "response.created")
    identity = (request_id, values[0]["response"]["model"], values[0]["response"]["created_at"])
    for v in values:
        if "response" in v:
            r = v["response"]
            require((r["id"], r["model"], r["created_at"]) == identity)
            response("response", {"model": r["model"], "input": "fixture"}, r)
    terminal = values[-1]["type"]
    if terminal in {"response.failed", "error"}:
        require(len(values) <= 3 and values[0]["response"]["status"] == "in_progress")
        if len(values) == 3:
            require(values[1]["type"] == "response.in_progress")
        if terminal == "response.failed":
            require(values[-1]["response"]["status"] == "failed")
        return
    require(terminal in {"response.completed", "response.incomplete"})
    types = [v["type"] for v in values]
    require(types[:4] == ["response.created", "response.in_progress", "response.output_item.added", "response.content_part.added"])
    require(types[-4:] == ["response.output_text.done", "response.content_part.done", "response.output_item.done", terminal])
    require(all(t == "response.output_text.delta" for t in types[4:-4]))
    require(values[0]["response"]["status"] == values[1]["response"]["status"] == "in_progress")
    added = values[2]["item"]
    require(added["status"] == "in_progress" and added["content"] == [])
    item_id = added["id"]
    require(values[3]["part"] == {"type": "output_text", "text": "", "annotations": []})
    for v in values[3:-2]:
        require(v["item_id"] == item_id)
    text = "".join(v["delta"] for v in values[4:-4])
    require(values[-4]["text"] == text and values[-3]["part"]["text"] == text)
    final_item = values[-2]["item"]
    require(final_item["id"] == item_id and final_item["content"] == [values[-3]["part"]])
    r = values[-1]["response"]
    expected = "completed" if terminal == "response.completed" else "incomplete"
    require(r["status"] == final_item["status"] == expected and r["output"] == [final_item])


def error_vector(v: dict) -> None:
    check_schema("error.schema.json", v["body"])
    code = v["body"]["error"]["code"]
    require((v["status"], v["body"]["error"]["type"]) == ERRORS[code])
    if code == "QUEUE_FULL":
        require(type(v["retryAfter"]) is int and 1 <= v["retryAfter"] <= 60)
    else:
        require(v["retryAfter"] is None)


def binding_vector(v: dict) -> None:
    """Check digest relationships with an explicit simulated verifier precondition.

    This function is NOT signature verification and MUST NOT be used for admission.
    """
    b, p, ctx = v["binding"], v["envelopePayload"], v["verifiedContext"]
    check_schema("request-binding.schema.json", b)
    require(ctx["signatureStatus"] == "VERIFIED_BY_CON007" and ctx["reservationStatus"] == "NEW_ATOMIC_RESERVATION")
    require(p["operation"] == "MODEL_INFERENCE")
    for key in ("organizationId", "subjectDigest", "releaseDigest", "policyDigest", "budgetDigest"):
        require(b[key] == p[key] == ctx[key])
    require(b["method"] == v["method"] and b["path"] == v["path"])
    body = v["rawBody"].encode("utf-8")
    decode(body)
    require(b["bodySha256"] == "sha256:" + hashlib.sha256(body).hexdigest())
    canonical = json.dumps(b, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    require(v["expectedCanonicalBinding"] == canonical.decode("utf-8"))
    require(p["requestDigest"] == "sha256:" + hashlib.sha256(canonical).hexdigest())
    require(ctx["nowUnixMs"] < b["deadlineUnixMs"] <= min(ctx["expiresUnixMs"], ctx["nowUnixMs"] + min(ctx["maxTaskSeconds"] * 1000, 300000)))
    require(ctx["inputTokenUpperBound"] + ctx["outputTokenLimit"] <= ctx["remainingModelTokens"])


def metrics(raw: str) -> None:
    import re
    require(0 < len(raw.encode("utf-8")) <= 65536 and raw.endswith("\n"))
    lines = raw.splitlines()
    require(len(lines) <= 256 and len(set(lines)) == len(lines))
    seen = set()
    for line in lines:
        match = re.fullmatch(r'(harness_model_queue_depth|harness_model_requests_total\{endpoint="(/v1/(chat/completions|completions|responses|embeddings|rerank))",state="(QUEUED|RUNNING|COMPLETED|CANCELLED|TIMED_OUT|REJECTED|FAILED)"\}) ([0-9]+)', line)
        require(match is not None)
        key, value = line.rsplit(" ", 1)
        require(key not in seen)
        seen.add(key)
        require(int(value) <= (1024 if key == "harness_model_queue_depth" else 9007199254740991))
