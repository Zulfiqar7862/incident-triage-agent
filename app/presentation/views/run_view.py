"""Public run view returned by the HTTP API (read model over the run checkpoint)."""

from __future__ import annotations

from typing import Any, Protocol

from app.domain.labels import alert_card, plain_task_from_alert, status_words
from app.presentation.views.decisions import enrich_pending, pending_display
from app.presentation.views.report import present_report, run_display


class RunViewSource(Protocol):
    def is_active(self, run_id: str) -> bool: ...

    def scenario_alert(self, scenario_id: str) -> dict | None: ...


def present_run(source: RunViewSource, st: dict, include_history: bool = False) -> dict[str, Any]:
    """Strip internal state and attach additive operator projections. Canonical fields stay unchanged."""
    view = {k: v for k, v in st.items() if k not in ("history", "env")}
    view["active"] = source.is_active(st["run_id"])
    view["history_messages"] = len(st["history"])
    view["status_label"] = status_words(str(st.get("status") or ""))
    if not view.get("alert"):
        a = source.scenario_alert(st["scenario_id"])
        if a:
            view["alert"] = alert_card(a)
            view["task"] = plain_task_from_alert(a)
    if view.get("pending"):
        view["pending"] = {
            **enrich_pending(view["pending"]),
            "operator": pending_display(view["pending"], st["history"]),
        }
    if view.get("result"):
        view["result"] = present_report(view["result"], st["history"], st.get("env", {}).get("applied", {}))
    view["operator"] = run_display(st)
    if include_history:
        view["history"] = st["history"]
    return view
