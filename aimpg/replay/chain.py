"""The fresh-session experiment: does starting a new session after a commit really save?

aimpg's receipt says a share of tokens is conversation carried over from before
the last commit. That's measured. Whether a fresh session saves that much is a
counterfactual, because a fresh session has to rebuild some context. This
measures it on real commits:

    task 1 (commit c1) in a new Claude Code session S                       "chain-first"
        ├── continue: the code reset to c2's parent, `--resume S`, task 2   "chain-continue"
        └── fresh:    same code, a NEW session told only the subject of     "chain-fresh"
                      task 1, then task 2

Only task 2 is compared (task 1 is shared): tokens, list-price cost of task-2
requests only, and whether c2's own tests pass. Both arms record c2 as their
commit, so the study statistics pair them like any other comparison.
"""

from __future__ import annotations

import json

from aimpg.replay.run import Config, Record, run_one, task_text
from aimpg.replay.setups import Setup
from aimpg.replay.workspace import Commit, Layout

FIRST = Setup("chain-first", spec={"agent": "claude", "chain": "first"})
CONTINUE = Setup("chain-continue", spec={"agent": "claude", "chain": "continue"})
FRESH = Setup("chain-fresh", spec={"agent": "claude", "chain": "fresh"})


def pairs(commits: list[Commit]) -> list[tuple[Commit, Commit]]:
    """Consecutive qualifying commits of one repo, oldest first, not overlapping: (1,2), (3,4), ..."""
    by_repo: dict[str, list[Commit]] = {}
    for c in sorted(commits, key=lambda c: c.ts):
        by_repo.setdefault(c.repo, []).append(c)
    return [(cs[i], cs[i + 1]) for cs in by_repo.values() for i in range(0, len(cs) - 1, 2)]


def fresh_task(c1: Commit, c2: Commit, mode: str) -> str:
    return f'Earlier in this repo you finished this task: "{c1.subject}".\n\nNext task:\n\n{task_text(c2, mode)}'


def run_chain(c1: Commit, c2: Commit, repeat: int, layout: Layout, cfg: Config, *, attempt: int = 0,
              solutions: dict | None = None) -> list[Record]:
    solutions = solutions or {}
    tag = f"{c1.sha[:8]}-{c2.sha[:8]}"
    first = run_one(c1, FIRST, repeat, layout, cfg, attempt=attempt, solution=solutions.get(c1.sha),
                    run_id=f"{tag}-chain-first-r{repeat}-a{attempt}")
    if first.outcome in ("harness_error", "account_error"):
        return [first]
    run_dir = layout.run_dir(first.run_id)
    try:
        session = json.loads((run_dir / "result.json").read_text()).get("session_id")
    except (OSError, ValueError):
        session = None
    if not session:
        first.outcome, first.passed, first.note = "harness_error", False, "task 1 left no session id to resume"
        return [first]
    cont = run_one(c2, CONTINUE, repeat, layout, cfg, attempt=attempt, solution=solutions.get(c2.sha),
                   run_id=f"{tag}-chain-continue-r{repeat}-a{attempt}", extra_args=("--resume", session),
                   resume_dir=run_dir, price_from_tokens=True)
    fresh = run_one(c2, FRESH, repeat, layout, cfg, attempt=attempt, solution=solutions.get(c2.sha),
                    run_id=f"{tag}-chain-fresh-r{repeat}-a{attempt}", task=fresh_task(c1, c2, cfg.task_mode),
                    price_from_tokens=True)
    for r in (cont, fresh):
        r.extra.update(chain_prev=c1.sha, prev_outcome=first.outcome)
    return [first, cont, fresh]
