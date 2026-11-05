"""Capture React operator-console screenshots into docs/screenshots/ (scripted provider)."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    dist = ROOT / "frontend" / "dist" / "index.html"
    if not dist.is_file():
        print("building frontend…")
        subprocess.check_call(["npm", "run", "build"], cwd=str(ROOT / "frontend"))

    port = int(os.environ.get("SHOT_PORT", "8877"))
    db = tempfile.mkdtemp(prefix="shots-") + "/agent.db"
    env = {
        **os.environ,
        "DB_PATH": db,
        "CHECKPOINT_DB_PATH": db.replace(".db", ".checkpoints.db"),
        "LLM_PROVIDER": "scripted",
        "REQUIRE_LLM": "false",
        "SCRIPTED_DELAY_S": "0.15",
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

        with httpx.Client(base_url=base, timeout=30, headers={"X-Operator": "screenshots"}) as c:
            rid = c.post("/api/runs", json={"scenario_id": "db-pool-regression"}).json()["run_id"]
            for _ in range(400):
                st = c.get(f"/api/runs/{rid}").json()
                if st["status"] == "awaiting_approval":
                    break
                time.sleep(0.05)
            else:
                raise RuntimeError(f"never reached approval: {st.get('status')}")

        console_errors: list[str] = []

        def on_console(msg):  # noqa: ANN001
            if msg.type == "error":
                console_errors.append(msg.text)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
            page.on("console", on_console)
            page.goto(base + "/", wait_until="networkidle")
            page.fill("#operator", "Alex Chen")
            page.wait_for_selector('[data-testid="empty-state"]', timeout=15000)
            page.wait_for_timeout(400)
            page.screenshot(path=str(OUT / "01-empty.png"), full_page=True)

            # Running / thinking: start a fresh slow-ish run via UI
            page.select_option("#scenario", "db-pool-regression")
            page.click("#startBtn")
            page.wait_for_url("**/#/runs/**", timeout=15000)
            page.wait_for_selector('[data-testid="thinking-indicator"], [data-testid="approval-card"]', timeout=60000)
            if page.locator('[data-testid="thinking-indicator"]').count():
                page.wait_for_timeout(300)
                page.screenshot(path=str(OUT / "02-running.png"), full_page=True)

            page.goto(base + f"/#/runs/{rid}", wait_until="networkidle")
            page.fill("#operator", "Alex Chen")
            page.wait_for_selector('[data-testid="approval-card"]', timeout=30000)
            page.wait_for_timeout(500)
            page.screenshot(path=str(OUT / "approval-gate.png"), full_page=True)
            page.screenshot(path=str(OUT / "walkthrough-01-approval.png"), full_page=True)

            page.click("#apOk")
            # Capture toast shortly after approve
            page.wait_for_timeout(500)
            page.screenshot(path=str(OUT / "05-toast.png"), full_page=True)
            page.wait_for_selector(".outcome", timeout=60000)
            page.wait_for_timeout(600)
            page.screenshot(path=str(OUT / "resolved.png"), full_page=True)
            page.screenshot(path=str(OUT / "walkthrough-02-resolved.png"), full_page=True)

            page2 = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="dark")
            page2.on("console", on_console)
            page2.add_init_script("localStorage.setItem('theme','dark')")
            page2.goto(base + f"/#/runs/{rid}")
            page2.fill("#operator", "Alex Chen")
            page2.wait_for_selector(".outcome", timeout=20000)
            page2.wait_for_timeout(400)
            page2.screenshot(path=str(OUT / "dark-mode.png"), full_page=True)

            phone = browser.new_page(viewport={"width": 390, "height": 844}, color_scheme="light")
            phone.on("console", on_console)
            phone.goto(base + f"/#/runs/{rid}")
            phone.fill("#operator", "Alex Chen")
            phone.wait_for_selector(".outcome", timeout=20000)
            phone.wait_for_timeout(400)
            phone.screenshot(path=str(OUT / "03-mobile.png"), full_page=True)

            # Error state screenshot: navigate to bogus run
            err = browser.new_page(viewport={"width": 1440, "height": 900})
            err.on("console", on_console)
            err.goto(base + "/#/runs/run-does-not-exist")
            err.wait_for_timeout(1200)
            err.screenshot(path=str(OUT / "04-error.png"), full_page=True)

            browser.close()

        if console_errors:
            print("console errors:", console_errors)
            # Filter benign noise + intentional 404 error-state navigation
            serious = [
                e
                for e in console_errors
                if "favicon" not in e.lower()
                and "404" not in e
                and "Failed to load resource" not in e
            ]
            if serious:
                raise RuntimeError(f"JS console errors: {serious}")

        try:
            from PIL import Image

            frames = [Image.open(OUT / n) for n in ("walkthrough-01-approval.png", "walkthrough-02-resolved.png")]
            w = min(f.width for f in frames)
            h = min(f.height for f in frames)
            frames = [f.crop((0, 0, w, h)) for f in frames]
            frames[0].save(OUT / "walkthrough.gif", save_all=True, append_images=frames[1:], duration=1400, loop=0)
        except Exception as e:  # noqa: BLE001
            print("gif skipped:", e)

        print("wrote:", sorted(p.name for p in OUT.glob("*")))
        return 0
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
