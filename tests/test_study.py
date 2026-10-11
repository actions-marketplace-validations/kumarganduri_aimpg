import random

import pytest

from aimpg.replay.run import Record
from aimpg.replay.study import compare, holm, render, wilson


def rec(repo, commit, setup, passed, cost, tokens=1000, repeat=0):
    return Record(f"{repo}{commit}{setup}{repeat}", repo, commit, setup, repeat, "passed" if passed else "tests_failed",
                  passed, "m", cost, 10.0, [[tokens, 0, 0, 0]], "ok", "", True, "claude")


def study(repos=6, commits=8, repeats=3, chal_cost=0.5, chal_pass=0.9, base_pass=0.9, tokens_ratio=1.0, seed=1):
    rng = random.Random(seed)
    out = []
    for r in range(repos):
        for c in range(commits):
            for k in range(repeats):
                out.append(rec(f"repo{r}", f"c{c}", "base", rng.random() < base_pass, 0.10 * (0.8 + 0.4 * rng.random()), 1000, k))
                out.append(rec(f"repo{r}", f"c{c}", "chal", rng.random() < chal_pass, 0.10 * chal_cost * (0.8 + 0.4 * rng.random()),
                               int(1000 * tokens_ratio), k))
    return out


def test_wilson_interval():
    lo, hi = wilson(8, 10)
    assert lo == pytest.approx(0.49, abs=0.01) and hi == pytest.approx(0.94, abs=0.01)
    assert wilson(0, 0) == (0.0, 1.0)


def test_a_real_halving_is_a_headline():
    c = compare(study(chal_cost=0.5), "base", "chal")
    holm([c])
    assert c.ratio_per_solved == pytest.approx(0.5, abs=0.08)
    assert c.ratio_per_solved_ci[1] < 1 and c.cheaper_in_repos == 6 and c.headline


def test_no_difference_is_not_a_headline():
    c = compare(study(chal_cost=1.0), "base", "chal")
    holm([c])
    assert c.ratio_per_solved_ci[0] < 1 < c.ratio_per_solved_ci[1] and not c.headline


def test_cheap_per_attempt_but_failing_costs_more_per_solved_task():
    c = compare(study(chal_cost=0.7, chal_pass=0.3), "base", "chal")
    assert c.cost_per_attempt["chal"] < c.cost_per_attempt["base"]
    assert c.ratio_per_solved > 1  # cheaper per token, dearer per solved task


def test_one_repo_cannot_carry_a_headline():
    data = [r for r in study(chal_cost=1.15) if r.repo != "repo0"] + [r for r in study(chal_cost=0.1, seed=2) if r.repo == "repo0"]
    c = compare(data, "base", "chal")
    holm([c])
    assert c.cheaper_in_repos < 5 and not c.headline


def test_tokens_ratio_and_render():
    c = compare(study(chal_cost=1.0, tokens_ratio=0.6), "base", "chal")
    assert c.ratio_tokens == pytest.approx(0.6, abs=0.01) and c.ratio_tokens_ci[1] < 1
    assert "-40%" in render([c])


def test_holm_adjusts_across_comparisons():
    a = compare(study(chal_cost=0.5), "base", "chal")
    b = compare(study(chal_cost=1.0, seed=3), "base", "chal")
    holm([a, b])
    assert a.p_holm >= a.p_per_solved and b.p_holm >= b.p_per_solved


def test_study_report_from_result_files(tmp_path, capsys):
    import json
    from dataclasses import asdict

    from aimpg.replay import study_cli

    folder = tmp_path / "runs"
    folder.mkdir()
    data = study(chal_cost=0.5)
    for repo in {r.repo for r in data}:
        with open(folder / f"{repo}.jsonl", "w") as fh:
            for r in data:
                if r.repo == repo:
                    d = asdict(r)
                    d["setup"] = {"base": "claude-code", "chal": "claude-code@haiku"}[r.setup]
                    fh.write(json.dumps(d) + "\n")
    plan = {"name": "t", "cutoff": "2026-07-01", "commits_per_repo": 8, "repeats": 3, "baseline": "plain",
            "challengers": ["haiku"], "repos": []}
    assert study_cli._report(plan, folder=folder) == 0
    out = capsys.readouterr().out
    assert "claude-code@haiku vs claude-code" in out and "| yes |" in out
    assert (tmp_path / "runs-report.md").exists() and (tmp_path / "runs-report.json").exists()


def test_primary_metric_decides_the_headline():
    # tokens cut by 40% at the same cost: a token-saver's claim holds on tokens, not on dollars
    data = study(chal_cost=1.0, tokens_ratio=0.6)
    on_tokens, on_cost = compare(data, "base", "chal", primary="tokens"), compare(data, "base", "chal")
    holm([on_tokens]), holm([on_cost])
    assert on_tokens.headline and on_tokens.cheaper_in_repos == 6
    assert not on_cost.headline
