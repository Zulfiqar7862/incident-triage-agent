"""Golden-set evals: run every scenario end to end and score the outcome.

Use this to catch regressions when you change the model, the system prompt, the
tools, or the context strategy. Production changes are auto-approved (it's a
sandbox) and operator questions get a neutral answer, so the score measures the
agent's own judgement.

    python -m evals.run_evals                 # uses whatever provider is configured
    python -m evals.run_evals --provider scripted --repeat 3

Scores per run:
  resolved        simulator ground truth: the right fix was really applied
  first_fix_right the first production change proposed was a correct one
  wrong_changes   production changes that didn't fix anything
  root_cause      the report names the cause (keyword groups from the scenario)
  steps, tokens, cost, seconds
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from app.config import Settings
from app.llm import make_llm
from app.mock_env import list_scenarios, load_scenario
from app.runtime import Runtime
from app.store import Store

DONE = {"completed", "failed", "cancelled", "needs_attention"}


def _fix_matches(action: dict, scenario: dict) -> bool:
    return any(
        action["tool"] == f["tool"] and all(action["args"].get(k) == v for k, v in f["args"].items())
        for f in scenario["expected"]["fix_any_of"]
    )


def score(st: dict, scenario: dict, seconds: float) -> dict:
    applied = list(st["env"].get("applied", {}).values())
    result = st.get("result") or {}
    text = (result.get("root_cause", "") + " " + result.get("summary", "")).lower()
    groups = scenario["expected"]["root_cause_keywords"]
    u = st["usage"]
    return {
        "scenario": scenario["id"],
        "status": st["status"],
        "resolved": bool(result.get("sim_resolved")),
        "first_fix_right": bool(applied) and _fix_matches(applied[0], scenario),
        "wrong_changes": sum(1 for a in applied if not _fix_matches(a, scenario)),
        "root_cause": all(any(k in text for k in g) for g in groups),
        "steps": st["step"],
        "tokens": u["input_tokens"] + u["output_tokens"],
        "cost_usd": round(u["cost_usd"], 4),
        "seconds": round(seconds, 1),
    }


async def run_one(rt: Runtime, store: Store, scenario_id: str, timeout: float) -> dict:
    t0 = time.monotonic()
    rid = rt.create_run(scenario_id)["run_id"]
    while time.monotonic() - t0 < timeout:
        await asyncio.sleep(0.1)
        st = store.load(rid)
        if st["status"] == "awaiting_approval":
            rt.approve(rid, actor="eval-harness")
        elif st["status"] == "awaiting_input":
            rt.message(rid, "No additional context available. Use your best judgement from the evidence.", actor="eval-harness")
        elif st["status"] in DONE:
            break
    else:
        rt.cancel(rid)
    st = store.load(rid)
    return score(st, load_scenario(scenario_id), time.monotonic() - t0)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", help="auto | anthropic | openai | scripted")
    ap.add_argument("--scenario", action="append", help="run only these scenario ids")
    ap.add_argument("--repeat", type=int, default=1, help="runs per scenario (models are non-deterministic)")
    ap.add_argument("--timeout", type=float, default=300)
    args = ap.parse_args()

    settings = Settings.from_env()
    if args.provider:
        settings.llm_provider = args.provider
    settings.scripted_delay_s = 0
    settings.db_path = os.path.join(tempfile.mkdtemp(), "eval.db")  # fresh DB: no long-term memory leaks between evals
    store = Store(settings.db_path)
    llm = make_llm(settings)
    rt = Runtime(store, llm, settings)

    ids = args.scenario or [s["id"] for s in list_scenarios()]
    rows = []
    for sid in ids:
        for _ in range(args.repeat):
            rows.append(await run_one(rt, store, sid, args.timeout))

    cols = ["scenario", "status", "resolved", "first_fix_right", "wrong_changes", "root_cause", "steps", "tokens", "cost_usd", "seconds"]
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    print(f"\nModel: {llm.provider} / {llm.model}\n")
    print("  ".join(c.ljust(widths[c]) for c in cols))
    for r in rows:
        print("  ".join(str(r[c]).ljust(widths[c]) for c in cols))
    passed = sum(r["resolved"] and r["root_cause"] and r["wrong_changes"] == 0 for r in rows)
    print(f"\nPassed {passed}/{len(rows)} (resolved, root cause named, no wrong production changes)")

    out = Path("evals/results")
    out.mkdir(parents=True, exist_ok=True)
    (out / "latest.json").write_text(json.dumps({"provider": llm.provider, "model": llm.model, "runs": rows}, indent=2))
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
