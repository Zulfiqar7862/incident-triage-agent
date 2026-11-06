"""Headless Playwright: full offline scenario including approval; fail on JS console errors."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    dist = ROOT / "frontend" / "dist" / "index.html"
    if not dist.is_file():
        subprocess.check_call(["npm", "run", "build"], cwd=str(ROOT / "frontend"))

    port = int(os.environ.get("E2E_PORT", "8878"))
    db = tempfile.mkdtemp(prefix="e2e-ui-") + "/agent.db"
    env = {
        **os.environ,
        "DB_PATH": db,
        "CHECKPOINT_DB_PATH": db.replace(".db", ".checkpoints.db"),
        "LLM_PROVIDER": "scripted",
        "REQUIRE_LLM": "false",
        "SCRIPTED_DELAY_S": "0.12",
        "TOOL_BACKOFF_S": "0.01",
        "LOG_LEVEL": "WARNING",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(80):
            try:
                if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(0.2)
        else:
            raise RuntimeError("server failed to start")

        errors: list[str] = []
        warnings: list[str] = []

        def run_state(page):
            rid = page.url.rsplit("/", 1)[-1]
            return httpx.get(f"{base}/api/runs/{rid}", timeout=5).json()

        def wait_status(page, expected):
            for _ in range(300):
                st = run_state(page)
                if st["status"] in expected:
                    return st
                time.sleep(0.05)
            raise AssertionError(f"expected {expected}, got {st['status']}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.on("console", lambda m: warnings.append(m.text) if m.type == "warning" else None)
            page.goto(base + "/", wait_until="networkidle")
            page.fill("#operator", "Alex Chen")
            assert page.locator("#operator").evaluate("el => getComputedStyle(el).outlineStyle === 'solid'")
            page.keyboard.press("Tab")
            assert page.locator("#scenario").evaluate("el => el === document.activeElement")
            page.wait_for_selector('[data-testid="empty-state"]')
            page.select_option("#scenario", "db-pool-regression")
            page.click("#startBtn")
            page.wait_for_selector('[data-testid="run-header"]', timeout=30000)
            page.wait_for_selector('[data-testid="thinking-indicator"], [data-testid="approval-card"]', timeout=90000)
            page.wait_for_selector('[data-testid="approval-card"]', timeout=120000)
            page.wait_for_selector('[data-testid="tool-card"]', timeout=30000)
            # expand a tool card — structured view, no raw JSON dump
            page.locator('[data-testid="tool-card"] button').first.click()
            page.wait_for_timeout(400)
            # Main timeline/run view must not show pretty-printed JSON objects by default
            body = page.locator('[data-testid="timeline"]').inner_text()
            side = page.locator('[aria-label="Run controls and state"]').inner_text()
            # Allow single-line values; forbid multi-line brace blocks typical of JSON dumps
            if re.search(r"\{\s*\n\s*\"", body):
                raise RuntimeError("raw JSON object visible in main timeline")
            # No function-call style text in the default operator view
            combined = body + "\n" + side
            if re.search(r"\b\w+_\w+\(", combined):
                raise RuntimeError(f"function-call text visible in UI: {re.search(r'\b\w+_\w+\(', combined).group(0)}")
            if re.search(r"\brun-[a-z0-9]+\b", combined, re.I):
                raise RuntimeError("raw run id visible in default UI")
            if "Demo mode" in combined:
                raise RuntimeError("demo wording visible in UI")
            if re.search(r"\bALRT-\d+", combined):
                raise RuntimeError("raw alert id visible in UI")
            if re.search(r"\bP[1-4]\b", combined):
                raise RuntimeError("P-code severity jargon visible in UI")
            forbidden = (
                r"DB_POOL_SIZE|ERROR POST|/api/checkout|TimeoutError|Traceback|pool-size|checkpoint|Agent is thinking"
            )
            assert not re.search(forbidden, combined, re.I), "technical evidence leaked into operator view"
            assert "Restore the previous version" in side
            assert "Failed requests:" in combined
            # Reload replays persisted events through the same display projection.
            page.reload(wait_until="networkidle")
            page.wait_for_selector('[data-testid="approval-card"]')
            assert not re.search(forbidden, page.locator("main").inner_text(), re.I)
            assert page.locator('[data-testid="thinking-indicator"]').count() == 0
            # Collapsed technical details should not be open
            assert page.locator('[data-testid="technical-details"]:visible').count() == 0
            # Message + edit + approve through real operator controls.
            page.fill("#opMsg", "Verify recovery after remediation.")
            page.click("#opSend")
            page.get_by_role("button", name="Edit before approving").click()
            page.get_by_label("Reason", exact=True).fill(
                "Evidence reviewed by operator; verify recovery after rollback."
            )
            page.click("#apOk")
            page.wait_for_selector(".outcome", timeout=90000)
            report_text = (
                page.locator('[data-testid="timeline"]').inner_text()
                + page.locator('[aria-label="Run controls and state"]').inner_text()
            )
            assert not re.search(r"\b\w+_\w+\(", report_text), "raw function-call syntax in resolved operator view"
            assert not re.search(forbidden, report_text, re.I), "raw diagnostics leaked in final report"
            rid = page.url.rsplit("/", 1)[-1]
            events = httpx.get(f"{base}/api/runs/{rid}/events", timeout=5).json()
            assert any(e["type"] == "approval.decided" and e["payload"].get("edited") for e in events)

            # A second investigation exercises pause/resume, reject, and cancel.
            previous = page.url
            page.click("#startBtn")
            page.wait_for_url(lambda url: str(url) != previous, timeout=30000)
            page.get_by_role("button", name="Pause", exact=True).click()
            wait_status(page, {"paused"})
            page.get_by_role("button", name="Resume", exact=True).click()
            page.wait_for_selector('[data-testid="approval-card"]', timeout=90000)
            page.fill("#apFb", "Do not apply; DB_POOL_SIZE TimeoutError ERROR POST /api/checkout")
            page.click("#apNo")
            rid = page.url.rsplit("/", 1)[-1]
            for _ in range(300):
                events = httpx.get(f"{base}/api/runs/{rid}/events", timeout=5).json()
                if any(e["type"] == "approval.decided" and e["payload"].get("decision") == "rejected" for e in events):
                    break
                time.sleep(0.05)
            else:
                raise AssertionError("rejection was not recorded")
            wait_status(page, {"completed"})
            page.wait_for_selector(".outcome")
            assert not re.search(forbidden, page.locator("main").inner_text(), re.I), "raw rejection feedback leaked"
            # Rejection can finish immediately; cancel a separate stable pending run.
            previous = page.url
            page.click("#startBtn")
            page.wait_for_url(lambda url: str(url) != previous, timeout=30000)
            page.wait_for_selector('[data-testid="approval-card"]', timeout=90000)
            page.once("dialog", lambda dialog: dialog.accept())
            page.get_by_role("button", name="Stop", exact=True).click()
            wait_status(page, {"cancelled"})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            browser.close()

        print("CONSOLE WARNINGS:", warnings)
        print("CONSOLE/PAGE ERRORS:", errors)
        if errors:
            return 1
        print("e2e ui OK")
        return 0
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
