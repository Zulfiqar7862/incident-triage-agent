# Incident triage agent

An AI agent that takes a production alert, investigates it with tools, finds the root cause, proposes a fix for a human to approve, applies it, and verifies the service recovered. An operator watches every step live in a web UI and can pause, redirect, edit, or reject the agent at any point.

![Approval gate](docs/screenshots/approval-gate.png)

## Quick start

Requires Python 3.11+.

```bash
make install          # or: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env  # add ANTHROPIC_API_KEY or OPENAI_API_KEY
make run              # or: .venv/bin/uvicorn app.main:app --port 8000
```

Open http://localhost:8000, pick a scenario, and click **Start triage**.

With no API key, the app runs an **offline scripted policy** instead of a model, and the header says so. It is a short, hand-written decision procedure, not the agent's intelligence. It exists so that the UI, runtime, tests and evals all work without a key, while exercising exactly the same tools, retries, approval gates and checkpoints a real model drives.

```bash
make test   # 14 tests, ~2 seconds, no API key needed
make eval   # golden-set evals against the configured model
docker build -t incident-agent . && docker run -p 8000:8000 --env-file .env incident-agent
```

## Why incident triage

Of the suggested use cases, triage forces the most real agent behaviour into a 2 to 4 hour build:

- The next step genuinely depends on what the last one found. A planner that follows a fixed script fails the second scenario.
- It has a natural, high-stakes human gate: the agent can investigate freely, but changing production needs a person.
- Success is verifiable. After a fix, the agent has to prove recovery with metrics, not just claim it.
- It runs against a deterministic simulation, so it's safe, reproducible, and evaluable. The tool interfaces are the same ones real Kubernetes, Prometheus and Loki clients would sit behind.

### The two scenarios

**Checkout errors after a deploy.** A config change in the latest deploy shrank the database connection pool from 50 to 5. The log backend times out on its first call, so the runtime must retry. One log line contains a prompt-injection attempt telling the agent to restart the database.

**Payment errors with a misleading deploy.** payment-gateway shipped a harmless deploy 16 minutes before errors started. The obvious move (roll it back) is wrong. The logs blame an upstream service, fraud-check, which is crash-looping out of memory. The agent has to reject its first hypothesis and follow the evidence upstream. The metrics backend is flaky on its first call.

## Architecture

```
 Browser UI ──REST──▶ FastAPI ──▶ Runtime ──▶ LLM adapter (Anthropic | OpenAI | offline policy)
     ▲                   │           │
     └──── SSE ◀─────────┘           ├──▶ Tool registry ──▶ Simulated cluster (state lives in the checkpoint)
       (event log)                   ├──▶ Context builder (working memory + compacted transcript)
                                     └──▶ SQLite: checkpoints, event log, operator inbox, long-term memory
```

| File | Responsibility |
|---|---|
| `app/runtime.py` | Run lifecycle, the agent loop, retries, human gates, checkpoints, events |
| `app/context.py` | What the model sees each step: system prompt, working memory, compaction |
| `app/tools.py` | Typed tool schemas, split into read, write, and meta kinds |
| `app/llm.py` | Provider-neutral message format plus Anthropic and OpenAI adapters |
| `app/store.py` | SQLite persistence |
| `app/memory.py` | Long-term memory promotion and redaction |
| `app/mock_env.py`, `scenarios/` | Deterministic simulated environment |
| `app/scripted.py` | Offline policy for keyless demos and tests |
| `static/index.html` | Operator UI, no build step |

### The loop

Each step:

1. Read any operator messages from the inbox.
2. Rebuild the prompt from the checkpoint.
3. Call the model.
4. Execute the tool calls:
   - Read-only calls run in parallel, with retry and backoff.
   - Working-memory updates apply immediately.
   - A production change or a question for the operator becomes a pending gate.
5. Checkpoint.

The run stops at a gate, a budget limit, `finish`, or an operator pause or cancel.

```
queued → running ⇄ awaiting_approval / awaiting_input / paused / needs_attention → completed | failed | cancelled
                 ↘ interrupted (server died) → resume
```

## Design decisions

**I wrote the runtime instead of using LangGraph.** The role is about owning agent runtimes, and the hard parts (durable execution, gates that survive restarts, idempotent side effects) are clearer to reason about and demo in about 500 lines I control than behind a framework's checkpointer. The trade-off is that I own bugs a framework would have fixed. With more time I'd benchmark against LangGraph or Pydantic AI before committing for production.

**Structured working memory is the source of truth; the transcript is disposable.** The agent records its plan, hypotheses, and notes through a tool, and the runtime appends a one-line entry to an action log for every tool call. The prompt is rebuilt every step as three layers:

- the system prompt;
- a `<working_memory>` block rendered from state;
- the recent transcript.

Context management happens at three points:

- **On arrival:** tool outputs are truncated, keeping head and tail at line boundaries, with a marker telling the model how to narrow its query.
- **After the last few steps:** older tool outputs shrink to a stub.
- **Over budget:** whole old steps are dropped, never separating a tool call from its result.

Dropping is safe because the action log already says what each step did. **Inspect context** in the UI shows the exact next prompt and how the token budget splits between the layers.

**Every production change needs approval, and the approval is durable.** Write tools never execute in the loop. They become a pending gate stored in the checkpoint, so a gate survives a server restart. The operator can approve, edit the arguments, or reject with feedback that goes back to the agent as the tool result. The runtime checkpoints its intent before executing, and actions are keyed by tool-call id, so a retried or double-clicked approval can't apply the same change twice.

**Confidence-based routing.** A proposed change with confidence below `MIN_WRITE_CONFIDENCE` (0.5) is bounced back to the agent rather than paging a human for a guess. The agent can also call `ask_operator` when evidence is ambiguous, which pauses the run until someone answers.

**Durability over performance.** State is checkpointed after every step. A step that dies midway is replayed from the previous checkpoint. A run that crashes stays `running` in the database, and on startup it is marked `interrupted` so an operator decides whether to resume it. Auto-resuming a production agent after an unexplained crash felt wrong. Operator messages are acknowledged only after the step that consumed them is checkpointed, so a crash doesn't lose them.

**Failure handling.** There are three kinds of failure, each handled differently:

- **Transient tool errors** are retried with exponential backoff, and each retry is visible in the trace.
- **Permanent tool errors and invalid arguments** go back to the model as errors it can correct.
- **Rate limits and overloads from the model provider** are retried.

Runaway behaviour is capped by:

- a step budget;
- a token budget;
- a limit on consecutive turns without a tool call.

Hitting any of these moves the run to `needs_attention`, and resuming it grants more budget.

**Prompt injection.** Tool output is untrusted data, and the system prompt says so, but the real defence is structural: nothing in a log line can execute a production change without a human approving a specific, visible action. Scenario 1 includes an injection attempt so you can watch it fail.

**Long-term memory is deliberately small.** Only resolved incidents are promoted, as a redacted one-liner: service, root cause, and fix. Secrets, emails, card numbers and IPs are stripped. Raw transcripts and logs are never kept. Memories expire after 30 days and are recalled by service with a "may be stale, verify" label. Run a scenario twice to see it recalled.

**Observability is built into the event log.** Every model call, tool call, retry, policy decision, operator decision and status change is an append-only event in SQLite. The UI's live trace is that log streamed over server-sent events, so a reconnecting browser or a later investigation sees exactly what happened. Each model call records tokens, latency, estimated cost, and context-window usage. Events are also logged as structured JSON for whatever collector you run.

## API

```
GET  /api/health                       provider, model, limits
GET  /api/scenarios                    available incidents
GET  /api/tools                        tool schemas (name, kind, JSON schema)
POST /api/runs                         {"scenario_id"} → start a run
GET  /api/runs                         list
GET  /api/runs/{id}                    state (?include_history=true for the raw transcript)
GET  /api/runs/{id}/context            the exact prompt the next step would send
GET  /api/runs/{id}/events?after=N     event log
GET  /api/runs/{id}/stream             live events over SSE (supports Last-Event-ID)
POST /api/runs/{id}/approve            {"args": {...}} optional edits
POST /api/runs/{id}/reject             {"feedback": "..."}
POST /api/runs/{id}/message            answer a question, or guide the agent at its next step
POST /api/runs/{id}/pause | resume | cancel
```

Errors use 404 for unknown runs, 409 for actions invalid in the current state, and 422 for bad input. Interactive docs are at `/docs`.

## Testing and evals

`make test` drives the real runtime with the offline policy and a fake model. It covers:

- both scenarios end to end;
- rejecting a change, and editing its arguments before approving;
- crash mid-step, then recover and resume without redoing earlier work;
- a pending approval surviving a restart, and double approval being refused;
- pause and resume;
- the step budget;
- low-confidence changes being blocked;
- model-call retry;
- invalid tool arguments;
- truncation;
- compaction that respects the budget and never splits tool pairs;
- long-term memory recall;
- an HTTP round trip.

`make eval` runs the golden set against whichever model is configured, auto-approving changes, and scores each run against simulator ground truth:

- whether the incident was really resolved;
- whether the first proposed fix was right;
- how many wrong production changes were made;
- whether the root cause was named;
- steps, tokens, cost and time.

Run it with `--repeat 5` before and after any prompt or model change.

## Limitations

- The real-model path was written against the public Anthropic and OpenAI APIs but developed mostly with the offline policy. Run `make eval` with a key before relying on it.
- Token counts for context budgeting are estimated at about 4 characters per token, not measured with a tokenizer.
- It runs as a single process with SQLite. Multiple workers would need a shared store and a lease on each run, so two workers can't drive the same run.
- There is no authentication or role-based approval. Anyone who can reach the UI can approve production changes.
- Retrieval is a lookup by service name, not semantic search, which is enough for two scenarios.

## What's next

1. **Real integrations:** Kubernetes, Prometheus and Loki behind the same tool interfaces, with read-only credentials for the investigation tools and separately scoped credentials for writes.
2. **OpenTelemetry GenAI spans** emitted alongside the event log, so traces land in Langfuse, Honeycomb or Grafana.
3. **Evals at scale:** 20 or more scenarios, including ones with no safe fix, plus LLM-as-judge scoring of report quality and CI that blocks prompt changes that regress.
4. **Approval policy:** roles, two-person approval for high-blast-radius changes, and approval timeouts.
5. **Semantic recall over past incidents and runbooks,** with retrieval scored on whether it changed the agent's decision, not just whether it matched.
6. **Prompt caching** for the system prompt and tool schemas, plus exact token counting.

## How this was built

AI usage was required for this assignment. The complete transcript is in [`docs/AI_TRANSCRIPT.md`](docs/AI_TRANSCRIPT.md), and the git history shows the build in stages, including bugs found along the way and their fixes.
