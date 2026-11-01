"""Render clip.html to PNG frames with the installed Chrome: one browser, render(t) per frame."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

FPS, SECONDS = 30, float(sys.argv[1]) if len(sys.argv) > 1 else 58
out = Path("frames"); out.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")
    page = browser.new_page(viewport={"width": 1280, "height": 720})
    page.goto(f"file://{Path('clip.html').resolve()}")
    page.wait_for_function("document.title === 'ready'")
    for i in range(int(FPS * SECONDS)):
        page.evaluate(f"render({i / FPS})")
        page.screenshot(path=str(out / f"f{i:05d}.png"))
    browser.close()
