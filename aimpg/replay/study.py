"""Statistics for a pre-registered multi-repo study (launch-review design, 2026-10-11).

For each challenger against the baseline, across every repo in the results:

    solve rate            with a 95% Wilson interval, overall and per repo
    cost per attempt      intention-to-treat: every run counts, failures included
    cost per solved task  total $ / tasks solved; the challenger/baseline ratio gets
                          a 95% interval from a bootstrap that resamples repos, then
                          commits within each repo (runs of one commit move together)
    tokens per attempt    the unit token-savers advertise; same ratio and interval
    direction by repo     in how many repos the challenger came out cheaper per solved task

Headline rule (pre-registered): a claim is stated only when its interval
excludes "no difference" after Holm correction across the primary comparisons
AND its direction holds in at least 5 of the 6+ repos (or all repos if fewer).
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean

from aimpg.replay.run import Record

BOOTSTRAP = 4000
Z95 = 1.959964


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def _tokens(r: Record) -> int:
    return sum(sum(u) for u in r.usages)


@dataclass
class Arm:
    setup: str
    runs: int = 0
    solved: int = 0
    usd: float = 0.0
    tokens: int = 0

    @property
    def solve_rate(self) -> float:
        return self.solved / self.runs if self.runs else 0.0

    @property
    def usd_per_solved(self) -> float | None:
        return self.usd / self.solved if self.solved else None


@dataclass
class Comparison:
    baseline: str
    challenger: str
    repos: int
    commits: int
    arms: dict[str, Arm]
    solve_ci: dict[str, tuple[float, float]]
    cost_per_attempt: dict[str, float]
    ratio_per_solved: float | None
    ratio_per_solved_ci: tuple[float, float] | None
    ratio_tokens: float | None
    ratio_tokens_ci: tuple[float, float] | None
    p_per_solved: float | None
    cheaper_in_repos: int
    per_repo: dict[str, dict] = field(default_factory=dict)
    p_holm: float | None = None
    headline: bool = False


def _group(records: list[Record]) -> dict[str, dict[str, list[Record]]]:
    """repo → commit → runs."""
    out: dict[str, dict[str, list[Record]]] = defaultdict(lambda: defaultdict(list))
    for r in records:
        out[r.repo][r.commit].append(r)
    return out


def _ratios(groups, baseline: str, challenger: str) -> tuple[float | None, float | None]:
    sums = {s: [0.0, 0, 0] for s in (baseline, challenger)}  # usd, solved, tokens
    for commits in groups:
        for runs in commits:
            for r in runs:
                if r.setup in sums:
                    sums[r.setup][0] += r.cost_usd
                    sums[r.setup][1] += r.passed
                    sums[r.setup][2] += _tokens(r)
    b, c = sums[baseline], sums[challenger]
    per_solved = (c[0] / c[1]) / (b[0] / b[1]) if b[1] and c[1] and b[0] else None
    n_b = sum(1 for g in groups for runs in g for r in runs if r.setup == baseline)
    n_c = sum(1 for g in groups for runs in g for r in runs if r.setup == challenger)
    tokens = (c[2] / n_c) / (b[2] / n_b) if n_b and n_c and b[2] else None
    return per_solved, tokens


def compare(records: list[Record], baseline: str, challenger: str, *, seed: int = 0) -> Comparison:
    mine = [r for r in records if r.setup in (baseline, challenger)]
    by_repo = _group(mine)
    # only commits both arms attempted (a commit excluded for one setup is excluded for both)
    for repo, commits in by_repo.items():
        for sha in [s for s, runs in commits.items() if {r.setup for r in runs} != {baseline, challenger}]:
            del commits[sha]
    mine = [r for commits in by_repo.values() for runs in commits.values() for r in runs]
    arms = {s: Arm(s) for s in (baseline, challenger)}
    for r in mine:
        a = arms[r.setup]
        a.runs += 1
        a.solved += r.passed
        a.usd += r.cost_usd
        a.tokens += _tokens(r)
    groups = [list(commits.values()) for commits in by_repo.values()]
    point, tok_point = _ratios(groups, baseline, challenger)

    rng = random.Random(seed)
    boot, boot_tok = [], []
    for _ in range(BOOTSTRAP if groups else 0):
        sample = []
        for _ in groups:  # resample repos, then commits within each
            g = groups[rng.randrange(len(groups))]
            sample.append([g[rng.randrange(len(g))] for _ in g])
        r, t = _ratios(sample, baseline, challenger)
        if r is not None:
            boot.append(r)
        if t is not None:
            boot_tok.append(t)

    def ci(xs: list[float]) -> tuple[float, float] | None:
        if len(xs) < 100:
            return None
        xs = sorted(xs)
        return (xs[int(0.025 * (len(xs) - 1))], xs[int(0.975 * (len(xs) - 1))])

    p = None
    if boot and point is not None:
        below = sum(1 for x in boot if x < 1) / len(boot)
        p = min(1.0, 2 * min(below, 1 - below))

    per_repo, cheaper = {}, 0
    for repo, commits in by_repo.items():
        r, _ = _ratios([list(commits.values())], baseline, challenger)
        k = {s: sum(x.passed for runs in commits.values() for x in runs if x.setup == s) for s in arms}
        n = {s: sum(1 for runs in commits.values() for x in runs if x.setup == s) for s in arms}
        per_repo[repo] = {"ratio_per_solved": r, "solved": k, "runs": n, "commits": len(commits)}
        cheaper += r is not None and r < 1
    return Comparison(
        baseline, challenger, len(by_repo), sum(len(c) for c in by_repo.values()), arms,
        {s: wilson(a.solved, a.runs) for s, a in arms.items()},
        {s: a.usd / a.runs if a.runs else 0.0 for s, a in arms.items()},
        point, ci(boot), tok_point, ci(boot_tok), p, cheaper, per_repo,
    )


def holm(comparisons: list[Comparison], *, alpha: float = 0.05) -> None:
    """Holm-adjusted p-values and the headline rule, in place."""
    ordered = sorted([c for c in comparisons if c.p_per_solved is not None], key=lambda c: c.p_per_solved)
    m, running = len(ordered), 0.0
    for i, c in enumerate(ordered):
        running = max(running, min(1.0, (m - i) * c.p_per_solved))
        c.p_holm = running
    for c in comparisons:
        need = min(5, c.repos) if c.repos >= 6 else c.repos
        direction = c.cheaper_in_repos if (c.ratio_per_solved or 1) < 1 else c.repos - c.cheaper_in_repos
        c.headline = bool(c.p_holm is not None and c.p_holm < alpha and c.repos and direction >= need)


def render(comparisons: list[Comparison]) -> str:
    def pct(x):
        return "—" if x is None else f"{x - 1:+.0%}"

    lines = ["| challenger vs baseline | repos · commits | solved (95% CI) | $ per attempt | $ per solved task (95% CI) | tokens per attempt (95% CI) | cheaper in | headline |",
             "|---|---|---|---|---|---|---|---|"]
    for c in comparisons:
        b, ch = c.arms[c.baseline], c.arms[c.challenger]
        lo, hi = c.solve_ci[c.challenger]
        rc = c.ratio_per_solved_ci
        tc = c.ratio_tokens_ci
        lines.append(
            f"| {c.challenger} vs {c.baseline} | {c.repos} · {c.commits} | {ch.solve_rate:.0%} ({lo:.0%}–{hi:.0%}) vs {b.solve_rate:.0%} "
            f"| ${c.cost_per_attempt[c.challenger]:.2f} vs ${c.cost_per_attempt[c.baseline]:.2f} "
            f"| {pct(c.ratio_per_solved)} ({pct(rc[0]) if rc else '—'} to {pct(rc[1]) if rc else '—'}) "
            f"| {pct(c.ratio_tokens)} ({pct(tc[0]) if tc else '—'} to {pct(tc[1]) if tc else '—'}) "
            f"| {c.cheaper_in_repos} of {c.repos} repos | {'yes' if c.headline else 'no'} |")
    lines += ["", "Intervals: 95%, bootstrap over repos then commits. Headline = Holm-adjusted p < 0.05 and the direction holds in ≥5 of 6+ repos."]
    return "\n".join(lines)
