"""Agent runtime: run lifecycle, the reason -> act -> observe loop, durable
checkpoints, tool execution with retry/backoff, human gates, and the event log.

Lifecycle
    queued -> running -> (awaiting_approval | awaiting_input | paused | needs_attention)
           -> running -> completed | failed | cancelled
    A server restart turns "running" into "interrupted"; resume continues from the
    last checkpoint. A failed run can also be resumed from its last checkpoint.

Durability
    State is checkpointed to SQLite after every step and on every status change.
    A step that crashes midway is simply replayed from the previous checkpoint.
    Production changes are idempotent by tool-call id, so a replayed approval
    never applies the same change twice.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

from .config import Settings
from .context import SYSTEM_PROMPT, brief_args, build_context, one_line, truncate_output
from .llm import LLMTransientError, ToolCall
from .memory import make_memory
from .mock_env import MockCluster, ToolError, ToolTransientError, load_scenario
from .store import Store
from .tools import TOOLS, ToolArgsError, ToolSpec, tool_schemas

log = logging.getLogger("agent")

TERMINAL = {"completed", "failed", "cancelled"}
RESUMABLE = {"paused", "interrupted", "failed", "needs_attention"}
NUDGE = ("You did not call a tool. Continue the investigation with a tool call, "
         "use ask_operator if you are blocked, or call finish if you are done.")


class NotFound(Exception):
    pass


class RunStateError(Exception):
    pass


class InvalidInput(Exception):
    pass


def _fmt(out) -> str:
    return out if isinstance(out, str) else json.dumps(out, indent=1, ensure_ascii=False)


def _new_state(run_id: str, scenario: dict, settings: Settings) -> dict:
    a = scenario["alert"]
    return {
        "run_id": run_id,
        "scenario_id": scenario["id"],
        "title": scenario["title"],
        "service": a["service"],
        "task": (f"Alert {a['id']} ({a['severity']}) on {a['service']}: {a['title']}. "
                 "Investigate, find the root cause, remediate safely, and verify."),
        "status": "queued",
        "status_reason": None,
        "created_at": time.time(),
        "step": 0,
        "max_steps": settings.max_steps,
        "max_run_tokens": settings.max_run_tokens,
        "plan": [],
        "hypotheses": [],
        "notes": [],
        "actions": [],
        "operator_log": [],
        "history": [],
        "pending": None,
        "recalled_memories": [],
        "env": {},
        "usage": {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "llm_ms": 0,
                  "tool_calls": 0, "tool_retries": 0, "tool_errors": 0},
        "last_context": None,
        "compacted_groups": 0,
        "nudges": 0,
        "result": None,
        "error": None,
    }


class Runtime:
    def __init__(self, store: Store, llm, settings: Settings):
        self.store = store
        self.llm = llm
        self.settings = settings
        self.tools = tool_schemas()
        self._tasks: dict[str, asyncio.Task] = {}
        self._control: dict[str, str] = {}

    # ---- queries -------------------------------------------------------------------------
    def get(self, run_id: str) -> dict:
        st = self.store.load(run_id)
        if st is None:
            raise NotFound(f"Run '{run_id}' not found")
        return st

    def is_active(self, run_id: str) -> bool:
        t = self._tasks.get(run_id)
        return bool(t and not t.done())

    def public(self, st: dict, include_history: bool = False) -> dict:
        view = {k: v for k, v in st.items() if k not in ("history", "env")}
        view["active"] = self.is_active(st["run_id"])
        view["history_messages"] = len(st["history"])
        if include_history:
            view["history"] = st["history"]
        return view

    # ---- lifecycle -------------------------------------------------------------------------
    def recover(self) -> int:
        """On startup, mark runs that were mid-flight when the process died."""
        runs = self.store.runs_with_status(["running", "queued"])
        for st in runs:
            self._set_status(st, "interrupted", "The server stopped while this run was in progress. Resume to continue from the last checkpoint.")
        return len(runs)

    def create_run(self, scenario_id: str) -> dict:
        try:
            scenario = load_scenario(scenario_id)
        except KeyError as e:
            raise NotFound(str(e).strip("'\"")) from None
        st = _new_state(f"run-{uuid.uuid4().hex[:8]}", scenario, self.settings)
        st["recalled_memories"] = self.store.recall([st["service"]], self.settings.memory_ttl_days, 3)
        self.store.create_run(st)
        self._emit(st, "run.created", {"task": st["task"], "scenario": scenario_id,
                                       "provider": self.llm.provider, "model": self.llm.model})
        if st["recalled_memories"]:
            self._emit(st, "memory.recalled", {"memories": st["recalled_memories"]})
        self._launch(st["run_id"])
        return st

    def pause(self, run_id: str) -> None:
        st = self.get(run_id)
        if not self.is_active(run_id):
            raise RunStateError(f"Run is {st['status']}; only a running run can be paused")
        self._control[run_id] = "pause"
        self._emit(st, "operator.control", {"action": "pause"})

    def cancel(self, run_id: str) -> None:
        st = self.get(run_id)
        if st["status"] in TERMINAL:
            raise RunStateError(f"Run is already {st['status']}")
        if self.is_active(run_id):
            self._control[run_id] = "cancel"
            self._emit(st, "operator.control", {"action": "cancel"})
            return
        st["pending"] = None
        self._set_status(st, "cancelled", "Cancelled by operator")

    def resume(self, run_id: str) -> None:
        st = self.get(run_id)
        if self.is_active(run_id) or st["status"] not in RESUMABLE:
            raise RunStateError(f"Run is {st['status']} and cannot be resumed")
        if st["status"] == "needs_attention":
            if st["step"] >= st["max_steps"]:
                st["max_steps"] += 10
            used = st["usage"]["input_tokens"] + st["usage"]["output_tokens"]
            if used >= st["max_run_tokens"]:
                st["max_run_tokens"] = int(st["max_run_tokens"] * 1.5)
        p = st.get("pending")
        if p:  # stopped while waiting on a human: go back to waiting, don't call the model
            kind = "awaiting_approval" if p["kind"] == "approval" else "awaiting_input"
            self._set_status(st, kind, "Restored the pending operator decision from the checkpoint")
            return
        self._emit(st, "operator.control", {"action": "resume"})
        self.store.save(st)
        self._launch(run_id)

    # ---- human-in-the-loop -------------------------------------------------------------------
    def approve(self, run_id: str, edited_args: dict | None = None, actor: str = "operator") -> None:
        st = self.get(run_id)
        p = st.get("pending")
        if st["status"] != "awaiting_approval" or not p or p["kind"] != "approval":
            raise RunStateError(f"Run is {st['status']}; nothing is waiting for approval")
        spec = TOOLS[p["tool"]]
        try:
            args = spec.parse({**p["args"], **(edited_args or {})})
        except ToolArgsError as e:
            raise InvalidInput(f"Edited arguments are invalid: {e}") from None
        final = args.model_dump()
        edited = final != p["args"]

        # Checkpoint the intent before touching production. If we crash after this,
        # re-approving replays idempotently (same action id).
        p["executing"], p["final_args"] = True, final
        self.store.save(st)
        try:
            content, is_error = _fmt(spec.handler(self._cluster(st), args, p["tool_call_id"])), False
        except ToolError as e:
            content, is_error = f"Execution failed: {e}", True

        header = "Operator APPROVED this action" + (f" after editing the arguments to {json.dumps(final)}" if edited else "") + "."
        st["operator_log"].append({"step": p["step"], "decision": "approved", "tool": p["tool"], "args": final,
                                   "edited": edited, "actor": actor, "at": time.time()})
        self._emit(st, "approval.decided", {"id": p["tool_call_id"], "decision": "approved", "tool": p["tool"],
                                            "args": final, "edited": edited, "actor": actor})
        self._record(st, p["step"], ToolCall(p["tool_call_id"], p["tool"], final), f"{header}\nResult: {content}", is_error, {})
        st["pending"] = None
        self.store.save(st)
        self._launch(run_id)

    def reject(self, run_id: str, feedback: str = "", actor: str = "operator") -> None:
        st = self.get(run_id)
        p = st.get("pending")
        if st["status"] != "awaiting_approval" or not p or p["kind"] != "approval":
            raise RunStateError(f"Run is {st['status']}; nothing is waiting for approval")
        feedback = feedback.strip()
        st["operator_log"].append({"step": p["step"], "decision": "rejected", "tool": p["tool"], "feedback": feedback,
                                   "actor": actor, "at": time.time()})
        self._emit(st, "approval.decided", {"id": p["tool_call_id"], "decision": "rejected", "tool": p["tool"],
                                            "feedback": feedback, "actor": actor})
        self._record(st, p["step"], ToolCall(p["tool_call_id"], p["tool"], p["args"]),
                     f"Operator REJECTED this action; it was NOT executed. Feedback: {feedback or '(none given)'}", False, {})
        st["pending"] = None
        self.store.save(st)
        self._launch(run_id)

    def message(self, run_id: str, text: str, actor: str = "operator") -> None:
        text = (text or "").strip()
        if not text:
            raise InvalidInput("Message is empty")
        st = self.get(run_id)
        if st["status"] in TERMINAL:
            raise RunStateError(f"Run is {st['status']}")
        p = st.get("pending")
        if st["status"] == "awaiting_input" and p and p["kind"] == "input":
            st["operator_log"].append({"step": p["step"], "decision": "message", "text": text, "at": time.time()})
            self._emit(st, "operator.message", {"text": text, "answering": p["question"], "actor": actor})
            self._record(st, p["step"], ToolCall(p["tool_call_id"], "ask_operator", p["args"]), f"Operator answered: {text}", False, {})
            st["pending"] = None
            self.store.save(st)
            self._launch(run_id)
            return
        self.store.push_inbox(run_id, text)
        self._emit(st, "operator.message", {"text": text, "queued": True, "actor": actor})

    # ---- the loop --------------------------------------------------------------------------------
    def _launch(self, run_id: str) -> None:
        if not self.is_active(run_id):
            self._tasks[run_id] = asyncio.get_running_loop().create_task(self._drive(run_id))

    async def _drive(self, run_id: str) -> None:
        st = self.get(run_id)
        self._set_status(st, "running")
        try:
            while True:
                ctl = self._control.pop(run_id, None)
                if ctl == "cancel":
                    self._set_status(st, "cancelled", "Cancelled by operator")
                    return
                if ctl == "pause":
                    self._set_status(st, "paused", "Paused by operator at a step boundary")
                    return
                if st["step"] >= st["max_steps"]:
                    self._set_status(st, "needs_attention", f"Step budget of {st['max_steps']} used up without finishing. Review the trace, send guidance, and resume to grant 10 more steps.")
                    return
                if st["usage"]["input_tokens"] + st["usage"]["output_tokens"] >= st["max_run_tokens"]:
                    self._set_status(st, "needs_attention", "Token budget for this run is used up. Resume to grant 50% more.")
                    return
                acks, outcome = await self._step(st)
                self.store.save(st)
                self.store.ack_inbox(acks)
                if outcome == "stop":
                    return
        except asyncio.CancelledError:
            raise  # process shutdown: the run stays "running" in the DB and recover() marks it interrupted
        except Exception as e:  # noqa: BLE001
            log.exception("run %s failed", run_id)
            st = self.get(run_id)  # discard the half-finished step; keep the last good checkpoint
            st["error"] = f"{type(e).__name__}: {e}"
            self._set_status(st, "failed", f"{st['error']}. Resume to retry from the last checkpoint.")
        finally:
            self._tasks.pop(run_id, None)

    async def _step(self, st: dict) -> tuple[list[int], str]:
        st["step"] += 1
        step = st["step"]

        inbox = self.store.peek_inbox(st["run_id"])
        for item in inbox:
            st["history"].append({"role": "user", "content": f"[Operator message] {item['text']}", "step": step})
            st["operator_log"].append({"step": step, "decision": "message", "text": item["text"], "at": item["ts"]})
        acks = [i["id"] for i in inbox]

        messages, stats = build_context(st, self.settings)
        st["last_context"] = stats
        if stats["dropped_groups"] > st["compacted_groups"]:
            self._emit(st, "context.compacted", {"dropped_groups": stats["dropped_groups"], "budget": stats["budget"]})
        st["compacted_groups"] = stats["dropped_groups"]

        t0 = time.perf_counter()
        resp = await self._call_llm(st, messages)
        ms = int((time.perf_counter() - t0) * 1000)
        u = st["usage"]
        cost = (resp.input_tokens * self.settings.cost_in_per_mtok + resp.output_tokens * self.settings.cost_out_per_mtok) / 1e6
        u["llm_calls"] += 1
        u["input_tokens"] += resp.input_tokens
        u["output_tokens"] += resp.output_tokens
        u["cost_usd"] = round(u["cost_usd"] + cost, 6)
        u["llm_ms"] += ms
        self._emit(st, "llm.call", {"model": resp.model, "input_tokens": resp.input_tokens, "output_tokens": resp.output_tokens,
                                    "latency_ms": ms, "cost_usd": round(cost, 6), "context": stats, "tool_calls": len(resp.tool_calls)})

        calls = resp.tool_calls
        st["history"].append({"role": "assistant", "text": resp.text, "step": step,
                              "tool_calls": [{"id": c.id, "name": c.name, "args": c.args} for c in calls]})
        if resp.text:
            self._emit(st, "agent.message", {"text": resp.text})
        if not calls:
            st["nudges"] += 1
            if st["nudges"] > 2:
                self._set_status(st, "needs_attention", "The agent stopped calling tools. Send guidance and resume.")
                return acks, "stop"
            st["history"].append({"role": "user", "content": NUDGE, "step": step})
            return acks, "continue"
        st["nudges"] = 0

        for c in calls:
            spec = TOOLS.get(c.name)
            self._emit(st, "tool.call", {"id": c.id, "name": c.name, "args": c.args, "kind": spec.kind if spec else "unknown"})

        results: dict[str, tuple] = {}
        reads: list[tuple[ToolCall, ToolSpec]] = []
        gate: dict | None = None
        finish: ToolCall | None = None
        for c in calls:
            spec = TOOLS.get(c.name)
            if spec is None:
                results[c.id] = (f"Unknown tool '{c.name}'. Available tools: {', '.join(TOOLS)}", True, {})
            elif spec.kind == "read":
                reads.append((c, spec))
            elif c.name == "finish":
                finish = c
            elif c.name == "update_working_memory":
                results[c.id] = self._apply_memory(st, c, spec)
            elif gate is not None:  # write tools and ask_operator: at most one human gate per step
                results[c.id] = ("Not executed: only one production change or operator question can be pending at a time. "
                                 "Re-issue it after the current one is resolved.", True, {})
            else:
                outcome = self._gate(st, c, spec, step)
                if isinstance(outcome, tuple):
                    results[c.id] = outcome
                else:
                    gate = outcome

        if reads:  # independent read-only calls run in parallel
            outs = await asyncio.gather(*(self._exec_read(st, c, spec) for c, spec in reads))
            for (c, _), out in zip(reads, outs):
                results[c.id] = out

        done = None
        if finish is not None:
            if gate is not None:
                results[finish.id] = ("Not finished: an operator decision is still pending.", True, {})
            else:
                try:
                    done = TOOLS["finish"].parse(finish.args)
                    results[finish.id] = ("Run finished.", False, {})
                except ToolArgsError as e:
                    results[finish.id] = (f"Invalid arguments for finish: {e}", True, {})

        for c in calls:  # keep results in the order the model issued the calls
            if c.id in results:
                self._record(st, step, c, *results[c.id])

        if done is not None:
            self._finish(st, done.model_dump())
            return acks, "stop"
        if gate is not None:
            st["pending"] = gate
            if gate["kind"] == "approval":
                self._emit(st, "approval.requested", gate)
                self._set_status(st, "awaiting_approval", f"Approve, edit, or reject {gate['tool']}({brief_args(gate['args'])}).")
            else:
                self._emit(st, "input.requested", gate)
                self._set_status(st, "awaiting_input", "The agent asked the operator a question.")
            return acks, "stop"
        return acks, "continue"

    # ---- step helpers -----------------------------------------------------------------------
    async def _call_llm(self, st: dict, messages: list[dict]):
        attempts = self.settings.llm_max_attempts
        for attempt in range(1, attempts + 1):
            try:
                return await self.llm.complete(SYSTEM_PROMPT, messages, self.tools, st)
            except LLMTransientError as e:
                if attempt == attempts:
                    raise
                delay = self.settings.llm_backoff_s * 2 ** (attempt - 1)
                self._emit(st, "llm.retry", {"attempt": attempt, "error": str(e)[:200], "retry_in_s": delay})
                await asyncio.sleep(delay)

    async def _exec_read(self, st: dict, call: ToolCall, spec: ToolSpec) -> tuple:
        try:
            args = spec.parse(call.args)
        except ToolArgsError as e:
            return (f"Invalid arguments for {call.name}: {e}. Check the tool schema and try again.", True, {"attempts": 1})
        cluster = self._cluster(st)
        t0 = time.perf_counter()
        max_attempts = self.settings.tool_max_attempts
        for attempt in range(1, max_attempts + 1):
            try:
                out = await asyncio.wait_for(asyncio.to_thread(spec.handler, cluster, args, call.id), self.settings.tool_timeout_s)
                return (_fmt(out), False, {"attempts": attempt, "duration_ms": int((time.perf_counter() - t0) * 1000)})
            except (ToolTransientError, asyncio.TimeoutError) as e:
                err = str(e) or f"timed out after {self.settings.tool_timeout_s}s"
                if attempt == max_attempts:
                    return (f"{call.name} failed after {attempt} attempts: {err}. The backend may be degraded; "
                            "try a different signal or come back to it later.", True,
                            {"attempts": attempt, "duration_ms": int((time.perf_counter() - t0) * 1000)})
                delay = self.settings.tool_backoff_s * 2 ** (attempt - 1)
                st["usage"]["tool_retries"] += 1
                self._emit(st, "tool.retry", {"id": call.id, "name": call.name, "attempt": attempt, "error": err, "retry_in_s": delay})
                await asyncio.sleep(delay)
            except ToolError as e:
                return (f"Error: {e}", True, {"attempts": attempt, "duration_ms": int((time.perf_counter() - t0) * 1000)})

    def _gate(self, st: dict, c: ToolCall, spec: ToolSpec, step: int):
        try:
            args = spec.parse(c.args).model_dump()
        except ToolArgsError as e:
            return (f"Invalid arguments for {c.name}: {e}", True, {})
        if spec.kind == "write":
            conf, floor = args["confidence"], self.settings.min_write_confidence
            if conf < floor:  # confidence-based routing: don't page a human for a guess
                self._emit(st, "policy.blocked", {"id": c.id, "tool": c.name, "confidence": conf, "min_confidence": floor})
                return (f"Blocked by policy: confidence {conf:.2f} is below the {floor:.2f} required to propose a production change. "
                        "Gather more evidence, or use ask_operator if you are unsure.", True, {})
            return {"kind": "approval", "tool_call_id": c.id, "tool": c.name, "args": args, "step": step,
                    "requested_at": time.time(), "executing": False}
        return {"kind": "input", "tool_call_id": c.id, "tool": c.name, "args": args, "question": args["question"],
                "step": step, "requested_at": time.time()}

    def _apply_memory(self, st: dict, c: ToolCall, spec: ToolSpec) -> tuple:
        try:
            a = spec.parse(c.args)
        except ToolArgsError as e:
            return (f"Invalid arguments for update_working_memory: {e}", True, {})
        changed = []
        if a.plan is not None:
            st["plan"] = a.plan
            changed.append("plan")
        if a.hypotheses:
            by_id = {h["id"]: h for h in st["hypotheses"]}
            for h in a.hypotheses:
                by_id[h.id] = h.model_dump()
            st["hypotheses"] = list(by_id.values())
            changed.append("hypotheses")
        if a.note:
            st["notes"].append({"step": st["step"], "text": a.note})
            changed.append("note")
        self._emit(st, "memory.update", {"changed": changed, "plan": st["plan"], "hypotheses": st["hypotheses"], "note": a.note})
        return ("Working memory updated: " + (", ".join(changed) or "no changes"), False, {})

    def _record(self, st: dict, step: int, call: ToolCall, content: str, is_error: bool, meta: dict) -> None:
        shown, trunc = truncate_output(content, self.settings.tool_output_max_chars)
        st["history"].append({"role": "tool", "tool_call_id": call.id, "name": call.name, "content": shown,
                              "is_error": is_error, "step": step})
        if call.name != "update_working_memory":
            st["actions"].append({"step": step, "tool": call.name, "args": brief_args(call.args),
                                  "status": "error" if is_error else "ok", "attempts": meta.get("attempts", 1),
                                  "outcome": one_line(content, 160)})
        st["usage"]["tool_calls"] += 1
        st["usage"]["tool_errors"] += int(is_error)
        self._emit(st, "tool.result", {"id": call.id, "name": call.name, "is_error": is_error, "content": shown,
                                       "truncated": trunc, "attempts": meta.get("attempts", 1),
                                       "duration_ms": meta.get("duration_ms")})

    def _finish(self, st: dict, result: dict) -> None:
        result["sim_resolved"] = self._cluster(st).resolved()  # simulator ground truth, shown for evaluation only
        st["result"] = result
        if result["resolved"]:
            mem = make_memory(st, result)
            self.store.add_memory(st["service"], st["run_id"], mem)
            self._emit(st, "memory.saved", {"memory": mem})
        self._emit(st, "run.finished", {"result": result, "usage": st["usage"]})
        self._set_status(st, "completed", "The agent reports the incident resolved" if result["resolved"]
                         else "The agent finished without resolving the incident")

    # ---- plumbing ----------------------------------------------------------------------------------
    def _cluster(self, st: dict) -> MockCluster:
        return MockCluster(load_scenario(st["scenario_id"]), st["env"])

    def _set_status(self, st: dict, status: str, reason: str | None = None) -> None:
        st["status"], st["status_reason"] = status, reason
        self.store.save(st)
        self._emit(st, "run.status", {"status": status, "reason": reason})

    def _emit(self, st: dict, type_: str, payload: dict) -> None:
        payload = {"step": st["step"], **payload}
        self.store.append_event(st["run_id"], type_, payload)
        log.info(json.dumps({"run": st["run_id"], "event": type_, "step": st["step"]}))
