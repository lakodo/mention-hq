"""Capture app screenshots for the docs, driving the demo database with a headless browser.

Boots the API against `hq-demo.db` (never your real DB) serving the built frontend, then walks
Playwright through each screen and writes PNGs into docs/assets/screenshots/. Regenerate with
`task docs:screenshots`, which reseeds and rebuilds first.

Prereqs: a built frontend (`task front:build`) and Chromium (`uv run playwright install
chromium`). Run from the backend directory.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from playwright.async_api import async_playwright

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
DEMO_DB = BACKEND / "hq-demo.db"
OUT = ROOT / "docs" / "assets" / "screenshots"

VIEWPORT = {"width": 1440, "height": 900}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(port: int) -> subprocess.Popen:
    env = {**os.environ, "DB_PATH": str(DEMO_DB), "SYNC_ON_STARTUP": "false"}
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=BACKEND,
        env=env,
    )


def _wait_healthy(port: int, timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.3)
    raise RuntimeError("demo server did not become healthy in time")


def _stack_task_path(port: int) -> str:
    """The route to the git-spice stack task — the best task detail to show (it has a Code lane)."""
    tasks = httpx.get(f"http://127.0.0.1:{port}/api/tasks", timeout=5).json()
    pick = next((t for t in tasks if "Datasets screen" in t["title"]), tasks[0])
    return f"/task/{pick['id'].removeprefix('task:')}"


async def _capture(port: int) -> list[str]:
    OUT.mkdir(parents=True, exist_ok=True)
    base = f"http://127.0.0.1:{port}"
    shots = [
        ("welcome", "/welcome"),
        ("board", "/"),
        ("task-detail", _stack_task_path(port)),
        ("catch-up", "/catchup"),
        ("timeline", "/timeline"),
        ("people", "/people"),
        ("admin", "/admin"),
    ]
    written = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(
            viewport=VIEWPORT,
            device_scale_factor=2,
            color_scheme="light",
            service_workers="block",
        )
        page = await context.new_page()
        for name, path in shots:
            await page.goto(f"{base}{path}", wait_until="networkidle")
            await page.wait_for_timeout(1200)  # let React Query paint and animations settle
            target = OUT / f"{name}.png"
            await page.screenshot(path=str(target))
            written.append(name)
            print(f"  captured {name}  ({path})")
        await browser.close()
    return written


async def _run() -> None:
    if not DEMO_DB.exists():
        raise SystemExit(f"No demo DB at {DEMO_DB}. Run `task back:seed` first.")
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        raise SystemExit("No built frontend. Run `task front:build` first.")

    port = _free_port()
    server = _start_server(port)
    try:
        _wait_healthy(port)
        await _capture(port)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
    print(f"\nScreenshots written to {OUT}")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
