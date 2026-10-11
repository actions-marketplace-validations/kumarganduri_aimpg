import json

import pytest

from aimpg import sci
from aimpg.durable import Judged
from aimpg.energy import total_wh
from aimpg.model import Request, Usage


def req(i, out=500):
    return Request(f"r{i}", "s", "claude-sonnet-5-5", 1000.0 + i, Usage(fresh_in=10, cache_write=2000, cache_read=20000, output=out), "/repo")


def test_formula_and_units():
    reqs = [req(i) for i in range(10)]
    s = sci.compute(reqs, 4, None, grid=400.0, period=(0, 86400))
    e = total_wh(reqs)
    lo = e.low / 1000 * (400 + 40)
    hi = e.high / 1000 * (400 + 70)
    assert s["total_g"] == [round(lo, 1), round(hi, 1)]
    assert s["sci"]["per_ai_assisted_commit_g"] == pytest.approx([lo / 4, hi / 4], rel=1e-4)
    tokens = 10 * (10 + 2000 + 20000 + 500)
    assert s["inputs"]["tokens"] == tokens
    assert s["sci"]["per_million_tokens_g"] == pytest.approx([lo / (tokens / 1e6), hi / (tokens / 1e6)], rel=1e-4)
    assert s["boundary"]["persona"] == "consumer" and "market-based" in s["inputs"]["I_method"]


def test_per_working_change_counts_all_judged_carbon_over_the_ones_that_lasted():
    judged = Judged(durable=[{"wh_low": 10, "wh_high": 100, "ts": 0}],
                    not_kept=[{"wh_low": 10, "wh_high": 100, "ts": 0}])
    s = sci.compute([req(0)], 1, judged, grid=500.0, period=(0, 1))
    w = s["sci"]["per_working_change_g"]
    assert w["working_changes"] == 1 and w["judged_commits"] == 2
    assert w["value_g"] == pytest.approx([20 / 1000 * 540, 200 / 1000 * 570])


def test_not_yet_judgeable_says_when():
    judged = Judged(too_new=[{"ts": 0.0}])
    s = sci.compute([req(0)], 1, judged, grid=458.0, period=(0, 1))
    assert s["sci"]["per_working_change_g"] is None and s["working_change_available_from"] == "1970-01-31"
    assert "available from 1970-01-31" in sci.render(s)


def test_empty_window_has_no_division_by_zero():
    s = sci.compute([], 0, None, grid=458.0, period=(0, 1))
    assert s["sci"]["per_million_tokens_g"] is None and s["sci"]["per_ai_assisted_commit_g"] is None


def test_cli_writes_the_disclosure(write_log, tmp_path, capsys):
    from aimpg.cli import main
    from conftest import assistant
    import time
    from datetime import datetime, timezone

    ts = datetime.fromtimestamp(time.time() - 3600, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    log = write_log([assistant("r1", ts, out=300)])
    out = tmp_path / "sci.json"
    assert main(["sci", "--logs", str(log.parent.parent), "--grid", "300", "--json", str(out)]) == 0
    text = capsys.readouterr().out
    assert "SCI FOR AI (Consumer)" in text and "300 g CO₂e/kWh" in text
    data = json.loads(out.read_text())
    assert data["inputs"]["I_g_per_kwh"] == 300 and data["specification"].endswith("SPEC.md")
