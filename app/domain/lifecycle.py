"""Run lifecycle status sets — shared by API, runtime, and SSE."""

TERMINAL = frozenset({"completed", "failed", "cancelled"})
RESUMABLE = frozenset({"paused", "interrupted", "failed", "needs_attention"})
NUDGE = (
    "You did not call a tool. Continue the investigation with a tool call, "
    "use ask_operator if you are blocked, or call finish if you are done."
)
