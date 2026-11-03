"""Offline scripted policy: a deterministic stand-in for the LLM.

It lets you run the whole app, UI, and test suite with no API key. It is NOT the
agent's intelligence: it's a short, hand-written decision procedure that drives
the same runtime, tools, retries, approval gates, and checkpoints a real model
drives. Set ANTHROPIC_API_KEY or OPENAI_API_KEY to run the real agent.
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid

from .llm import LLMResponse, ToolCall

WRITE_TOOLS = {"rollback_deploy", "restart_service"}
LOG_QUERY = "error warn timeout exception oom killed"


def _call(name: str, **args) -> ToolCall:
    return ToolCall(f"call_{uuid.uuid4().hex[:12]}", name, args)


def _resp(text: str, calls: list[ToolCall]) -> LLMResponse:
    out_tokens = 40 + 25 * len(calls)
    return LLMResponse(text, calls, input_tokens=0, output_tokens=out_tokens, model="scripted-offline-policy")


class _Calls:
    """Index of every tool call in the run's history, joined with its result."""

    def __init__(self, history: list[dict]):
        results = {m["tool_call_id"]: m for m in history if m["role"] == "tool"}
        self.items: list[dict] = []
        for m in history:
            if m["role"] != "assistant":
                continue
            for tc in m.get("tool_calls", []):
                r = results.get(tc["id"])
                self.items.append({
                    "idx": len(self.items), "name": tc["name"], "args": tc["args"],
                    "content": r["content"] if r else None, "is_error": bool(r and r.get("is_error")),
                })

    def find(self, name: str, after: int = -1, **match) -> list[dict]:
        return [
            c for c in self.items
            if c["name"] == name and c["idx"] > after and c["content"] is not None and not c["is_error"]
            and all(c["args"].get(k) == v for k, v in match.items())
        ]

    def last(self, name: str, **match) -> dict | None:
        found = self.find(name, **match)
        return found[-1] if found else None


def _first_line(text: str, needles) -> str:
    for line in text.splitlines():
        low = line.lower()
        if any(n in low for n in needles):
            return line.split(" ", 2)[-1][:180]
    return ""


class ScriptedPolicy:
    provider = "scripted"
    model = "scripted-offline-policy"

    def __init__(self, delay_s: float = 0.8):
        self.delay_s = delay_s

    async def complete(self, system: str, messages: list[dict], tools: list[dict], state: dict | None = None) -> LLMResponse:
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        resp = self.decide(state or {"history": []})
        resp.input_tokens = sum(len(json.dumps(m)) for m in messages) // 4 + len(system) // 4
        return resp

    # ------------------------------------------------------------------------------------------
    def decide(self, state: dict) -> LLMResponse:
        C = _Calls(state["history"])
        if not C.items:
            return _resp("Starting triage: I'll lay out a plan and read the alert.", [
                _call("update_working_memory", plan=[
                    "Read the alert and identify the affected service",
                    "Check health, error metrics, and recent deploys",
                    "Read error logs and follow the evidence, including upstream dependencies",
                    "Propose one remediation for operator approval",
                    "Verify recovery with metrics, then report",
                ]),
                _call("get_alert"),
            ])

        alert_call = C.last("get_alert")
        if not alert_call:
            return _resp("Retrying the alert lookup.", [_call("get_alert")])
        svc = json.loads(alert_call["content"])["service"]

        answered = C.last("ask_operator")
        if answered:
            return _resp("Wrapping up with what I know.", [_call(
                "finish", summary=f"Triage of {svc} was inconclusive; handed back to the operator.",
                root_cause="Not determined by the agent.", resolved=False,
                follow_ups=[f"Operator guidance: {answered['content'][:200]}"],
            )])

        # Investigate the alerting service; follow the evidence upstream if the logs point there.
        chain, target = [svc], svc
        while True:
            need = self._investigate(C, target, deep=target != svc)
            if need:
                if target != svc and not C.find("describe_service", service=target):
                    return _resp(
                        f"{svc}'s logs blame its upstream dependency {target}, so the recent {svc} deploy is probably a red herring. Checking {target}.",
                        [_call("update_working_memory", hypotheses=[
                            {"id": "H1", "text": f"A recent change to {svc} is causing its errors", "status": "rejected",
                             "evidence": f"{svc}'s failing requests are calls to upstream {target}"},
                            {"id": "H2", "text": f"{target} is unhealthy and failing {svc}'s requests", "status": "investigating",
                             "evidence": "upstream errors and an open circuit breaker in logs"},
                        ])] + need,
                    )
                verb = "Reading logs" if need[0].name == "search_logs" else "Gathering health, metrics and deploy history"
                return _resp(f"{verb} for {target}.", need)
            logs = C.last("search_logs", service=target)["content"]
            m = re.search(r"upstream ([a-z0-9-]+)", logs)
            if m and m.group(1) in self._deps(C, target) and m.group(1) not in chain:
                target = m.group(1)
                chain.append(target)
                continue
            break

        if not C.find("search_runbooks"):
            logs = (C.last("search_logs", service=target) or {}).get("content") or ""
            q = " ".join(w for w in ("pool", "oom", "crashloop", "timeout", "memory") if w in logs.lower()) or f"{target} errors"
            return _resp(f"Checking runbooks for '{q}' before proposing a change.",
                         [_call("search_runbooks", query=q, top_k=2)])

        writes = [c for c in C.items if c["name"] in WRITE_TOOLS and c["content"] is not None]
        if not writes:
            return self._propose(C, svc, target)

        w = writes[-1]
        if w["is_error"] or "REJECTED" in w["content"]:
            return _resp("The operator rejected my change, so I'll stop and hand back with my findings.", [_call(
                "finish", summary=f"Proposed {w['name']} on {w['args'].get('service')} was rejected; incident not resolved by the agent.",
                root_cause=w["args"].get("reason", "See trace."), resolved=False,
                follow_ups=["Operator to choose a remediation", f"Operator feedback: {w['content'][:200]}"],
            )])

        verify = C.find("query_metrics", after=w["idx"], service=svc, metric="error_rate")
        if not verify:
            return _resp(f"Change applied. Verifying {svc}'s error rate before declaring success.",
                         [_call("query_metrics", service=svc, metric="error_rate", window_minutes=30)])

        data = json.loads(verify[-1]["content"])
        current = data["points"][-1]["value"]
        ok = current <= max(data["baseline"] * 2, 0.5)
        fix = f"{w['name']}({', '.join(f'{k}={v}' for k, v in w['args'].items() if k not in ('reason', 'confidence'))})"
        follow = (
            [f"Find and fix the memory leak in {target} (cache grows without eviction over multi-day uptime)",
             f"Alert on {target} heap above 85% and on restart count",
             f"Add a fallback in {svc} when the {target} circuit breaker is open"]
            if w["name"] == "restart_service" else
            [f"Revert or correct the config change in {target} before redeploying",
             "Add a canary gate on error rate for config-only changes",
             "Load-test connection-pool sizing changes before rollout"]
        )
        text = f"{svc} error rate is {current}{data['unit']} against a {data['baseline']}{data['unit']} baseline."
        return _resp(text + (" Recovered; writing the report." if ok else " Not recovered."), [_call(
            "finish", summary=f"{text} Remediation: {fix}.", root_cause=w["args"].get("reason", ""),
            resolved=ok, fix_applied=fix, follow_ups=follow,
        )])

    # ------------------------------------------------------------------------------------------
    def _investigate(self, C: _Calls, target: str, deep: bool) -> list[ToolCall]:
        need = []
        if not C.find("describe_service", service=target):
            need.append(_call("describe_service", service=target))
        if not C.find("query_metrics", service=target, metric="error_rate"):
            need.append(_call("query_metrics", service=target, metric="error_rate", window_minutes=60))
        if not C.find("get_recent_deploys", service=target):
            need.append(_call("get_recent_deploys", service=target))
        if deep and not C.find("query_metrics", service=target, metric="restarts"):
            need.append(_call("query_metrics", service=target, metric="restarts", window_minutes=60))
        if need:
            return need
        if not C.find("search_logs", service=target):
            return [_call("search_logs", service=target, query=LOG_QUERY, limit=50)]
        return []

    def _deps(self, C: _Calls, service: str) -> list[str]:
        c = C.last("describe_service", service=service)
        return json.loads(c["content"]).get("dependencies", []) if c else []

    def _propose(self, C: _Calls, svc: str, target: str) -> LLMResponse:
        logs = C.last("search_logs", service=target)["content"]
        low = logs.lower()
        desc = json.loads(C.last("describe_service", service=target)["content"])
        deploys = json.loads(C.last("get_recent_deploys", service=target)["content"])["deploys"]

        if "outofmemory" in low or "oomkilled" in low or "crashloop" in desc["pods"].lower():
            evidence = _first_line(logs, ("outofmemoryerror", "oomkilled"))
            reason = (f"{target} pods are exhausting memory and crash-looping (pods: {desc['pods']}; logs: {evidence}). "
                      f"{svc}'s calls to it fail. A rolling restart clears the leaked heap.")
            return _resp(f"{target} is out of memory and crash-looping. A restart should restore capacity; the leak still needs a code fix.", [
                _call("update_working_memory", hypotheses=[{"id": "H2", "text": f"{target} is unhealthy and failing {svc}'s requests",
                                                            "status": "confirmed", "evidence": f"pods {desc['pods']}; {evidence}"}]),
                _call("restart_service", service=target, reason=reason, confidence=0.8),
            ])

        recent = [d for d in deploys if d["minutes_ago"] <= 120]
        if recent and len(deploys) > 1:
            d = recent[0]
            for change in d["changes"]:
                hits = sorted({w for w in re.findall(r"[a-z_]{4,}", change.lower()) if w in low})
                if hits:
                    prev = deploys[deploys.index(d) + 1]["version"]
                    evidence = _first_line(logs, hits)
                    reason = (f"Deploy {d['version']} of {target} ({d['minutes_ago']} min ago) changed '{change}', "
                              f"and errors started right after it: {evidence}")
                    return _resp(f"The errors line up with the {d['version']} deploy, and its change ('{change}') matches the log errors. Proposing a rollback to {prev}.", [
                        _call("update_working_memory", hypotheses=[{"id": "H1", "text": f"Deploy {d['version']} broke {target} via '{change}'",
                                                                    "status": "confirmed", "evidence": evidence}]),
                        _call("rollback_deploy", service=target, to_version=prev, reason=reason, confidence=0.85),
                    ])

        return _resp("The evidence doesn't point to a clear, safe remediation.", [
            _call("ask_operator", question=f"I couldn't find a clear cause for {svc}'s errors. Is there anything changing outside the deploy history (traffic, infra, vendors)?"),
        ])
