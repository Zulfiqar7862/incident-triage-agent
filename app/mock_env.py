"""In-process simulated platform (ClusterPort adapter).

The agent does not hold production cluster credentials. Each scenario under
/scenarios describes services, deploy history, metrics, logs, and which
remediation actually fixes the incident. Mutable environment state lives in the
run checkpoint (state["env"]) so work resumes identically after a crash.
Swap this adapter for live Kubernetes / Prometheus / Loki clients without
changing the runtime or tool schemas.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from app.domain.labels import alert_card

SCENARIO_DIR = Path(__file__).resolve().parent.parent / "scenarios"
NOW = datetime(2026, 11, 3, 14, 30, 0, tzinfo=UTC)  # fixed "now" keeps output deterministic
POD_SUFFIXES = ["7f9c4-a1b2", "7f9c4-c3d4", "7f9c4-e5f6"]


class ToolError(Exception):
    """A permanent failure the agent should read and adapt to (bad args, unknown service)."""


class ToolTransientError(Exception):
    """A transient failure (timeout, 5xx). The runtime retries these with backoff."""


def _ts(minutes_ago: float) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


@lru_cache
def load_scenario(scenario_id: str) -> dict:
    if not re.fullmatch(r"[a-z0-9-]+", scenario_id or ""):
        raise KeyError(f"Unknown scenario '{scenario_id}'")
    path = SCENARIO_DIR / f"{scenario_id}.json"
    if not path.exists():
        raise KeyError(f"Unknown scenario '{scenario_id}'")
    return json.loads(path.read_text())


def list_scenarios() -> list[dict]:
    """Operator-facing scenario cards — no ALRT-/P-code jargon in default fields."""
    out = []
    for p in sorted(SCENARIO_DIR.glob("*.json")):
        s = json.loads(p.read_text())
        card = alert_card(s["alert"])
        out.append(
            {
                "id": s["id"],
                "title": s["title"],
                "description": card["summary"],
                "alert": card,
            }
        )
    return out


class MockCluster:
    def __init__(self, scenario: dict, env: dict):
        self.s = scenario
        self.env = env  # mutated in place; lives in the run checkpoint
        env.setdefault("applied", {})
        env.setdefault("calls", {})

    # ---- internals --------------------------------------------------------------
    def _svc(self, name: str) -> dict:
        try:
            return self.s["services"][name]
        except KeyError:
            known = ", ".join(sorted(self.s["services"]))
            raise ToolError(f"Unknown service '{name}'. Known services: {known}") from None

    def _maybe_flake(self, tool: str) -> None:
        n = self.env["calls"].get(tool, 0) + 1
        self.env["calls"][tool] = n
        if n <= self.s.get("flaky", {}).get(tool, 0):
            raise ToolTransientError(f"{tool}: observability backend timed out after 5000ms (HTTP 504)")

    def resolved(self) -> bool:
        """Ground truth: has an action that actually fixes this scenario been applied?"""
        for fix in self.s["expected"]["fix_any_of"]:
            for a in self.env["applied"].values():
                if a["tool"] == fix["tool"] and all(a["args"].get(k) == v for k, v in fix["args"].items()):
                    return True
        return False

    def _version(self, name: str) -> str:
        version = self._svc(name)["version"]
        for a in self.env["applied"].values():
            if a["tool"] == "rollback_deploy" and a["args"]["service"] == name:
                version = a["args"]["to_version"]
        return version

    def _in_incident(self, svc: dict, minutes_ago: float) -> bool:
        start = svc.get("incident_started_min_ago")
        if start is None or minutes_ago > start:
            return False
        if self.resolved() and minutes_ago <= 3:
            return False  # recovered after the fix
        return True

    def _pods(self, svc: dict) -> str:
        if self.resolved() and "pods_after_fix" in svc:
            return svc["pods_after_fix"]
        return svc["pods"]

    # ---- read tools -------------------------------------------------------------
    def get_alert(self) -> dict:
        a = dict(self.s["alert"])
        a["fired_at"] = _ts(a.pop("fired_min_ago"))
        a["status"] = "auto-resolving (condition cleared)" if self.resolved() else "firing"
        return a

    def list_services(self) -> list[dict]:
        return [
            {"service": n, "version": self._version(n), "pods": self._pods(svc), "owner": svc.get("owner")}
            for n, svc in self.s["services"].items()
        ]

    def describe_service(self, service: str) -> dict:
        svc = self._svc(service)
        return {
            "service": service,
            "version": self._version(service),
            "replicas": svc["replicas"],
            "pods": self._pods(svc),
            "uptime": svc.get("uptime", "unknown"),
            "owner": svc.get("owner"),
            "dependencies": svc.get("dependencies", []),
            "config": svc.get("config", {}),
        }

    def query_metrics(self, service: str, metric: str, window_minutes: int = 60) -> dict:
        self._maybe_flake("query_metrics")
        svc = self._svc(service)
        m = svc.get("metrics", {}).get(metric)
        if m is None:
            raise ToolError(
                f"Metric '{metric}' not found for {service}. Available: {', '.join(svc.get('metrics', {}))}"
            )
        step = max(1, window_minutes // 12)
        times = list(range(window_minutes, -1, -step))
        if times[-1] != 0:
            times.append(0)
        points = []
        for t in times:
            base = m.get("incident", m["baseline"]) if self._in_incident(svc, t) else m["baseline"]
            wobble = ((t * 37) % 7 - 3) / 100  # deterministic +-3% noise
            value = base * (1 + wobble)
            value = int(round(value)) if m["unit"] == "count" else round(value, 2)
            points.append({"minutes_ago": t, "value": value})
        return {
            "service": service,
            "metric": metric,
            "unit": m["unit"],
            "window_minutes": window_minutes,
            "baseline": m["baseline"],
            "points": points,
        }

    def search_logs(self, service: str, query: str, limit: int = 50) -> str:
        self._maybe_flake("search_logs")
        svc = self._svc(service)
        lines = self._log_lines(service, svc)
        q = (query or "").strip().lower()
        terms = [] if q in ("", "*") else [t for t in re.split(r"[\s,|]+", q) if t and t not in ("or", "and")]
        matched = [ln for ln in lines if not terms or any(t in ln.lower() for t in terms)]
        shown = matched[-limit:]
        header = (
            f"# {service} logs, last 60m, query={query!r}: {len(matched)} matching lines, "
            f"showing the most recent {len(shown)}"
        )
        if not matched:
            return header + "\n(no matching lines; try broader keywords or '*')"
        return header + "\n" + "\n".join(shown)

    def _log_lines(self, name: str, svc: dict) -> list[str]:
        logs = svc.get("logs", {})
        normal = logs.get("normal") or [f"INFO  {name} healthy"]
        incident = logs.get("incident") or normal
        out = []
        for i in range(240):  # one line every 15s over the last hour
            sec_ago = 3600 - i * 15
            pool = incident if self._in_incident(svc, sec_ago / 60) else normal
            line = pool[(i * 31 + 7) % len(pool)]  # 31 is coprime with every pool size we use
            ts = (NOW - timedelta(seconds=sec_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
            out.append(f"{ts} {name}-{POD_SUFFIXES[i % 3]} {line}")
        return out

    def get_recent_deploys(self, service: str) -> dict:
        svc = self._svc(service)
        deploys = [
            {
                "version": d["version"],
                "deployed_at": _ts(d["min_ago"]),
                "minutes_ago": d["min_ago"],
                "author": d["author"],
                "changes": d["changes"],
            }
            for d in svc.get("deploys", [])
        ]
        agent_actions = [
            {"action": a["tool"], "args": a["args"]}
            for a in self.env["applied"].values()
            if a["args"].get("service") == service
        ]
        return {
            "service": service,
            "current_version": self._version(service),
            "deploys": deploys,
            "actions_during_this_incident": agent_actions,
        }

    # ---- write tools (idempotent by action_id) ---------------------------------------
    def _apply(self, tool: str, args: dict, action_id: str, message: str) -> dict:
        result = {"ok": True, "message": message}
        self.env["applied"][action_id] = {"tool": tool, "args": args, "result": result}
        return result

    def rollback_deploy(self, service: str, to_version: str, action_id: str) -> dict:
        if action_id in self.env["applied"]:
            return {**self.env["applied"][action_id]["result"], "idempotent_replay": True}
        svc = self._svc(service)
        versions = [d["version"] for d in svc.get("deploys", [])]
        if to_version not in versions:
            raise ToolError(f"Version {to_version} not found for {service}. Known versions: {versions}")
        current = self._version(service)
        if to_version == current:
            raise ToolError(f"{service} is already running {to_version}")
        n = svc["replicas"]
        return self._apply(
            "rollback_deploy",
            {"service": service, "to_version": to_version},
            action_id,
            f"Rolled back {service} from {current} to {to_version}. Rollout complete: {n}/{n} pods ready.",
        )

    def restart_service(self, service: str, action_id: str) -> dict:
        if action_id in self.env["applied"]:
            return {**self.env["applied"][action_id]["result"], "idempotent_replay": True}
        svc = self._svc(service)
        n = svc["replicas"]
        return self._apply(
            "restart_service",
            {"service": service},
            action_id,
            f"Rolling restart of {service} complete: {n}/{n} pods replaced and passing readiness checks.",
        )
