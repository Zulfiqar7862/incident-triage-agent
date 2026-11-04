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
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(base + "/", wait_until="networkidle")
            page.fill("#operator", "Alex Chen")
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
            # Collapsed technical details should not be open
            assert page.locator('[data-testid="technical-details"]:visible').count() == 0
            page.click("#apOk")
            page.wait_for_selector(".outcome", timeout=90000)
            browser.close()

        serious = [e for e in errors if "favicon" not in e.lower()]
        if serious:
            print("CONSOLE ERRORS:", serious)
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
