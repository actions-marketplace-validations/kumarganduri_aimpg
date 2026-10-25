import time

import pytest

from aimpg import durable, ledger
from aimpg.receipt import working_changes

from gitrepo import Repo, days_ago

LINES = "def compute_total(items):\n    return sum(item.price for item in items)\n\ndef describe_order(order):\n    return f'order {order.id} with {len(order.items)} items'\n"


def rec(repo, sha, ts, usd=1.0):
    return {"repo": str(repo.path), "sha": sha, "ts": ts, "subject": "s", "author": "t@example.com", "requests": 3, "usd": usd, "wh_low": 1, "wh_high": 9, "first_seen": ts}


@pytest.fixture
def repo(tmp_path):
    r = Repo(tmp_path / "repo")
    r.commit({"base.py": "print('base line')\n"}, "base", days_ago(80))
    return r


def test_every_outcome(repo):
    t = days_ago(60)
    good = repo.commit({"good.py": LINES}, "feat: good", t)
    reworked = repo.commit({"redo.py": LINES}, "feat: soon redone", t + 100)
    repo.commit({"redo.py": "def compute_total(items):\n    return 0\n"}, "fix: rewrite", t + 5 * 86400)
    reverted = repo.commit({"oops.py": LINES}, "feat: oops", t + 200)
    repo.git("revert", "--no-edit", reverted, when=t + 300)
    repo.git("checkout", "-q", "-b", "side")
    side = repo.commit({"side.py": LINES}, "feat: never merged", t + 400)
    repo.git("checkout", "-q", "main")
    repo.commit({"later.py": "print('main keeps moving')\n"}, "later", days_ago(1))
    young = repo.commit({"young.py": LINES}, "feat: young", days_ago(3))

    data = {ledger.key(r["repo"], r["sha"]): r for r in (
        rec(repo, good, t), rec(repo, reworked, t + 100), rec(repo, reverted, t + 200),
        rec(repo, side, t + 400), rec(repo, young, days_ago(3)),
    )}
    j = durable.judge(data)
    assert [r["sha"] for r in j.durable] == [good]
    assert [r["sha"] for r in j.reworked] == [reworked]
    assert [r["sha"] for r in j.reverted] == [reverted]
    assert [r["sha"] for r in j.not_kept] == [side]
    assert [r["sha"] for r in j.too_new] == [young]
    assert j.cost_per_durable() == pytest.approx(4.0)  # $4 on 4 judged commits, 1 durable
    assert j.waste_ratio() == pytest.approx(0.75)
    text = "\n".join(working_changes(j))
    assert "1 of 4 judged commits are working changes (25%)" in text and "Cost per working change: $4.00" in text


def test_too_new_says_when(repo):
    sha = repo.commit({"a.py": LINES}, "feat", days_ago(5))
    j = durable.judge({"k": rec(repo, sha, days_ago(5))})
    assert j.judged == [] and j.cost_per_durable() is None
    assert "Available on" in "\n".join(working_changes(j))


def test_ledger_keeps_the_fuller_record(tmp_path):
    from aimpg.energy import WhRange
    from aimpg.model import Request, Task, Usage
    from aimpg.receipt import TaskEnergy

    path = tmp_path / "ledger.json"

    def energy(n):
        t = Task("/r", "abc", 1.0, "s", "exact", "kept", author="a")
        for i in range(n):
            t.add(Request(str(i), "s", "m", 0, Usage(output=1), "/r"))
        return TaskEnergy(t, WhRange(n, 2 * n), WhRange(0, 0), usd=n * 0.1)

    assert ledger.record([energy(5)], path) == 1
    ledger.record([energy(2)], path)  # older logs were deleted: fewer requests now
    assert ledger.load(path)[ledger.key("/r", "abc")]["requests"] == 5
    ledger.record([energy(8)], path)
    assert ledger.load(path)[ledger.key("/r", "abc")]["requests"] == 8


def test_record_separator_in_a_later_file_keeps_a_shipped_commit_durable(repo):
    sha = repo.commit({"good.py": LINES}, "feat: good", days_ago(40))
    repo.commit({"b.txt": "data\x1eother\n"}, "fixture", days_ago(1))
    j = durable.judge({"k": rec(repo, sha, days_ago(40))})
    assert [r["sha"] for r in j.durable] == [sha] and j.not_kept == [] and j.errors == {}


def test_repo_git_cannot_read_is_left_unjudged(repo, tmp_path):
    good = repo.commit({"good.py": LINES}, "feat: good", days_ago(40))
    gone = Repo(tmp_path / "gone")
    lost = gone.commit({"a.py": LINES}, "feat: lost", days_ago(40))
    gone.git("branch", "-m", "main", "trunk")  # no main/master/origin: git can't tell what shipped
    data = {"a": rec(repo, good, days_ago(40), usd=2.0), "b": rec(gone, lost, days_ago(40), usd=6.0),
            "c": {**rec(repo, "f" * 40, days_ago(40)), "repo": str(tmp_path / "deleted")}}
    j = durable.judge(data)
    assert len(j.unreadable) == 2 and j.not_kept == [] and [r["sha"] for r in j.judged] == [good]
    assert j.cost_per_durable() == pytest.approx(2.0) and j.waste_ratio() == 0  # not counted as waste
    text = "\n".join(working_changes(j))
    assert "2 commits in repos aimpg couldn't read are left out" in text and "gone: no default branch found" in text
    assert "0 never shipped" in text


def test_working_changes_say_they_cover_all_history(repo):
    sha = repo.commit({"good.py": LINES}, "feat: good", days_ago(40))
    j = durable.judge({"k": {**rec(repo, sha, days_ago(40)), "first_seen": days_ago(35)}})
    assert f"all history since {durable.day(days_ago(35))}, not just this window" in working_changes(j)[0]
