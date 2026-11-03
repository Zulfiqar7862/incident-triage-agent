"""Capture UI screenshots into docs/screenshots/ using the scripted offline policy."""
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
    port = int(os.environ.get("SHOT_PORT", "8877"))
    db = tempfile.mkdtemp(prefix="shots-") + "/agent.db"
    env = {
        **os.environ,
        "DB_PATH": db,
        "CHECKPOINT_DB_PATH": db.replace(".db", ".checkpoints.db"),
        "LLM_PROVIDER": "scripted",
        "REQUIRE_LLM": "false",
        "SCRIPTED_DELAY_S": "0.1",
        "TOOL_BACKOFF_S": "0.01",
        "LOG_LEVEL": "WARNING",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
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
            for _ in range(300):
                st = c.get(f"/api/runs/{rid}").json()
                if st["status"] == "awaiting_approval":
                    break
                time.sleep(0.05)
            else:
                raise RuntimeError(f"never reached approval: {st.get('status')}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
            page.goto(base + "/", wait_until="networkidle")
            page.fill("#operator", "Alex Chen")
            page.wait_for_timeout(500)
            page.screenshot(path=str(OUT / "01-empty.png"), full_page=True)

            page.goto(base + f"/#{rid}", wait_until="networkidle")
            page.fill("#operator", "Alex Chen")
            # Force select in case hashchange raced with init
            page.evaluate(f"window.location.hash = '#{rid}';")
            page.wait_for_timeout(500)
            page.wait_for_selector(".approval", timeout=30000)
            page.wait_for_timeout(400)
            page.screenshot(path=str(OUT / "approval-gate.png"), full_page=True)
            page.screenshot(path=str(OUT / "demo-01-approval.png"), full_page=True)

            page.click("#apOk")
            page.wait_for_selector(".outcome", timeout=30000)
            page.wait_for_timeout(500)
            page.screenshot(path=str(OUT / "resolved.png"), full_page=True)
            page.screenshot(path=str(OUT / "demo-02-resolved.png"), full_page=True)

            page2 = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="dark")
            page2.goto(base + f"/#{rid}")
            page2.fill("#operator", "Alex Chen")
            page2.wait_for_selector(".outcome", timeout=20000)
            page2.wait_for_timeout(400)
            page2.screenshot(path=str(OUT / "dark-mode.png"), full_page=True)

            phone = browser.new_page(viewport={"width": 390, "height": 844}, color_scheme="light")
            phone.goto(base + f"/#{rid}")
            phone.fill("#operator", "Alex Chen")
            phone.wait_for_selector(".outcome", timeout=20000)
            phone.wait_for_timeout(400)
            phone.screenshot(path=str(OUT / "03-mobile.png"), full_page=True)

            browser.close()

        try:
            from PIL import Image
            frames = [Image.open(OUT / n) for n in ("demo-01-approval.png", "demo-02-resolved.png")]
            w = min(f.width for f in frames)
            h = min(f.height for f in frames)
            frames = [f.crop((0, 0, w, h)) for f in frames]
            frames[0].save(OUT / "demo.gif", save_all=True, append_images=frames[1:], duration=1400, loop=0)
        except Exception as e:
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
