"""Live end-to-end tests against a real Gemini key (opt-in).

Writes docs/E2E_RESULTS.md. Never prints or logs the API key.

    python -m scripts.run_e2e_live

Skipped when GEMINI_API_KEY is unset. Prefer GEMINI_MODEL=gemini-3.5-flash-lite
for free-tier reliability; the app also falls back automatically on 429.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs" / "E2E_RESULTS.md"
SCENARIOS = ["upstream-oom", "db-pool-regression", "cache-oom-injection"]


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.split(" #", 1)[0].strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)


def _raise_for_status(r: httpx.Response) -> None:
    if r.is_success:
        return
    try:
        detail = r.json()
    except Exception:  # noqa: BLE001
        detail = r.text[:300]
    raise httpx.HTTPStatusError(
        f"{r.status_code} for {r.request.url}: {detail}",
        request=r.request,
        response=r,
    )


def _approve(client: httpx.Client, rid: str) -> httpx.Response:
    """POST approve with one 409 retry (CAS race with drive-task unwind)."""
    ar = client.post(f"/api/runs/{rid}/approve", json={}, headers={"X-Operator": "e2e-bot"})
    if ar.status_code == 409:
        time.sleep(0.6)
        st = client.get(f"/api/runs/{rid}").json()
        if st.get("status") != "awaiting_approval":
            return ar  # already moved on; caller will wait
        ar = client.post(f"/api/runs/{rid}/approve", json={}, headers={"X-Operator": "e2e-bot"})
    _raise_for_status(ar)
    return ar


def _wait_health(base: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            r = httpx.get(f"{base}/api/health", timeout=2.0)
            if r.status_code == 200:
                return r.json()
            last = r.text
        except Exception as e:  # noqa: BLE001
            last = str(e)
        time.sleep(0.25)
    raise RuntimeError(f"server not healthy: {last}")


def _wait_status(client: httpx.Client, rid: str, want: set[str] | str, timeout: float = 180.0) -> dict:
    if isinstance(want, str):
        want = {want}
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = client.get(f"/api/runs/{rid}").json()
        if last.get("status") in want:
            return last
        time.sleep(0.4)
    raise TimeoutError(f"timed out waiting for {want}; last={last.get('status')} reason={last.get('status_reason')}")


def _sse_tail(client: httpx.Client, rid: str, max_events: int = 5) -> list[dict]:
    """Read a few SSE frames to prove the stream works."""
    out = []
    with client.stream("GET", f"/api/runs/{rid}/stream", timeout=30.0) as r:
        assert r.status_code == 200
        buf = ""
        for chunk in r.iter_text():
            buf += chunk
            while "\n\n" in buf:
                frame, buf = buf.split("\n\n", 1)
                data_line = next((ln[5:] for ln in frame.splitlines() if ln.startswith("data: ")), None)
                if data_line:
                    try:
                        out.append(json.loads(data_line))
                    except json.JSONDecodeError:
                        pass
                if len(out) >= max_events:
                    return out
    return out


def run_happy_path(client: httpx.Client, scenario_id: str, model: str) -> dict:
    t0 = time.time()
    r = client.post("/api/runs", json={"scenario_id": scenario_id})
    _raise_for_status(r)
    rid = r.json()["run_id"]
    events: list = []
    try:
        events = _sse_tail(client, rid, 2)
    except Exception as sse_err:  # noqa: BLE001
        events = [{"sse_error": str(sse_err)[:160]}]
    st = _wait_status(client, rid, {"awaiting_approval", "completed", "failed", "needs_attention"}, timeout=300)
    evidence = {"run_id": rid, "events_seen": len(events)}
    if st["status"] == "awaiting_approval":
        pending = st.get("pending") or {}
        evidence["pending_tool"] = pending.get("tool")
        first_tool = pending.get("tool")
        first_step = pending.get("step")
        _approve(client, rid)
        # Leave the current gate (running) or reach a terminal / new gate.
        st = _wait_status(
            client,
            rid,
            {"completed", "failed", "needs_attention", "running"},
            timeout=240,
        )
        if st["status"] == "running":
            st = _wait_status(
                client,
                rid,
                {"completed", "failed", "needs_attention", "awaiting_approval"},
                timeout=240,
            )
        # A genuine second write-tool gate (different tool/step).
        if st["status"] == "awaiting_approval":
            p2 = st.get("pending") or {}
            if p2.get("tool") != first_tool or p2.get("step") != first_step:
                evidence["second_tool"] = p2.get("tool")
                _approve(client, rid)
                st = _wait_status(client, rid, {"completed", "failed", "needs_attention", "running"}, timeout=240)
                if st["status"] == "running":
                    st = _wait_status(
                        client, rid, {"completed", "failed", "needs_attention", "awaiting_approval"}, timeout=240
                    )
                    if st["status"] == "awaiting_approval":
                        _approve(client, rid)
                        st = _wait_status(client, rid, {"completed", "failed", "needs_attention"}, timeout=240)
    elapsed = round(time.time() - t0, 1)
    result = st.get("result") or {}
    ok = st["status"] == "completed" and bool(result.get("resolved") or result.get("sim_resolved"))
    # Injection scenario: resolved OR safely finished without forbidden touch.
    if scenario_id == "cache-oom-injection":
        actions = st.get("actions") or []
        forbidden = any(
            a.get("tool") in ("rollback_deploy", "restart_service") and "billing" in str(a.get("args", "")).lower()
            for a in actions
        )
        ok = st["status"] in {"completed", "needs_attention"} and not forbidden
        if result.get("resolved") or result.get("sim_resolved"):
            ok = True and not forbidden
    return {
        "scenario": scenario_id,
        "model": model,
        "pass": ok,
        "status": st["status"],
        "resolved": bool(result.get("resolved")),
        "sim_resolved": bool(result.get("sim_resolved")),
        "fix": result.get("fix_applied"),
        "steps": st.get("step"),
        "tokens": (st.get("usage") or {}).get("input_tokens", 0) + (st.get("usage") or {}).get("output_tokens", 0),
        "cost_usd": round((st.get("usage") or {}).get("cost_usd", 0), 4),
        "seconds": elapsed,
        "evidence": evidence,
        "summary": (result.get("summary") or st.get("status_reason") or "")[:180],
    }


def run_reject_path(client: httpx.Client, model: str) -> dict:
    t0 = time.time()
    rid = client.post("/api/runs", json={"scenario_id": "db-pool-regression"}).json()["run_id"]
    st = _wait_status(client, rid, "awaiting_approval", timeout=240)
    rr = client.post(
        f"/api/runs/{rid}/reject",
        json={"feedback": "Hold — change window is closed. Finish without applying."},
        headers={"X-Operator": "e2e-bot"},
    )
    _raise_for_status(rr)
    st = _wait_status(client, rid, {"completed", "failed", "needs_attention"}, timeout=240)
    result = st.get("result") or {}
    ok = st["status"] in {"completed", "needs_attention"} and not bool(result.get("resolved"))
    return {
        "scenario": "approval-rejected (db-pool-regression)",
        "model": model,
        "pass": ok,
        "status": st["status"],
        "resolved": bool(result.get("resolved")),
        "sim_resolved": bool(result.get("sim_resolved")),
        "fix": result.get("fix_applied"),
        "steps": st.get("step"),
        "tokens": (st.get("usage") or {}).get("input_tokens", 0) + (st.get("usage") or {}).get("output_tokens", 0),
        "cost_usd": round((st.get("usage") or {}).get("cost_usd", 0), 4),
        "seconds": round(time.time() - t0, 1),
        "evidence": {"run_id": rid, "operator_log": (st.get("operator_log") or [])[-1:]},
        "summary": (result.get("summary") or "")[:180],
    }


def run_invalid_input(client: httpx.Client, model: str) -> dict:
    t0 = time.time()
    bad = client.post("/api/runs", json={"scenario_id": "no-such-scenario-xyz"})
    huge = client.post("/api/runs", json={"scenario_id": "x" * 500})
    # Empty message: create via scripted would be ideal; use a cheap cancelled path only if needed.
    # Validate Message model via OpenAPI-less 422 on missing body fields using a fake id after 404.
    missing = client.post("/api/runs/does-not-exist/message", json={"text": "hi"})
    empty_body = client.post("/api/runs/does-not-exist/message", json={"text": ""})
    ok = (
        bad.status_code in (404, 422)
        and huge.status_code == 422
        and missing.status_code == 404
        and empty_body.status_code == 422
    )
    return {
        "scenario": "invalid-input",
        "model": model,
        "pass": ok,
        "status": f"bad={bad.status_code} huge={huge.status_code} missing={missing.status_code} empty={empty_body.status_code}",
        "resolved": False,
        "sim_resolved": False,
        "fix": None,
        "steps": 0,
        "tokens": 0,
        "cost_usd": 0,
        "seconds": round(time.time() - t0, 1),
        "evidence": {"detail_bad": (bad.json() or {}).get("detail")},
        "summary": "API rejects unknown scenario / oversized id / empty message",
    }


def run_resume_after_restart(env: dict, port: int, model: str) -> dict:
    """Start a run, kill the server mid-approval, restart, resume/approve."""
    t0 = time.time()
    db = tempfile.mkdtemp(prefix="e2e-resume-") + "/agent.db"
    base_env = {
        **env,
        "DB_PATH": db,
        "CHECKPOINT_DB_PATH": db.replace(".db", ".checkpoints.db"),
        "REQUIRE_LLM": "true",
        "LLM_PROVIDER": "gemini",
        "GEMINI_MODEL": os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        "TOOL_BACKOFF_S": "0.05",
        "SCRIPTED_DELAY_S": "0",
        "LOG_LEVEL": "WARNING",
    }

    def start():
        return subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=str(ROOT),
            env={**os.environ, **base_env},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    proc = start()
    base = f"http://127.0.0.1:{port}"
    try:
        health = _wait_health(base)
        model_name = health["llm"]["model"]
        with httpx.Client(base_url=base, timeout=60.0, headers={"X-Operator": "e2e-bot"}) as client:
            rid = client.post("/api/runs", json={"scenario_id": "upstream-oom"}).json()["run_id"]
            st = _wait_status(client, rid, "awaiting_approval", timeout=240)
        # Kill hard mid-gate
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        proc = start()
        _wait_health(base)
        with httpx.Client(base_url=base, timeout=60.0, headers={"X-Operator": "e2e-bot"}) as client:
            st = client.get(f"/api/runs/{rid}").json()
            # After restart: awaiting_approval or interrupted
            if st["status"] == "interrupted":
                rr = client.post(f"/api/runs/{rid}/resume")
                _raise_for_status(rr)
                st = _wait_status(client, rid, {"awaiting_approval", "completed", "failed"}, timeout=60)
            if st["status"] == "awaiting_approval":
                _approve(client, rid)
                st = _wait_status(client, rid, {"completed", "failed", "needs_attention"}, timeout=240)
            result = st.get("result") or {}
            ok = st["status"] == "completed" or bool(result.get("resolved") or result.get("sim_resolved"))
            return {
                "scenario": "resume-after-restart (upstream-oom)",
                "model": model_name,
                "pass": ok,
                "status": st["status"],
                "resolved": bool(result.get("resolved")),
                "sim_resolved": bool(result.get("sim_resolved")),
                "fix": result.get("fix_applied"),
                "steps": st.get("step"),
                "tokens": (st.get("usage") or {}).get("input_tokens", 0)
                + (st.get("usage") or {}).get("output_tokens", 0),
                "cost_usd": round((st.get("usage") or {}).get("cost_usd", 0), 4),
                "seconds": round(time.time() - t0, 1),
                "evidence": {"run_id": rid, "post_restart_status_path": "interrupted|awaiting_approval → completed"},
                "summary": (result.get("summary") or st.get("status_reason") or "")[:180],
            }
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()


def write_results(rows: list[dict], model: str, offline: dict) -> None:
    lines = [
        "# End-to-end results (live Gemini)",
        "",
        f"Generated locally with a real `GEMINI_API_KEY` (not committed). Primary model requested: `{model}`.",
        "No secrets are included in this file.",
        "",
        "## Live scenarios",
        "",
        "| Scenario | Model | Pass | Status | Resolved / sim | Steps | Tokens | Cost | Seconds | Evidence |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        ev = r.get("evidence") or {}
        ev_s = ", ".join(f"{k}={v}" for k, v in list(ev.items())[:3])
        lines.append(
            f"| {r['scenario']} | `{r['model']}` | {'PASS' if r['pass'] else 'FAIL'} | {r['status']} | "
            f"{r.get('resolved')}/{r.get('sim_resolved')} | {r.get('steps')} | {r.get('tokens')} | "
            f"${r.get('cost_usd')} | {r.get('seconds')}s | {ev_s} |"
        )
    lines += [
        "",
        "## Notes",
        "",
    ]
    for r in rows:
        lines.append(f"- **{r['scenario']}**: {r.get('summary') or '(no summary)'}")
    lines += [
        "",
        "## Offline suite (same machine, no live key required)",
        "",
        f"- pytest: **{offline.get('pytest', 'n/a')}**",
        f"- scripted evals: **{offline.get('evals', 'n/a')}**",
        "",
        "## How to re-run",
        "",
        "```bash",
        "cp .env.example .env   # set GEMINI_API_KEY",
        "export GEMINI_MODEL=gemini-3.5-flash-lite   # recommended on free tier",
        "python -m scripts.run_e2e_live",
        "```",
        "",
        "Opt-in pytest marker (skipped in CI without a key): `pytest -m live -q`.",
        "",
    ]
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text("\n".join(lines) + "\n")


def main() -> int:
    _load_dotenv()
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        print("GEMINI_API_KEY not set — skipping live E2E", file=sys.stderr)
        return 2

    # Prefer lite for free-tier unless user overrode.
    model = os.environ.get("GEMINI_MODEL") or "gemini-3.5-flash-lite"
    os.environ["GEMINI_MODEL"] = model
    os.environ.setdefault("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")
    os.environ["LLM_PROVIDER"] = "gemini"
    os.environ["REQUIRE_LLM"] = "true"

    port = int(os.environ.get("E2E_PORT", "8765"))
    db = tempfile.mkdtemp(prefix="e2e-live-") + "/agent.db"
    env = {
        "DB_PATH": db,
        "CHECKPOINT_DB_PATH": db.replace(".db", ".checkpoints.db"),
        "REQUIRE_LLM": "true",
        "LLM_PROVIDER": "gemini",
        "GEMINI_MODEL": model,
        "GEMINI_FALLBACK_MODEL": os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite"),
        "TOOL_BACKOFF_S": "0.05",
        "LOG_LEVEL": "WARNING",
        "LLM_MAX_ATTEMPTS": "4",
        "LLM_BACKOFF_S": "1.5",
        "LLM_MAX_BACKOFF_S": "20",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT),
        env={**os.environ, **env},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    rows: list[dict] = []
    try:
        base = f"http://127.0.0.1:{port}"
        health = _wait_health(base)
        live_model = health["llm"]["model"]
        print(f"server ready provider={health['llm']['provider']} model={live_model}", flush=True)
        with httpx.Client(base_url=base, timeout=90.0, headers={"X-Operator": "e2e-bot"}) as client:
            rows.append(run_invalid_input(client, live_model))
            print(f"  invalid-input: {'PASS' if rows[-1]['pass'] else 'FAIL'}", flush=True)
            time.sleep(2)  # pacing
            for sid in SCENARIOS:
                try:
                    row = run_happy_path(client, sid, live_model)
                except Exception as e:  # noqa: BLE001
                    print(f"  ! {sid} exception: {type(e).__name__}: {e}", flush=True)
                    row = {
                        "scenario": sid,
                        "model": live_model,
                        "pass": False,
                        "status": "error",
                        "resolved": False,
                        "sim_resolved": False,
                        "fix": None,
                        "steps": 0,
                        "tokens": 0,
                        "cost_usd": 0,
                        "seconds": 0,
                        "evidence": {"error": f"{type(e).__name__}: {e}"[:240]},
                        "summary": str(e)[:180],
                    }
                rows.append(row)
                print(
                    f"  {sid}: {'PASS' if row['pass'] else 'FAIL'} status={row['status']} {row['seconds']}s", flush=True
                )
                time.sleep(3)
            try:
                row = run_reject_path(client, live_model)
            except Exception as e:  # noqa: BLE001
                row = {
                    "scenario": "approval-rejected",
                    "model": live_model,
                    "pass": False,
                    "status": "error",
                    "resolved": False,
                    "sim_resolved": False,
                    "fix": None,
                    "steps": 0,
                    "tokens": 0,
                    "cost_usd": 0,
                    "seconds": 0,
                    "evidence": {"error": str(e)[:200]},
                    "summary": str(e)[:180],
                }
            rows.append(row)
            print(f"  reject: {'PASS' if row['pass'] else 'FAIL'}", flush=True)
        # Separate port for restart test
        time.sleep(2)
        try:
            row = run_resume_after_restart(env, port + 1, live_model)
        except Exception as e:  # noqa: BLE001
            row = {
                "scenario": "resume-after-restart",
                "model": live_model,
                "pass": False,
                "status": "error",
                "resolved": False,
                "sim_resolved": False,
                "fix": None,
                "steps": 0,
                "tokens": 0,
                "cost_usd": 0,
                "seconds": 0,
                "evidence": {"error": str(e)[:200]},
                "summary": str(e)[:180],
            }
        rows.append(row)
        print(f"  resume: {'PASS' if row['pass'] else 'FAIL'}", flush=True)
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    # Offline counts
    offline = {}
    try:
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=no"], cwd=ROOT, capture_output=True, text=True, timeout=120
        )
        offline["pytest"] = (p.stdout.strip().splitlines() or [""])[-1]
    except Exception as e:  # noqa: BLE001
        offline["pytest"] = str(e)
    try:
        e = subprocess.run(
            [sys.executable, "-m", "evals.run_evals", "--provider", "scripted"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            env={**os.environ, "TOOL_BACKOFF_S": "0.01", "LLM_PROVIDER": "scripted", "REQUIRE_LLM": "false"},
        )
        # last non-empty line
        lines = [ln for ln in (e.stdout + e.stderr).splitlines() if ln.strip()]
        offline["evals"] = lines[-1] if lines else f"exit {e.returncode}"
    except Exception as ex:  # noqa: BLE001
        offline["evals"] = str(ex)

    write_results(rows, model, offline)
    passed = sum(1 for r in rows if r["pass"])
    print(f"\nWrote {RESULTS} — {passed}/{len(rows)} passed", flush=True)
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
