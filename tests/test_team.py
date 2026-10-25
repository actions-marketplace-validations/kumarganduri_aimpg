import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from aimpg import team
from aimpg.cli import main
from aimpg.energy import WhRange
from aimpg.model import Request, Task, Usage
from aimpg.receipt import TaskEnergy

DAY = 86400


def git(repo, *args, email=None, when=None):
    env = None
    if when:
        import os

        env = {**os.environ, "GIT_AUTHOR_DATE": f"@{int(when)} +0000", "GIT_COMMITTER_DATE": f"@{int(when)} +0000"}
    pre = ["-c", f"user.email={email}", "-c", "user.name=x"] if email else []
    return subprocess.run(["git", "-C", str(repo), *pre, *args], check=True, capture_output=True, text=True, env=env).stdout.strip()


def clone(origin, path, email):
    subprocess.run(["git", "clone", "-q", str(origin), str(path)], check=True, capture_output=True)
    git(path, "config", "user.email", email)
    git(path, "config", "user.name", email.split("@")[0])
    return path


def commit(repo, name, email, when):
    (repo / name).write_text(name)
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", f"feat: {name}", email=email, when=when)
    return git(repo, "rev-parse", "HEAD")


def energy(repo, sha, author, usd=1.0, wh=(10, 100), n=3):
    reqs = [Request(f"r{i}", "s", "claude-sonnet-5-5", 0.0, Usage(output=10), str(repo)) for i in range(n)]
    task = Task(str(repo), sha, time.time(), "x", "exact", "kept", requests=reqs, weights=[1.0] * n, author=author)
    return TaskEnergy(task, WhRange(*wh), WhRange(0, 0), usd=usd)


def setup(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    seed = clone(origin, tmp_path / "seed", "seed@x")
    commit(seed, "README", "seed@x", time.time() - 60 * DAY)
    git(seed, "push", "-q", "origin", "HEAD:main")
    return origin


def test_notes_go_only_on_your_own_commits_and_hold_only_metadata(tmp_path):
    origin = setup(tmp_path)
    ann = clone(origin, tmp_path / "ann", "ann@x")
    mine = commit(ann, "a", "ann@x", time.time() - 3 * DAY)
    theirs = commit(ann, "b", "bob@x", time.time() - 2 * DAY)
    written, skipped = team.write_notes(str(ann), [energy(ann, mine, "ann@x"), energy(ann, theirs, "bob@x")])
    assert (written, skipped) == (1, 1)
    notes = team.read_notes(ann)
    assert set(notes) == {mine}
    assert notes[mine] == {"aimpg_note": 1, "usd": 1.0, "wh": [10.0, 100.0], "requests": 3, "tier": "exact"}


def test_two_developers_push_notes_without_clobbering_each_other(tmp_path):
    origin = setup(tmp_path)
    ann, bob = clone(origin, tmp_path / "ann", "ann@x"), clone(origin, tmp_path / "bob", "bob@x")
    a = commit(ann, "a", "ann@x", time.time() - 3 * DAY)
    git(ann, "push", "-q", "origin", "HEAD:main")
    git(bob, "pull", "-q", "--rebase", "origin", "main")
    b = commit(bob, "b", "bob@x", time.time() - 2 * DAY)
    git(bob, "push", "-q", "origin", "HEAD:main")
    team.write_notes(str(ann), [energy(ann, a, "ann@x", usd=2.0)])
    team.write_notes(str(bob), [energy(bob, b, "bob@x", usd=3.0)])
    team.push(str(ann))
    team.push(str(bob))  # must merge ann's notes, not overwrite them
    reader = clone(origin, tmp_path / "ci", "ci@x")
    git(reader, "fetch", "-q", "origin", "+refs/notes/aimpg:refs/notes/aimpg")
    assert {sha: n["usd"] for sha, n in team.read_notes(reader).items()} == {a: 2.0, b: 3.0}


def test_rewriting_keeps_the_fuller_note(tmp_path):
    origin = setup(tmp_path)
    ann = clone(origin, tmp_path / "ann", "ann@x")
    a = commit(ann, "a", "ann@x", time.time() - DAY)
    team.write_notes(str(ann), [energy(ann, a, "ann@x", n=5)])
    assert team.write_notes(str(ann), [energy(ann, a, "ann@x", n=2)]) == (0, 0)  # older logs, fewer requests: kept
    assert team.read_notes(ann)[a]["requests"] == 5


def test_pr_summary_and_markdown(tmp_path):
    origin = setup(tmp_path)
    ann = clone(origin, tmp_path / "ann", "ann@x")
    git(ann, "checkout", "-q", "-b", "feature")
    a = commit(ann, "a", "ann@x", time.time() - DAY)
    commit(ann, "b", "ann@x", time.time())
    team.write_notes(str(ann), [energy(ann, a, "ann@x", usd=4.1, wh=(200, 1900))])
    s = team.pr_summary(str(ann), git(ann, "rev-list", "origin/main..HEAD").split())
    assert s["noted"] == 1 and s["commits"] == 2 and s["usd"] == 4.1
    md = team.pr_markdown(s)
    assert "$4.10" in md and "0.20–1.90 kWh" in md and "1 of 2 commits" in md


def test_rollup_needs_enough_people_and_never_ranks_them(tmp_path):
    origin = setup(tmp_path)
    repo = clone(origin, tmp_path / "team", "lead@x")
    energies = []
    for i, who in enumerate(["a@x", "b@x", "c@x", "d@x"]):
        sha = commit(repo, f"f{i}", who, time.time() - (40 - i) * DAY)
        energies.append(energy(repo, sha, who, usd=1.0 + i))
    for e in energies:
        team.write_notes(str(repo), [e], author=e.task.author)
    small = team.rollup(str(repo), days=90)
    assert small == {"repo": "team", "days": 90, "contributors": 4, "min_group": 5, "enough": False}
    assert "appear at 5" in team.rollup_markdown(small)

    sha = commit(repo, "f4", "e@x", time.time() - 35 * DAY)
    team.write_notes(str(repo), [energy(repo, sha, "e@x", usd=5.0)], author="e@x")
    git(repo, "push", "-q", "origin", "HEAD:main")
    r = team.rollup(str(repo), days=90)
    assert r["enough"] and r["usd"] == 15.0 and r["noted_commits"] == 5
    assert r["judged"]["working"] == 5 and r["cost_per_working_change"] == 3.0 and r["waste_ratio"] == 0.0
    md = team.rollup_markdown(r)
    assert "$3.00" in md and "no per-person numbers" in md
    assert not any(p in md for p in ("a@x", "b@x", "e@x"))
    assert team.rollup(str(repo), days=90, min_group=10)["enough"] is False


def test_bad_notes_are_ignored(tmp_path):
    origin = setup(tmp_path)
    ann = clone(origin, tmp_path / "ann", "ann@x")
    a = commit(ann, "a", "ann@x", time.time())
    git(ann, "notes", "--ref=aimpg", "add", "-m", json.dumps({"aimpg_note": 1, "usd": -5, "wh": [1, 2], "requests": 1}), a)
    assert team.read_notes(ann) == {}


def test_cli_team_commands(tmp_path, capsys):
    origin = setup(tmp_path)
    ann = clone(origin, tmp_path / "ann", "ann@x")
    git(ann, "checkout", "-q", "-b", "feature")
    a = commit(ann, "a", "ann@x", time.time())
    team.write_notes(str(ann), [energy(ann, a, "ann@x")])
    assert main(["team", "pr", "--repo", str(ann), "--base", "origin/main"]) == 0
    assert "AI cost of this pull request" in capsys.readouterr().out
    assert main(["team", "rollup", "--repo", str(ann), "--min-group", "1"]) == 0
    assert "Cost per working change" in capsys.readouterr().out


def test_note_counts_a_split_session_once_not_once_per_commit(tmp_path):
    e = energy(tmp_path, "abc", "ann@x", n=8)
    e.task.weights = [0.25] * 8  # a fuzzy session split four ways
    assert team.note_for(e)["requests"] == 2


def test_weekly_rows_never_show_fewer_than_min_group_people(tmp_path):
    origin = setup(tmp_path)
    repo = clone(origin, tmp_path / "team", "lead@x")
    for i, who in enumerate(["a@x", "b@x", "c@x", "d@x", "e@x"]):
        sha = commit(repo, f"f{i}", who, time.time() - 20 * DAY)
        team.write_notes(str(repo), [energy(repo, sha, who, usd=1.0)], author=who)
    solo = commit(repo, "solo", "a@x", time.time() - 3 * DAY)  # alone in her week
    team.write_notes(str(repo), [energy(repo, solo, "a@x", usd=47.13)], author="a@x")
    r = team.rollup(str(repo), days=90)
    assert list(r["weeks"].values()) == [{"usd": 52.13, "commits": 6}]  # her week joins the one before
    assert "$47.13" not in team.rollup_markdown(r)


def test_notes_with_infinity_or_bools_are_ignored(tmp_path):
    origin = setup(tmp_path)
    ann = clone(origin, tmp_path / "ann", "ann@x")
    a = commit(ann, "a", "ann@x", time.time())
    git(ann, "notes", "--ref=aimpg", "add", "-m", '{"aimpg_note": 1, "usd": Infinity, "wh": [true, 1e400], "requests": true}', a)
    assert team.read_notes(ann) == {}


def test_pr_comment_is_found_by_its_marker_not_by_who_wrote_last():
    md = team.pr_markdown({"commits": 1, "noted": 1, "usd": 1.0, "wh": [1, 2], "requests": 1})
    assert md.startswith(team.PR_MARKER) and "1 of 1 commit has notes" in md and "1 model request\n" in md
    action = (Path(__file__).parent.parent / "action.yml").read_text()
    assert team.PR_MARKER in action and "--edit-last" not in action


def test_cli_team_errors_go_to_stderr_and_bad_numbers_are_refused(tmp_path, capsys):
    origin = setup(tmp_path)
    ann = clone(origin, tmp_path / "ann", "ann@x")
    assert main(["team", "pr", "--repo", str(ann), "--base", "origin/master"]) == 1
    out = capsys.readouterr()
    assert out.out == "" and "Can't list this branch's commits" in out.err
    for bad in (["--days", "-5"], ["--min-group", "0"]):
        with pytest.raises(SystemExit):
            main(["team", "rollup", "--repo", str(ann), *bad])


def test_action_step_prints_the_error_to_the_log(tmp_path):
    """Run the Action's aimpg step as GitHub would, with uvx standing in for the published package."""
    lines = (Path(__file__).parent.parent / "action.yml").read_text().splitlines()
    start = lines.index("      id: run")
    start = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |") + 1
    end = next(i for i in range(start, len(lines)) if lines[i].startswith("    - "))
    script = "\n".join(line[8:] for line in lines[start:end])
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uvx = bin_dir / "uvx"  # drops `--quiet --from PATH aimpg`
    uvx.write_text(f'#!/bin/sh\nshift 4\nexec {sys.executable} -c "import sys; from aimpg.cli import main; sys.exit(main(sys.argv[1:]))" "$@"\n')
    uvx.chmod(0o755)
    repo = clone(setup(tmp_path), tmp_path / "ci", "ci@x")
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "RUNNER_TEMP": str(tmp_path),
           "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"), "GITHUB_OUTPUT": str(tmp_path / "output"),
           "MODE": "pr", "BASE_REF": "master", "DAYS": "90", "MIN_GROUP": "5", "ACTION_PATH": "x"}
    run = subprocess.run(["bash", "-c", script], cwd=repo, env=env, capture_output=True, text=True)
    assert run.returncode == 1
    assert "Can't list this branch's commits" in run.stderr and "::error::aimpg team pr failed" in run.stdout
    env["BASE_REF"] = "main"
    run = subprocess.run(["bash", "-c", script], cwd=repo, env=env, capture_output=True, text=True)
    assert run.returncode == 0 and team.PR_MARKER in (tmp_path / "summary").read_text()
