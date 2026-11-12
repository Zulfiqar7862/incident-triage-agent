"""Tool registry. Each tool has a typed argument model (validated before execution),
a JSON schema the model sees, and a kind that decides how the runtime treats it:

  read   - safe, run immediately, in parallel, with retry/backoff
  write  - production change: always paused behind an operator approval gate
  meta   - changes the agent's own state (working memory, asking the operator, finishing)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


class ToolArgsError(Exception):
    pass


# ---- argument models --------------------------------------------------------------
class NoArgs(BaseModel):
    pass


class ServiceArgs(BaseModel):
    service: str = Field(description="Service name, e.g. checkout-service")


class MetricsArgs(BaseModel):
    service: str = Field(description="Service name")
    metric: str = Field(
        description="Metric name: error_rate, latency_p99, cpu, memory, restarts, or a service-specific one"
    )
    window_minutes: int = Field(60, ge=5, le=360, description="How far back to look")


class LogsArgs(BaseModel):
    service: str = Field(description="Service name")
    query: str = Field(
        description="Space-separated keywords; a line matches if it contains ANY keyword (case-insensitive). Use '*' for all lines."
    )
    limit: int = Field(50, ge=1, le=500, description="Max lines to return (most recent first kept)")


class RunbookArgs(BaseModel):
    query: str = Field(description="Symptoms or keywords to search, e.g. 'db pool exhausted' or 'OOMKilled crashloop'")
    top_k: int = Field(2, ge=1, le=3, description="Max runbooks to return (precision over volume)")


class RollbackArgs(BaseModel):
    service: str = Field(description="Service to roll back")
    to_version: str = Field(description="A previous version from get_recent_deploys")
    reason: str = Field(description="The evidence-based root cause this change addresses")
    confidence: float = Field(ge=0, le=1, description="Honest confidence (0-1) that this change fixes the incident")


class RestartArgs(BaseModel):
    service: str = Field(description="Service to restart")
    reason: str = Field(description="The evidence-based root cause this change addresses")
    confidence: float = Field(ge=0, le=1, description="Honest confidence (0-1) that this change fixes the incident")


class Hypothesis(BaseModel):
    id: str = Field(description="Stable id, e.g. H1")
    text: str
    status: Literal["investigating", "confirmed", "rejected"]
    evidence: str = ""


class MemoryArgs(BaseModel):
    plan: list[str] | None = Field(None, description="Replace the investigation plan")
    hypotheses: list[Hypothesis] | None = Field(None, description="Hypotheses to add or update (matched by id)")
    note: str | None = Field(None, description="A fact worth keeping for later steps")


class AskArgs(BaseModel):
    question: str = Field(description="A specific question for the on-call operator")


class FinishArgs(BaseModel):
    summary: str = Field(description="Two or three sentences for the incident channel")
    root_cause: str
    resolved: bool = Field(description="True only if you verified recovery with metrics")
    fix_applied: str | None = None
    follow_ups: list[str] = Field(default_factory=list)


# ---- registry ------------------------------------------------------------------------
@dataclass
class ToolSpec:
    name: str
    description: str
    kind: Literal["read", "write", "meta"]
    model: type[BaseModel]
    handler: Callable[[Any, Any, str], Any] | None = None  # (cluster, args, call_id) -> result

    def parse(self, raw: dict | None) -> BaseModel:
        try:
            return self.model.model_validate(raw or {})
        except ValidationError as e:
            msg = "; ".join(f"{'.'.join(map(str, err['loc'])) or 'args'}: {err['msg']}" for err in e.errors())
            raise ToolArgsError(msg) from None

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "kind": self.kind,
            "input_schema": _inline_refs(self.model.model_json_schema()),
        }


def _inline_refs(schema: dict) -> dict:
    """Inline $defs and drop titles so the schema works with every provider."""
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(dict(defs[node["$ref"].split("/")[-1]]))
            return {k: walk(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)


_SPECS = [
    ToolSpec(
        "get_alert",
        "Get the full alert that triggered this run: service, severity, firing time, status.",
        "read",
        NoArgs,
        lambda cl, a, cid: cl.get_alert(),
    ),
    ToolSpec(
        "list_services",
        "List all services with current version, pod status and owner.",
        "read",
        NoArgs,
        lambda cl, a, cid: cl.list_services(),
    ),
    ToolSpec(
        "describe_service",
        "Describe a service: version, replicas, pod health, uptime, owner, dependencies, runtime config.",
        "read",
        ServiceArgs,
        lambda cl, a, cid: cl.describe_service(a.service),
    ),
    ToolSpec(
        "query_metrics",
        "Time series for one metric of one service over the last N minutes, with its normal baseline.",
        "read",
        MetricsArgs,
        lambda cl, a, cid: cl.query_metrics(a.service, a.metric, a.window_minutes),
    ),
    ToolSpec(
        "search_logs",
        "Search a service's logs from the last hour. Returns matching lines, most recent last. Large results are truncated, so prefer specific keywords.",
        "read",
        LogsArgs,
        lambda cl, a, cid: cl.search_logs(a.service, a.query, a.limit),
    ),
    ToolSpec(
        "search_runbooks",
        "Retrieve internal runbooks matching the symptoms. Prefer this before proposing a production change when the cause looks familiar. Returns short excerpts, not the whole library.",
        "read",
        RunbookArgs,
        lambda cl, a, cid: cl.search_runbooks(a.query, a.top_k),
    ),
    ToolSpec(
        "get_recent_deploys",
        "Deploy history for a service (newest first) with change notes, plus any actions taken during this incident.",
        "read",
        ServiceArgs,
        lambda cl, a, cid: cl.get_recent_deploys(a.service),
    ),
    ToolSpec(
        "rollback_deploy",
        "PRODUCTION CHANGE, requires operator approval. Roll a service back to a previous version from its deploy history.",
        "write",
        RollbackArgs,
        lambda cl, a, cid: cl.rollback_deploy(a.service, a.to_version, cid),
    ),
    ToolSpec(
        "restart_service",
        "PRODUCTION CHANGE, requires operator approval. Rolling restart of every pod of a service.",
        "write",
        RestartArgs,
        lambda cl, a, cid: cl.restart_service(a.service, cid),
    ),
    ToolSpec(
        "update_working_memory",
        "Update your durable working memory: replace the plan, add/update hypotheses by id, or add a note. Working memory survives context compaction; record anything you will need later.",
        "meta",
        MemoryArgs,
    ),
    ToolSpec(
        "ask_operator",
        "Pause and ask the human operator a question when evidence is ambiguous or you need a decision. The run waits for the answer.",
        "meta",
        AskArgs,
    ),
    ToolSpec(
        "finish",
        "End the run with an incident report. Call only after verifying the outcome, or after concluding you cannot resolve it.",
        "meta",
        FinishArgs,
    ),
]

TOOLS: dict[str, ToolSpec] = {s.name: s for s in _SPECS}


def tool_schemas() -> list[dict]:
    return [s.schema() for s in _SPECS]


def build_tool_registry() -> dict[str, ToolSpec]:
    """Factory: return a fresh name→ToolSpec map (copy of the canonical registry)."""
    return dict(TOOLS)


def tools_by_kind(kind: str) -> list[ToolSpec]:
    """Filter registry by kind (read | write | meta) — useful for policy / UI."""
    return [s for s in _SPECS if s.kind == kind]
