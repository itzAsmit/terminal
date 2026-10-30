"""Regenerate the README assets: assets/demo.gif plus act stills.

Renders `seance demo --json` inside scripts/terminal_mock.html (an HTML mock
of a macOS Terminal.app window) with Playwright/Chromium, so the Mac look is
identical no matter what OS the dev machine runs. Frames are assembled into
an animated GIF with Pillow.

Usage:
    pip install playwright pillow && playwright install chromium
    python scripts/capture_assets.py

Outputs (committed to the repo):
    assets/demo-wail.png, assets/demo-fail.png, assets/demo-journal.png
    assets/demo.gif
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
ASSETS = ROOT / "assets"
BUILD = ROOT / "scripts" / "_build"
MOCK = ROOT / "scripts" / "terminal_mock.html"

# (asset name, act number whose END is shown) — act 4 is the final act.
STILLS = [("demo-wail.png", 2), ("demo-fail.png", 3), ("demo-journal.png", 4)]

GIF_FRAME_MS = 140
GIF_WAIT_MS = 80  # screenshot cadence


def demo_events() -> list[dict]:
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    r = subprocess.run(
        [sys.executable, "-m", "seance", "demo", "--json"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=True,
    )
    return json.loads(r.stdout)


def open_page(browser, scale: float):
    page = browser.new_page(
        viewport={"width": 900, "height": 780}, device_scale_factor=scale
    )
    page.goto(MOCK.as_uri())
    return page


def shoot(page, path: Path) -> None:
    page.evaluate("() => window.seanceSolidCaret()")
    page.wait_for_timeout(60)
    page.screenshot(path=str(path), clip=page.evaluate("() => window.seanceRect()"))


def main() -> None:
    events = demo_events()
    ASSETS.mkdir(exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        # --- PNG stills at 2x (retina-crisp), one per key act ----------------
        page = open_page(browser, scale=2)
        page.evaluate("(e) => window.seanceInit(e)", events)
        acts = page.evaluate("() => window.seanceActs()")
        stills: dict[int, Path] = {}
        for asset_name, act in STILLS:
            if act < acts:
                page.evaluate("(k) => window.seanceRunToAct(k)", act + 1)
                page.wait_for_function("() => window.__paused === true", timeout=120_000)
            else:
                page.evaluate("() => window.seanceRunAll()")
                page.wait_for_function("() => window.__done === true", timeout=120_000)
            page.wait_for_timeout(250)  # let the last typewriter settle
            out = ASSETS / asset_name
            shoot(page, out)
            stills[act] = out
            print(f"still  {out.relative_to(ROOT)}  (end of act {act})")
        page.close()

        # --- GIF frames at 1x, full session ----------------------------------
        page = open_page(browser, scale=1)
        page.evaluate("(e) => window.seanceInit(e)", events)
        rect = page.evaluate("() => window.seanceRect()")
        page.evaluate("() => window.seanceRunAll()")
        frames: list[Path] = []
        idx = 0
        t_end = time.time() + 120
        while time.time() < t_end:
            f = BUILD / f"frame-{idx:03d}.png"
            page.screenshot(path=str(f), clip=rect)
            frames.append(f)
            if page.evaluate("() => window.__done === true"):
                for _ in range(6):  # hold the final frame ~0.8s
                    frames.append(f)
                break
            page.wait_for_timeout(GIF_WAIT_MS)
            idx += 1
        page.close()
        browser.close()

    if not frames:
        raise SystemExit("no frames captured")

    gif_path = ASSETS / "demo.gif"
    imgs = [Image.open(f).convert("RGB").quantize(colors=160) for f in frames]
    imgs[0].save(
        gif_path,
        save_all=True,
        append_images=imgs[1:],
        duration=GIF_FRAME_MS,
        loop=0,
        optimize=True,
    )
    size_kb = gif_path.stat().st_size // 1024
    print(f"gif    {gif_path.relative_to(ROOT)}  ({len(frames)} frames, {size_kb} KB)")
    for f in BUILD.glob("frame-*.png"):
        f.unlink()


if __name__ == "__main__":
    main()
