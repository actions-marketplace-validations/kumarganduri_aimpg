"""Team numbers without a server: per-commit cost notes in git, rolled up in CI.

    developer (opt-in)                         the repo, in CI (GitHub Action)
    aimpg notes push ──► refs/notes/aimpg ──►  aimpg team pr      AI cost of a pull request
      a small note on each of YOUR commits     aimpg team rollup  cost per working change,
      (cost, energy range, request count)                         waste ratio, weekly trend

A note is metadata only, for example
    {"aimpg_note": 1, "usd": 2.05, "wh": [36.6, 313.0], "requests": 31, "tier": "exact"}
Never prompts, code or model output. Notes go only on commits authored by the
person writing them. Anyone who can read the repo can read the notes.

The rollup never ranks people. It shows team numbers only when at least
MIN_GROUP people share notes in the period (a smaller team can lower it on
purpose with --min-group). Working changes are judged in CI from the repo's
own history, the same way as `aimpg report`.
"""

from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from aimpg import durable
from aimpg.gitkept import DAY, GitError, _git, load_commits, user_email

NOTES_REF = "aimpg"
FULL_REF = f"refs/notes/{NOTES_REF}"
NOTE_VERSION = 1
MIN_GROUP = 5


# ---------------------------------------------------------------- notes

def note_for(e) -> dict:
    """e: receipt.TaskEnergy."""
    return {"aimpg_note": NOTE_VERSION, "usd": round(e.usd + e.lead_up_usd, 2),
            "wh": [round(e.total.low, 1), round(e.total.high, 1)],
            "requests": len(e.task.requests) + len(e.task.lead_up), "tier": e.task.attribution}


def read_notes(repo: str | Path) -> dict[str, dict]:
    """commit sha → note, for every valid aimpg note in the repo."""
    try:
        listing = _git(repo, "notes", f"--ref={NOTES_REF}", "list")
    except GitError:
        return {}
    pairs = [line.split() for line in listing.splitlines() if line.strip()]
    if not pairs:
        return {}
    blobs = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"],
                           input=("\n".join(b for b, _ in pairs) + "\n").encode(), capture_output=True).stdout
    out, pos = {}, 0
    for blob, sha in pairs:  # sizes are in bytes, so parse bytes
        header_end = blobs.index(b"\n", pos)
        size = int(blobs[pos:header_end].split()[2])
        body = blobs[header_end + 1: header_end + 1 + size]
        pos = header_end + 1 + size + 1
        try:
            note = json.loads(body)
        except ValueError:
            continue
        if isinstance(note, dict) and note.get("aimpg_note") == NOTE_VERSION and _valid(note):
            out[sha] = note
    return out


def _valid(note: dict) -> bool:
    wh = note.get("wh")
    return (isinstance(note.get("usd"), (int, float)) and note["usd"] >= 0 and isinstance(wh, list) and len(wh) == 2
            and all(isinstance(x, (int, float)) and x >= 0 for x in wh) and isinstance(note.get("requests"), int))


def write_notes(repo: str, energies, *, author: str | None = None) -> tuple[int, int]:
    """Note each AI-assisted commit of `repo` that `author` made. Returns (written, skipped)."""
    me = (author or user_email(repo)).lower()
    if not me:
        raise GitError("set git user.email first: notes go only on your own commits")
    existing = read_notes(repo)
    written = skipped = 0
    for e in energies:
        if e.task.repo != repo or e.task.author.lower() != me or e.total.high <= 0:
            skipped += 1
            continue
        note = note_for(e)
        old = existing.get(e.task.sha)
        if old == note or (old and old.get("requests", 0) > note["requests"]):  # keep the fuller one
            continue
        _git(repo, "notes", f"--ref={NOTES_REF}", "add", "-f", "-F", "-", e.task.sha, stdin=json.dumps(note, sort_keys=True))
        written += 1
    return written, skipped


def push(repo: str, remote: str = "origin") -> str:
    """Merge teammates' notes from the remote (keeping ours on the rare same-commit clash), then push."""
    incoming = f"refs/notes/{NOTES_REF}-incoming"
    for attempt in range(2):
        try:
            _git(repo, "fetch", "--quiet", remote, f"+{FULL_REF}:{incoming}")
            _git(repo, "notes", f"--ref={NOTES_REF}", "merge", "-s", "ours", "--quiet", incoming)
        except GitError as exc:
            if "couldn't find remote ref" not in str(exc).lower() and "could not find remote ref" not in str(exc).lower():
                raise
        try:
            _git(repo, "push", "--quiet", remote, FULL_REF)
            return f"pushed {FULL_REF} to {remote}"
        except GitError:
            if attempt:
                raise
    return ""


# ---------------------------------------------------------------- pull request

def pr_summary(repo: str, shas: list[str]) -> dict:
    notes = read_notes(repo)
    mine = {s: notes[s] for s in shas if s in notes}
    return {"commits": len(shas), "noted": len(mine), "usd": round(sum(n["usd"] for n in mine.values()), 2),
            "wh": [round(sum(n["wh"][0] for n in mine.values()), 1), round(sum(n["wh"][1] for n in mine.values()), 1)],
            "requests": sum(n["requests"] for n in mine.values())}


def pr_markdown(s: dict) -> str:
    lines = ["### ⚡ AI cost of this pull request", ""]
    if not s["noted"]:
        lines += [f"No aimpg notes on the {s['commits']} commits here yet. "
                  "Each author can add theirs with `aimpg notes push` (metadata only)."]
    else:
        lines += [f"**${s['usd']:,.2f}** API-equivalent · **{_wh(s['wh'])}** · {s['requests']:,} model requests",
                  "", f"<sub>{s['noted']} of {s['commits']} commits have notes from their authors · "
                  "[aimpg](https://github.com/kumarganduri/aimpg) · energy is a range because model sizes aren't public"
                  " · see your own: `uvx aimpg report`</sub>"]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- rollup

def rollup(repo: str, *, days: int = 90, now: float | None = None, min_group: int = MIN_GROUP) -> dict:
    import time

    now = now or time.time()
    since = now - days * DAY
    notes = read_notes(repo)
    commits = {c.sha: c for c in load_commits(repo, since, reflog=False)}
    noted = {sha: (commits[sha], n) for sha, n in notes.items() if sha in commits}
    people = {c.author_email.lower() for c, _ in noted.values()}
    out = {"repo": Path(repo).name, "days": days, "contributors": len(people), "min_group": min_group,
           "enough": len(people) >= min_group}
    if not out["enough"]:
        return out
    ledger = {sha: {"repo": repo, "sha": sha, "ts": c.ts, "usd": n["usd"], "wh_low": n["wh"][0], "wh_high": n["wh"][1]}
              for sha, (c, n) in noted.items()}
    judged = durable.judge(ledger, now)
    weeks = defaultdict(lambda: {"usd": 0.0, "commits": 0})
    for c, n in noted.values():
        y, w, _ = datetime.fromtimestamp(c.ts, tz=timezone.utc).isocalendar()
        weeks[f"{y}-W{w:02d}"]["usd"] += n["usd"]
        weeks[f"{y}-W{w:02d}"]["commits"] += 1
    out.update({
        "usd": round(sum(n["usd"] for _, n in noted.values()), 2),
        "wh": [round(sum(n["wh"][0] for _, n in noted.values()), 1), round(sum(n["wh"][1] for _, n in noted.values()), 1)],
        "noted_commits": len(noted),
        "cost_per_working_change": judged.cost_per_durable(),
        "waste_ratio": judged.waste_ratio(),
        "judged": {"working": len(judged.durable), "reverted": len(judged.reverted), "reworked": len(judged.reworked),
                   "not_kept": len(judged.not_kept), "too_new": len(judged.too_new)},
        "weeks": {k: {"usd": round(v["usd"], 2), "commits": v["commits"]} for k, v in sorted(weeks.items())},
    })
    return out


def rollup_markdown(r: dict) -> str:
    lines = [f"### ⚡ AI cost for {r['repo']} · last {r['days']} days", ""]
    if not r["enough"]:
        lines.append(f"{r['contributors']} people share aimpg notes here; team numbers appear at {r['min_group']} "
                     "so no one's individual cost can be read off the totals.")
        return "\n".join(lines) + "\n"
    j = r["judged"]
    cpw = f"${r['cost_per_working_change']:,.2f}" if r["cost_per_working_change"] is not None else "not yet"
    waste = f"{r['waste_ratio']:.0%}" if r["waste_ratio"] is not None else "not yet"
    lines += [
        f"| | |", "|---|---|",
        f"| AI spend (API-equivalent) | **${r['usd']:,.2f}** over {r['noted_commits']} commits |",
        f"| Energy | {_wh(r['wh'])} |",
        f"| **Cost per working change** | **{cpw}** |",
        f"| Waste ratio (spend on work that didn't last) | {waste} |",
        f"| Judged after 30 days | {j['working']} lasted · {j['reverted']} reverted · {j['reworked']} reworked · {j['not_kept']} never merged · {j['too_new']} too new |",
        "", "| week | AI spend | commits |", "|---|---|---|",
        *[f"| {w} | ${v['usd']:,.2f} | {v['commits']} |" for w, v in r["weeks"].items()],
        "", f"<sub>{r['contributors']} people share notes · no per-person numbers, by design · "
        "[aimpg](https://github.com/kumarganduri/aimpg) · see your own: `uvx aimpg report`</sub>",
    ]
    return "\n".join(lines) + "\n"


def _wh(v: list[float]) -> str:
    lo, hi = v
    return f"{lo / 1000:,.2f}–{hi / 1000:,.2f} kWh" if hi >= 1000 else f"{lo:,.1f}–{hi:,.1f} Wh"
