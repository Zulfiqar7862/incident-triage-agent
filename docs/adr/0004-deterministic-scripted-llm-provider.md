# ADR-0004: Deterministic scripted LLM provider for CI and offline use

- Status: accepted
- Date: 2026-11-12

## Context

CI and reviewers must be able to run the full system, including approvals and
verification, without an API key, without cost and with repeatable results.

## Options considered

1. Live model in CI.
2. Recorded HTTP cassettes per provider.
3. A scripted policy that implements `LLMPort` and plays a sensible
   investigation for each scenario.

## Decision

Option 3: [`ScriptedPolicy`](../../app/infrastructure/llm/scripted.py),
selected automatically when no key is set (`LLM_PROVIDER=auto`) or explicitly
with `LLM_PROVIDER=scripted`. `REQUIRE_LLM=true` refuses to start without a
real model.

## Consequences

- Positive: deterministic tests and evals (3/3 scenarios with fixed step and
  token counts); offline demos.
- Negative: it does not exercise real model behaviour. The opt-in live smoke
  test (`pytest -m live`) covers Gemini.
- Negative: `scripted.py` is exempt from the function-size budget because its
  decision table is long by nature.
