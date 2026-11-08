from aimpg.cli import main


def test_demo_receipt_runs_on_made_up_data_only(tmp_path, capsys):
    assert main(["report", "--demo"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("DEMO: made-up sample data")
    assert "demo-shop" in out and "WORKING CHANGES" in out and "judged commits are working changes" in out
    assert "Use a mid-size model" in out  # the demo is mostly on the largest model, so the main tip shows


def test_demo_has_no_share_card(capsys):
    assert main(["report", "--demo", "--share"]) == 1
    assert "--share isn't available with --demo" in capsys.readouterr().out


def test_no_logs_points_to_the_demo(tmp_path, capsys):
    assert main(["report", "--logs", str(tmp_path / "none"), "--codex-logs", str(tmp_path / "none2")]) == 0
    assert "aimpg report --demo" in capsys.readouterr().out
