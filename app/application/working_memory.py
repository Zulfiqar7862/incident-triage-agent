"""Apply the agent's ``update_working_memory`` tool call to run state."""

from __future__ import annotations

from app.tools.specs import MemoryArgs


def apply_working_memory(st: dict, args: MemoryArgs) -> list[str]:
    """Replace the plan, upsert hypotheses by id, append a note. Returns changed keys."""
    changed: list[str] = []
    if args.plan is not None:
        st["plan"] = args.plan
        changed.append("plan")
    if args.hypotheses:
        by_id = {h["id"]: h for h in st["hypotheses"]}
        for h in args.hypotheses:
            by_id[h.id] = h.model_dump()
        st["hypotheses"] = list(by_id.values())
        changed.append("hypotheses")
    if args.note:
        st["notes"].append({"step": st["step"], "text": args.note})
        changed.append("note")
    return changed
