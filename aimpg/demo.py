"""`aimpg report --demo`: a sample receipt from made-up data, for people without AI coding logs.

It builds a small throwaway git repo and Claude Code session logs in a temp folder, then runs the
normal report on them, so the demo shows exactly what the real receipt looks like. Nothing is read
from or written to the user's own logs, repos or aimpg history.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

DAY = 86400
EMAIL = "you@example.com"

# (days ago, subject, model, requests): two months of a small web app, mostly on the largest model
COMMITS = [
    (58, "feat: user signup form", "claude-opus-5-5", 14),
    (55, "fix: validate email before submit", "claude-opus-5-5", 6),
    (52, "feat: password reset flow", "claude-opus-5-5", 22),
    (49, "refactor: move auth helpers into one module", "claude-opus-5-5", 18),
    (46, "feat: experimental magic-link login", "claude-opus-5-5", 25),  # removed later: never shipped for good
    (43, "test: cover the reset token expiry", "claude-sonnet-5-5", 8),
    (40, "fix: off-by-one in pagination", "claude-sonnet-5-5", 5),
    (37, "feat: CSV export of orders", "claude-opus-5-5", 16),
    (34, "chore: bump dependencies", "claude-haiku-5-5", 3),
    (27, "feat: order search with filters", "claude-opus-5-5", 20),
    (24, "fix: timezone in order dates", "claude-opus-5-5", 9),
    (21, "remove the magic-link experiment", "claude-sonnet-5-5", 4),
    (18, "feat: dark mode", "claude-opus-5-5", 17),
    (15, "fix: dark mode contrast on buttons", "claude-sonnet-5-5", 6),
    (12, "feat: invoice PDFs", "claude-opus-5-5", 24),
    (9, "perf: cache the product list", "claude-opus-5-5", 11),
    (6, "fix: invoice totals rounding", "claude-sonnet-5-5", 7),
    (3, "feat: email receipts", "claude-opus-5-5", 19),
    (1, "docs: setup guide", "claude-haiku-5-5", 3),
]


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _git(repo: Path, *args: str, when: float | None = None) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")  # the user's git config can't change the demo
    if when is not None:
        env.update(GIT_AUTHOR_DATE=f"@{int(when)} +0000", GIT_COMMITTER_DATE=f"@{int(when)} +0000")
    return subprocess.run(["git", "-C", str(repo), *args], env=env, check=True, capture_output=True, text=True).stdout.strip()


def _row(session: str, cwd: str, ts: float, n: int, model: str, content: list, carried: int) -> dict:
    return {
        "type": "assistant", "sessionId": session, "cwd": cwd, "timestamp": _iso(ts), "isSidechain": False,
        "version": "2.1.287", "requestId": f"req_{session}_{n}",
        "message": {"id": f"msg_{session}_{n}", "model": model, "content": content,
                    "usage": {"input_tokens": 1200, "cache_creation_input_tokens": 9000,
                              "cache_read_input_tokens": 40000 + carried + n * 6000, "output_tokens": 1400}},
    }


def build(root: Path, now: float | None = None) -> tuple[Path, Path]:
    """Write the demo repo and logs under root. Returns (logs folder, repo)."""
    now = now or time.time()
    repo = root / "demo-shop"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", EMAIL)
    _git(repo, "config", "user.name", "You")
    (repo / "README.md").write_text("demo shop\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "initial commit", when=now - 60 * DAY)

    logs = root / "projects" / "-demo-shop"
    logs.mkdir(parents=True)
    carried = 0
    for i, (ago, subject, model, requests) in enumerate(COMMITS):
        t = now - ago * DAY
        session, cwd = f"demo{i}", str(repo)
        if subject.startswith("remove the magic-link"):
            _git(repo, "rm", "-q", "magic_link.py")
        else:
            name = "magic_link.py" if "magic-link" in subject else f"app/change_{i}.py"
            path = repo / name
            path.parent.mkdir(exist_ok=True)
            path.write_text("".join(f"line_{i}_{k} = {k}\n" for k in range(12)))
            _git(repo, "add", name)
        start = t - requests * 70
        rows = [_row(session, cwd, start + n * 70, n, model, [{"type": "text", "text": "ok"}], carried) for n in range(requests)]
        call = [{"type": "tool_use", "id": f"tu{i}", "name": "Bash", "input": {"command": f"git commit -m '{subject}'"}}]
        rows.append(_row(session, cwd, t - 2, requests, model, call, carried))
        rows.append({"type": "user", "sessionId": session, "cwd": cwd, "timestamp": _iso(t + 1),
                     "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"tu{i}", "content": "done"}]}})
        _git(repo, "commit", "-q", "-m", subject, when=t)
        carried = 30000 if i % 3 else 0  # some sessions carry on into the next task
        (logs / f"{session}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return logs.parent, repo
