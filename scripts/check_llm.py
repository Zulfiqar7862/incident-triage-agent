"""Live smoke test for the configured model provider.

Runs a real two-step tool-calling exchange (call a tool, receive its result,
call another tool), which is the exact pattern that breaks when a provider's
multi-turn requirements (like Gemini thought signatures) aren't met. Uses the
production adapter and tool schemas; no runs are created and nothing is changed.

    python -m scripts.check_llm
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

from app.config import ConfigError, Settings
from app.context import SYSTEM_PROMPT
from app.llm import LLMError, LLMTransientError, make_llm
from app.tools import tool_schemas

ALERT = {
    "id": "ALRT-0001",
    "service": "checkout-service",
    "severity": "P1",
    "status": "firing",
    "title": "checkout-service 5xx error rate above 5%",
}


async def main() -> int:
    try:
        settings = Settings.from_env()
        llm = make_llm(settings)
    except ConfigError as e:
        print(f"FAIL config: {e}")
        return 2
    if llm.provider == "scripted":
        print("FAIL no model configured. Set GEMINI_API_KEY (or ANTHROPIC_API_KEY / OPENAI_API_KEY) in .env.")
        return 2
    print(f"Checking {llm.provider} / {llm.model} ...")
    tools = tool_schemas()
    messages = [{"role": "user", "content": "Connectivity check. Call get_alert now and nothing else."}]

    try:
        t0 = time.perf_counter()
        r1 = await llm.complete(SYSTEM_PROMPT, messages, tools)
        ms1 = int((time.perf_counter() - t0) * 1000)
        names = [c.name for c in r1.tool_calls]
        if "get_alert" not in names:
            print(f"FAIL step 1: expected a get_alert call, got {names or 'no tool calls'}; text={r1.text[:200]!r}")
            return 1
        print(f"  step 1 ok: called {names} ({ms1} ms, {r1.input_tokens} in / {r1.output_tokens} out)")

        assistant = {
            "role": "assistant",
            "text": r1.text,
            "tool_calls": [{"id": c.id, "name": c.name, "args": c.args} for c in r1.tool_calls],
        }
        if r1.raw:
            assistant["raw"] = r1.raw
        messages.append(assistant)
        for c in r1.tool_calls:
            content = json.dumps(ALERT) if c.name == "get_alert" else "Not needed for this check."
            messages.append(
                {"role": "tool", "tool_call_id": c.id, "name": c.name, "content": content, "is_error": False}
            )
        messages.append(
            {
                "role": "user",
                "content": "Good. Now call finish with resolved=false, summary 'connectivity check', root_cause 'n/a'.",
            }
        )

        t0 = time.perf_counter()
        r2 = await llm.complete(SYSTEM_PROMPT, messages, tools)
        ms2 = int((time.perf_counter() - t0) * 1000)
    except (LLMError, LLMTransientError) as e:
        print(f"FAIL provider error: {e}")
        return 1

    names = [c.name for c in r2.tool_calls]
    if not r2.tool_calls:
        print(f"FAIL step 2: no tool call; text={r2.text[:200]!r}")
        return 1
    print(f"  step 2 ok: called {names} ({ms2} ms, {r2.input_tokens} in / {r2.output_tokens} out)")
    if r1.raw:
        print("  provider state (thought signatures) replayed successfully")
    print("PASS: the model can run the agent's multi-step tool loop.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
