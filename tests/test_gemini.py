"""Gemini adapter tests against a mocked Generative Language API.

The mock enforces the rules that break hand-written Gemini integrations in
production: every model turn must replay the exact thought signature Gemini
issued on its first function call, every function call needs a matching
function response, ids Gemini issued must be echoed, and tools must be declared
with parametersJsonSchema. A request that violates any rule gets the same 400 the
real API returns, so these tests fail the way production would.
"""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest
from app.config import ConfigError, Settings
from app.llm import GEMINI_DUMMY_SIGNATURE, GeminiLLM, LLMError, make_llm, to_gemini
from app.runtime import Runtime
from app.store import Store

KEY = "test-gemini-key"
REASON = "Deploy v2.14.0 set DB_POOL_SIZE 50 -> 5; logs show pool exhaustion timeouts"

SCRIPT = [  # (text, [(name, args)]) — what "Gemini" decides on each step
    (
        "Planning, then reading the alert.",
        [
            ("update_working_memory", {"plan": ["Read alert", "Check deploys and logs", "Fix", "Verify"]}),
            ("get_alert", {}),
        ],
    ),
    (
        "Checking deploys and logs in parallel.",
        [
            ("get_recent_deploys", {"service": "checkout-service"}),
            ("search_logs", {"service": "checkout-service", "query": "error pool", "limit": 20}),
        ],
    ),
    (
        "The pool-size change explains the errors. Proposing a rollback.",
        [
            (
                "rollback_deploy",
                {"service": "checkout-service", "to_version": "v2.13.2", "reason": REASON, "confidence": 0.9},
            ),
        ],
    ),
    ("Verifying.", [("query_metrics", {"service": "checkout-service", "metric": "error_rate", "window_minutes": 30})]),
    (
        "Recovered.",
        [
            (
                "finish",
                {
                    "summary": "Rolled back checkout-service; errors at baseline.",
                    "root_cause": "DB_POOL_SIZE reduced from 50 to 5 in v2.14.0 exhausted the connection pool.",
                    "resolved": True,
                    "fix_applied": "rollback_deploy(checkout-service, v2.13.2)",
                },
            )
        ],
    ),
]


class StrictGemini:
    """A fake Gemini endpoint that validates requests like the real one."""

    def __init__(self, script=SCRIPT, faults: dict[int, httpx.Response] | None = None):
        self.script = script
        self.faults = dict(faults or {})
        self.issued: list[str] = []  # signatures handed out, in order
        self.requests: list[dict] = []
        self.calls = 0

    def _reject(self, msg: str) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": msg}})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.calls in self.faults:
            return self.faults.pop(self.calls)
        if request.headers.get("x-goog-api-key") != KEY:
            return httpx.Response(403, json={"error": {"message": "API key not valid"}})
        assert request.url.path.endswith(":generateContent")
        body = json.loads(request.content)
        self.requests.append(body)

        if "systemInstruction" not in body:
            return self._reject("missing systemInstruction")
        decls = body["tools"][0]["functionDeclarations"]
        if not all("parametersJsonSchema" in d and "parameters" not in d for d in decls):
            return self._reject("tools must use parametersJsonSchema")

        contents = body["contents"]
        if contents[0]["role"] != "user":
            return self._reject("first content must be from the user")
        seen_sigs, issued_ids = [], set()
        for i, c in enumerate(contents):
            if c["role"] != "model":
                continue
            fcs = [p for p in c["parts"] if "functionCall" in p]
            if fcs:
                sig = fcs[0].get("thoughtSignature")
                if not sig:
                    return self._reject(
                        f"Function call {fcs[0]['functionCall']['name']} in the {i}. content block is missing a thought_signature."
                    )
                seen_sigs.append(sig)
                issued_ids |= {p["functionCall"]["id"] for p in fcs if "id" in p["functionCall"]}
                nxt = contents[i + 1] if i + 1 < len(contents) else None
                frs = [p["functionResponse"] for p in (nxt or {}).get("parts", []) if "functionResponse" in p]
                if nxt is None or nxt["role"] != "user" or len(frs) < len(fcs):
                    return self._reject(f"content {i}: every function call needs a function response")
                if [f["name"] for f in frs[: len(fcs)]] != [p["functionCall"]["name"] for p in fcs]:
                    return self._reject(f"content {i}: function responses out of order")
                for fc_part, f in zip(fcs, frs):
                    want = fc_part["functionCall"].get("id")
                    if want and f.get("id") != want:
                        return self._reject(f"function response for {f['name']} must echo id {want}")
                for f in frs:
                    if "id" in f and f["id"] not in issued_ids:
                        return self._reject(f"unknown function response id {f['id']}")
                    if not isinstance(f["response"], dict):
                        return self._reject("functionResponse.response must be an object")
        if seen_sigs != self.issued[: len(seen_sigs)]:
            return self._reject("thought signatures do not match the ones issued")

        step = len(seen_sigs)
        text, calls = self.script[step]
        sig = f"sig-{step}-{'x' * 24}"
        self.issued.append(sig)
        parts = [{"text": text}]
        for j, (name, args) in enumerate(calls):
            fc = {"name": name, "args": args}
            if step == 0:
                fc["id"] = f"g-{j}"  # some responses carry ids; they must be echoed back
            part = {"functionCall": fc}
            if j == 0:
                part["thoughtSignature"] = sig
            parts.append(part)
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "STOP"}],
                "usageMetadata": {
                    "promptTokenCount": 1000 + 100 * step,
                    "candidatesTokenCount": 60,
                    "thoughtsTokenCount": 40,
                },
                "modelVersion": "gemini-3.5-flash",
            },
        )


def make(tmp_path, mock: StrictGemini, db: str = "g.db"):
    settings = Settings(db_path=str(tmp_path / db), tool_backoff_s=0.01, llm_backoff_s=0.01)
    store = Store(settings.db_path)
    llm = GeminiLLM("gemini-3.5-flash", KEY, 30, transport=httpx.MockTransport(mock))
    return settings, store, Runtime(store, llm, settings)


async def wait_for(store, rid, statuses, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = store.load(rid)
        if st["status"] in statuses:
            return st
        await asyncio.sleep(0.01)
    raise AssertionError(f"status={st['status']} reason={st['status_reason']}")


def test_full_run_on_gemini_replays_thought_signatures(tmp_path):
    async def go():
        faults = {
            2: httpx.Response(429, json={"error": {"message": "quota"}}),
            3: httpx.Response(503, json={"error": {"message": "overloaded"}}),
        }
        mock = StrictGemini(faults=faults)
        _, store, rt = make(tmp_path, mock)
        rid = rt.create_run("db-pool-regression")["run_id"]
        st = await wait_for(store, rid, {"awaiting_approval", "failed"})
        assert st["status"] == "awaiting_approval", st["status_reason"]
        assert st["pending"]["args"]["to_version"] == "v2.13.2"
        rt.approve(rid, actor="priya")
        st = await wait_for(store, rid, {"completed", "failed"})
        assert st["status"] == "completed", st["status_reason"]
        assert st["result"]["resolved"] and st["result"]["sim_resolved"]
        assert st["usage"]["output_tokens"] == 5 * 100  # thinking tokens are billed as output
        assert st["operator_log"][-1]["actor"] == "priya"
        types = [e["type"] for e in store.events_since(rid, 0, 10_000)]
        assert types.count("llm.retry") == 2  # 429 and 503 were retried, not fatal
        # The final request carried every signature Gemini issued, in order.
        last = mock.requests[-1]["contents"]
        sigs = [
            p["thoughtSignature"] for c in last if c["role"] == "model" for p in c["parts"] if "thoughtSignature" in p
        ]
        assert sigs == mock.issued[:-1]

    asyncio.run(go())


def test_signatures_survive_a_server_restart(tmp_path):
    async def go():
        mock = StrictGemini()
        settings, store, rt = make(tmp_path, mock)
        rid = rt.create_run("db-pool-regression")["run_id"]
        await wait_for(store, rid, {"awaiting_approval"})
        # New process: new runtime and HTTP client, same database. Signatures must come from the checkpoint.
        rt2 = Runtime(store, GeminiLLM("gemini-3.5-flash", KEY, 30, transport=httpx.MockTransport(mock)), settings)
        rt2.recover()
        rt2.approve(rid)
        st = await wait_for(store, rid, {"completed", "failed"})
        assert st["status"] == "completed", st["status_reason"]

    asyncio.run(go())


def test_bad_request_fails_the_run_with_a_clear_error_and_is_resumable(tmp_path):
    async def go():
        mock = StrictGemini(faults={1: httpx.Response(400, json={"error": {"message": "Invalid model name"}})})
        _, store, rt = make(tmp_path, mock)
        rid = rt.create_run("db-pool-regression")["run_id"]
        st = await wait_for(store, rid, {"failed"})
        assert "Invalid model name" in st["status_reason"]
        rt.resume(rid)  # e.g. after fixing config; continues from the checkpoint
        await wait_for(store, rid, {"awaiting_approval"})

    asyncio.run(go())


def test_blocked_and_malformed_responses():
    from app.llm import from_gemini

    with pytest.raises(LLMError, match="SAFETY"):
        from_gemini({"promptFeedback": {"blockReason": "SAFETY"}}, "m")
    with pytest.raises(LLMError, match="finishReason=SAFETY"):
        from_gemini({"candidates": [{"content": {"parts": []}, "finishReason": "SAFETY"}]}, "m")
    r = from_gemini({"candidates": [{"content": {"parts": []}, "finishReason": "MALFORMED_FUNCTION_CALL"}]}, "m")
    assert r.tool_calls == [] and "malformed" in r.text  # runtime nudges the model to retry
    r = from_gemini(
        {"candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True}, {"text": "hi"}]}}]}, "m"
    )
    assert r.text == "hi" and r.raw["parts"] == [{"text": "hi"}]  # thought summaries are not replayed


def test_history_from_another_provider_gets_a_placeholder_signature():
    msgs = [
        {"role": "user", "content": "wm"},
        {
            "role": "assistant",
            "text": "",
            "tool_calls": [
                {"id": "toolu_1", "name": "get_alert", "args": {}},
                {"id": "toolu_2", "name": "list_services", "args": {}},
            ],
        },
        {"role": "tool", "tool_call_id": "toolu_1", "name": "get_alert", "content": "{}", "is_error": False},
        {"role": "tool", "tool_call_id": "toolu_2", "name": "list_services", "content": "boom", "is_error": True},
        {"role": "user", "content": "[Operator message] check the db"},
    ]
    c = to_gemini(msgs)
    assert [x["role"] for x in c] == ["user", "model", "user"]
    assert c[1]["parts"][0]["thoughtSignature"] == GEMINI_DUMMY_SIGNATURE
    assert "thoughtSignature" not in c[1]["parts"][1]
    assert "functionResponse" in c[2]["parts"][0] and "id" not in c[2]["parts"][0]["functionResponse"]
    assert c[2]["parts"][1]["functionResponse"]["response"] == {"error": "boom"}
    assert c[2]["parts"][-1] == {"text": "[Operator message] check the db"}


def test_provider_selection_fails_fast(monkeypatch):
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ConfigError, match="GEMINI_API_KEY"):
        make_llm(Settings(llm_provider="gemini"))
    with pytest.raises(ConfigError, match="REQUIRE_LLM"):
        make_llm(Settings(require_llm=True))
    assert make_llm(Settings()).provider == "scripted"
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    llm = make_llm(Settings(gemini_model="gemini-3.5-pro"))
    assert (llm.provider, llm.model) == ("gemini", "gemini-3.5-pro")


def test_settings_validation(monkeypatch):
    monkeypatch.setenv("REQUIRE_LLM", "false")
    monkeypatch.setenv("MAX_STEPS", "40")
    s = Settings.from_env()
    assert s.require_llm is False and s.max_steps == 40
    monkeypatch.setenv("MIN_WRITE_CONFIDENCE", "2")
    with pytest.raises(ConfigError, match="MIN_WRITE_CONFIDENCE"):
        Settings.from_env()
    monkeypatch.setenv("MIN_WRITE_CONFIDENCE", "0.5")
    monkeypatch.setenv("REQUIRE_LLM", "maybe")
    with pytest.raises(ConfigError, match="REQUIRE_LLM"):
        Settings.from_env()


def test_check_llm_script_against_strict_gemini(monkeypatch, capsys):
    import scripts.check_llm as check

    mock = StrictGemini()
    monkeypatch.setattr(
        check, "make_llm", lambda s: GeminiLLM("gemini-3.5-flash", KEY, 30, transport=httpx.MockTransport(mock))
    )
    assert asyncio.run(check.main()) == 0
    out = capsys.readouterr().out
    assert "PASS" in out and "thought signatures" in out
