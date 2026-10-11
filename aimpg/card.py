"""`aimpg report --share`: a receipt card for social posts (1200×630, the size link
previews use). Totals only: never repo names, commit messages, paths or code.

Writes an SVG (always) and a PNG next to it when the machine can render one
(macOS Quick Look, rsvg-convert, or cairosvg), and returns a one-line post.
"""

from __future__ import annotations

import html
import re
import shutil
import statistics
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from aimpg.coach import tips as coach_tips
from aimpg.cost import total_cost
from aimpg.energy import total_wh
from aimpg.receipt import KEPT, task_energy

W, H = 1200, 630


@dataclass
class CardNumbers:
    days: int
    usd: float
    commits: int
    kwh: tuple[float, float]
    typical_usd: float | None
    typical_label: str
    tip: str | None
    cost_per_working: float | None


def numbers(parsed, attribution, since: float, now: float, judged=None) -> CardNumbers:
    in_window = [r for r in parsed.requests if r.ts >= since]
    energies = task_energy(attribution.tasks)
    usd, _ = total_cost(in_window)
    wh = total_wh(in_window)
    with_work = [e for e in energies if e.task.requests]
    kept = [e for e in with_work if e.task.status in KEPT]
    pool = kept if len(kept) >= 5 else with_work
    typical = statistics.median(e.usd for e in pool) if pool else None
    found = coach_tips(in_window, attribution)
    tip = None
    fresh = next((t for t in found if t.title.startswith("Start a fresh session")), None)
    pct = re.match(r"\d+%", fresh.measured) if fresh else None
    if pct:
        tip = f"{pct.group(0)} of my agents' tokens re-read conversation from before my last commit"
    cpw = judged.cost_per_durable() if judged is not None and judged.judged else None
    return CardNumbers(round((now - since) / 86400), usd, len(energies), (wh.low / 1000, wh.high / 1000), typical,
                       "per kept commit" if pool is kept else "per commit", tip, cpw)


def _money(x: float) -> str:
    return f"${x:,.0f}" if x >= 100 else f"${x:,.2f}"


def svg(n: CardNumbers) -> str:
    e = html.escape
    big = _money(n.cost_per_working) if n.cost_per_working is not None else (_money(n.typical_usd) if n.typical_usd else "—")
    big_label = "per working change (still standing after 30 days)" if n.cost_per_working is not None else n.typical_label
    kwh = f"{n.kwh[0]:,.1f}–{n.kwh[1]:,.0f} kWh" if n.kwh[1] >= 10 else f"{n.kwh[0]:,.2f}–{n.kwh[1]:,.1f} kWh"
    rows = [("AI spend at API list prices", _money(n.usd)), ("Commits made with AI help", f"{n.commits:,}"),
            ("Energy (estimate, range)", kwh)]
    row_svg = "".join(
        f'<text x="72" y="{392 + i * 52}" class="k">{e(k)}</text><text x="1128" y="{392 + i * 52}" class="v" text-anchor="end">{e(v)}</text>'
        f'<line x1="72" y1="{408 + i * 52}" x2="1128" y2="{408 + i * 52}" class="rule"/>'
        for i, (k, v) in enumerate(rows))
    tip = f'<text x="72" y="566" class="tip">↺ {e(n.tip)}</text>' if n.tip else ""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>
.bg{{fill:#10292a}} .k{{font:500 26px "IBM Plex Sans",Helvetica,Arial,sans-serif;fill:#9fb9b2}}
.v{{font:600 28px "IBM Plex Mono",Menlo,monospace;fill:#e2ece8}} .rule{{stroke:#24433f;stroke-width:1.5}}
.eyebrow{{font:600 22px "IBM Plex Mono",Menlo,monospace;fill:#f0ad3a;letter-spacing:3px}}
.big{{font:800 132px "Archivo","Helvetica Neue",Arial,sans-serif;fill:#ffffff}}
.biglabel{{font:500 30px "IBM Plex Sans",Helvetica,Arial,sans-serif;fill:#e2ece8}}
.tip{{font:500 24px "IBM Plex Sans",Helvetica,Arial,sans-serif;fill:#f0ad3a}}
.foot{{font:500 22px "IBM Plex Mono",Menlo,monospace;fill:#9fb9b2}}
</style>
<rect class="bg" width="{W}" height="{H}"/>
<rect x="0" y="0" width="{W}" height="8" fill="#f0ad3a"/>
<text x="72" y="92" class="eyebrow">MY AI CODING · LAST {n.days} DAYS</text>
<text x="66" y="236" class="big">{e(big)}</text>
<text x="72" y="290" class="biglabel">{e(big_label)}</text>
{row_svg}
{tip}
<text x="1128" y="606" class="foot" text-anchor="end">see yours: uvx aimpg report</text>
</svg>
'''


def post_text(n: CardNumbers) -> str:
    head = (f"My AI coding costs {_money(n.cost_per_working)} per working change"
            if n.cost_per_working is not None else
            f"My AI coding: {_money(n.typical_usd)} {n.typical_label}" if n.typical_usd else "My AI coding")
    return (f"{head} ({_money(n.usd)} over {n.commits} commits in {n.days} days, at API list prices). "
            "Measured from my own Claude Code/Codex logs with aimpg. See yours: uvx aimpg report")


CHROMES = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
           "/Applications/Chromium.app/Contents/MacOS/Chromium",
           "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
           "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
           "google-chrome", "chromium", "chromium-browser", "microsoft-edge")


def to_png(svg_path: Path) -> Path | None:
    """Best effort, no new dependencies: rsvg-convert, a headless Chrome-family browser, or cairosvg."""
    png = svg_path.with_suffix(".png")
    if shutil.which("rsvg-convert"):
        if subprocess.run(["rsvg-convert", "-w", str(W), "-o", str(png), str(svg_path)], capture_output=True).returncode == 0:
            return png
    for browser in CHROMES:
        exe = browser if Path(browser).exists() else shutil.which(browser)
        if not exe:
            continue
        png.unlink(missing_ok=True)
        with tempfile.TemporaryDirectory() as profile:
            proc = subprocess.Popen([exe, "--headless", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                                     "--no-default-browser-check", "--disable-extensions", f"--user-data-dir={profile}",
                                     f"--window-size={W},{H}", f"--screenshot={png}", svg_path.resolve().as_uri()],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
            # Chrome sometimes writes the screenshot and then doesn't exit: wait for the file, then stop it
            deadline = time.time() + 60
            while time.time() < deadline and proc.poll() is None and not (png.exists() and png.stat().st_size > 0):
                time.sleep(0.25)
            time.sleep(0.5)
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)
        if png.exists() and png.stat().st_size > 0:
            return png
    try:
        import cairosvg  # type: ignore

        cairosvg.svg2png(url=str(svg_path), write_to=str(png), output_width=W)
        return png
    except Exception:
        return None


def write(n: CardNumbers, path: Path) -> tuple[Path, Path | None]:
    path = path.with_suffix(".svg")
    path.write_text(svg(n))
    return path, to_png(path)
