"""The suite never touches the developer's real ~/.claude, ~/.codex or ~/.aimpg (see conftest)."""

from pathlib import Path

import pytest

from conftest import REAL_HOME, guarded, touched


def test_home_and_every_state_path_point_away_from_the_real_home():
    from aimpg import cli, codex_logs, defaults, ledger, live, logs, scoreboard
    from aimpg.replay import cli as replay_cli
    from aimpg.replay import study_cli, verify

    assert Path.home() != REAL_HOME
    paths = [logs.DEFAULT_ROOT, cli.DEFAULT_ROOT, codex_logs.DEFAULT_ROOT, ledger.LEDGER, live.LIVE_DIR, live.PREVIOUS,
             live.SETTINGS, replay_cli.STATE, verify.STATE, scoreboard.SECRET, defaults.REPLAY_STATE,
             defaults.VERIFY_STATE, study_cli.STATE]
    assert not [p for p in paths if guarded(p)]


def test_guard_sees_an_access_to_the_real_home():
    before = len(touched)
    with pytest.raises(OSError):
        open(REAL_HOME / ".aimpg" / "aimpg-test-no-such-dir" / "x")  # read-only, and the path does not exist
    assert len(touched) == before + 1 and "aimpg-test-no-such-dir" in touched[-1]
    del touched[before:]  # expected here; any other test doing this fails


def test_ledger_default_path_is_looked_up_at_call_time():
    """Regression: load()/record() bound ~/.aimpg/ledger.json at import, so suite runs wrote the real ledger."""
    from aimpg import ledger
    from aimpg.energy import WhRange
    from aimpg.model import Request, Task, Usage
    from aimpg.receipt import TaskEnergy

    t = Task("/r", "abc", 1.0, "s", "exact", "kept", author="a")
    t.add(Request("1", "s", "m", 0, Usage(output=1), "/r"))
    assert ledger.record([TaskEnergy(t, WhRange(1, 2), WhRange(0, 0), usd=0.1)]) == 1
    assert ledger.LEDGER.exists() and ledger.key("/r", "abc") in ledger.load()
