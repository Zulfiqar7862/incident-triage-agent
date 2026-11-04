"""Record a Playwright MP4 walkthrough of the React operator console (offline provider)."""
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
MP4 = OUT / "walkthrough.mp4"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    dist = ROOT / "frontend" / "dist" / "index.html"
    if not dist.is_file():
        subprocess.check_call(["npm", "run", "build"], cwd=str(ROOT / "frontend"))

    port = int(os.environ.get("WALK_PORT", "8879"))
    db = tempfile.mkdtemp(prefix="walk-") + "/agent.db"
    env = {
        **os.environ,
        "DB_PATH": db,
        "CHECKPOINT_DB_PATH": db.replace(".db", ".checkpoints.db"),
        "LLM_PROVIDER": "scripted",
        "REQUIRE_LLM": "false",
        "SCRIPTED_DELAY_S": "0.35",
        "TOOL_BACKOFF_S": "0.02",
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

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                record_video_dir=str(OUT / "_video"),
                record_video_size={"width": 1440, "height": 900},
                color_scheme="light",
            )
            page = context.new_page()
            page.goto(base + "/", wait_until="networkidle")
            page.fill("#operator", "Alex Chen")
            page.wait_for_selector('[data-testid="empty-state"]')
            page.wait_for_timeout(800)
            page.select_option("#scenario", "db-pool-regression")
            page.wait_for_timeout(400)
            page.click("#startBtn")
            page.wait_for_selector('[data-testid="run-header"]', timeout=30000)
            # Let thinking / tools stream
            try:
                page.wait_for_selector('[data-testid="thinking-indicator"]', timeout=20000)
                page.wait_for_timeout(1200)
            except Exception:
                pass
            page.wait_for_selector('[data-testid="approval-card"]', timeout=120000)
            page.wait_for_timeout(1500)
            # Expand a tool card if present
            tools = page.locator('[data-testid="tool-card"] button')
            if tools.count():
                tools.first.click()
                page.wait_for_timeout(900)
            page.click("#apOk")
            page.wait_for_selector(".outcome", timeout=120000)
            page.wait_for_timeout(2000)
            context.close()
            browser.close()

        # Move the single webm and convert to mp4 if ffmpeg exists
        vdir = OUT / "_video"
        vids = list(vdir.glob("*.webm"))
        if not vids:
            raise RuntimeError("no video recorded")
        webm = vids[0]
        dest_webm = OUT / "walkthrough.webm"
        webm.replace(dest_webm)
        # Prefer mp4 via ffmpeg
        if subprocess.call(["which", "ffmpeg"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
            subprocess.check_call(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(dest_webm),
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    str(MP4),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print("wrote", MP4)
        else:
            # Keep webm as the deliverable alias
            dest_webm.replace(MP4.with_suffix(".webm"))
            print("ffmpeg missing; wrote", OUT / "walkthrough.webm")
        for leftover in vdir.glob("*"):
            leftover.unlink(missing_ok=True)
        vdir.rmdir()
        return 0
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
