import io
import json
import time

import pytest

from aimpg import live
from aimpg.live import SessionState, commit_note, status_line, update

from conftest import assistant, bash_call, tool_result


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "LIVE_DIR", tmp_path / "live")
    monkeypatch.setattr(live, "PREVIOUS", tmp_path / "live" / "previous_statusline.json")
    monkeypatch.setattr(live, "_refresh_in_background", lambda: None)


def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))


def append(path, rows):
    with open(path, "a") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_reads_only_new_lines_and_dedupes_requests(tmp_path):
    t = tmp_path / "s.jsonl"
    now = time.time() - 600
    append(t, [assistant("r1", iso(now), fresh=2, write=10_000, read=0, out=100), assistant("r1", iso(now), fresh=2, write=10_000, read=0, out=100)])
    s = update(SessionState(), t)
    assert len(s.task) == 1 and s.base_ctx == 10_002
    first_offset = s.offset
    append(t, [assistant("r2", iso(now + 10), fresh=2, write=500, read=10_000, out=200)])
    s = update(s, t)
    assert len(s.task) == 2 and s.offset > first_offset and s.last_ctx == 10_502


def test_partial_last_line_waits(tmp_path):
    t = tmp_path / "s.jsonl"
    t.write_text(json.dumps(assistant("r1", iso(time.time()))) + "\n" + '{"type": "assistant", "mess')
    s = update(SessionState(), t)
    assert len(s.task) == 1 and s.offset == len(t.read_text().split("\n")[0]) + 1


def test_commit_in_transcript_closes_the_task_and_tracks_carried_context(tmp_path):
    t = tmp_path / "s.jsonl"
    now = time.time() - 600
    append(t, [
        assistant("r1", iso(now), fresh=2, write=10_000, read=0, out=100),
        assistant("r2", iso(now + 5), fresh=2, write=1_000, read=60_000, out=100),
        bash_call("tu1", "git commit -m feat", iso(now + 10)),
        tool_result("tu1", iso(now + 12)),
        assistant("r3", iso(now + 20), fresh=2, write=500, read=72_000, out=100),
    ])
    s = update(SessionState(), t)
    assert len(s.commits) == 1 and s.commits[0]["requests"] == 3  # r1, r2 and the commit call itself
    assert list(s.task) == ["r3"]
    assert 0.8 < s.carried_share() < 0.9  # most of r3's context predates the commit


def test_status_line_colors_and_hints():
    s = SessionState(base_ctx=10_000, last_ctx=100_000, first_ctx_after_commit=90_000, commits=[{"ts": 1, "cost": 1, "requests": 3}])
    s.task = {"r": [0, "claude-sonnet-5-5", 2, 1000, 90_000, 1_000_000, 0, False]}  # ~$10 task
    line = status_line({"rate_limits": {"five_hour": {"used_percentage": 63}}}, s, usual=1.0)
    assert line.startswith("⚡ ") and "\033[31m" in line  # > 3x usual: red
    assert "usual $1.00" in line and "80% from before your last commit" in line and "5h 63%" in line
    assert "/clear" not in line  # Report No. 1: a fresh session cost more, so no /clear advice
    assert "\033[" not in status_line({}, SessionState(), usual=None)


def test_hook_ignores_other_commands(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})))
    assert live.run_post_commit_hook() == 0
    assert capsys.readouterr().out == ""


def test_hook_announces_a_commit_once(tmp_path, monkeypatch, capsys):
    t = tmp_path / "s.jsonl"
    now = time.time() - 30
    append(t, [assistant("r1", iso(now), fresh=2, write=10_000, read=0, out=100), assistant("r2", iso(now + 5), fresh=2, write=500, read=50_000, out=300)])
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}, "session_id": "S", "transcript_path": str(t)})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    live.run_post_commit_hook()
    msg = json.loads(capsys.readouterr().out)["systemMessage"]
    assert msg.startswith("aimpg: that commit cost $") and "over 2 AI requests" in msg and "/clear" not in msg
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    live.run_post_commit_hook()
    assert capsys.readouterr().out == ""  # nothing new: no second note


def test_hook_still_announces_when_the_status_line_saw_the_commit_first(tmp_path, monkeypatch, capsys):
    t = tmp_path / "s.jsonl"
    now = time.time() - 30
    append(t, [assistant("r1", iso(now), out=100), bash_call("tu1", "git commit -m x", iso(now + 5)), tool_result("tu1", iso(now + 6))])
    update(SessionState(), t).save("S")  # status line ran first and closed the task
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}, "session_id": "S", "transcript_path": str(t)})))
    live.run_post_commit_hook()
    assert "that commit cost" in json.loads(capsys.readouterr().out)["systemMessage"]


def test_commit_note_without_old_context_has_no_clear_hint():
    assert "/clear" not in commit_note({"cost": 0.5, "requests": 4, "stale_share": 0.1})


def test_install_keeps_existing_statusline_and_hooks_and_uninstall_restores(tmp_path):
    settings = tmp_path / "settings.json"
    original = {"statusLine": {"type": "command", "command": "~/my-line.sh"}, "theme": "dark",
                "hooks": {"PostToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "fmt.sh"}]}]}}
    settings.write_text(json.dumps(original))
    assert live.install(settings, "/bin/aimpg", confirm=lambda _: "n") == "Nothing changed."
    assert json.loads(settings.read_text()) == original
    live.install(settings, "/bin/aimpg", confirm=lambda _: "y")
    new = json.loads(settings.read_text())
    assert new["statusLine"]["command"] == "/bin/aimpg statusline" and new["theme"] == "dark"
    assert len(new["hooks"]["PostToolUse"]) == 2
    assert live.previous_statusline() == "~/my-line.sh"
    assert list(tmp_path.glob("settings.json.aimpg-backup-*"))
    live.uninstall(settings)
    assert json.loads(settings.read_text()) == original


def test_status_line_wraps_the_previous_one(tmp_path, monkeypatch, capsys):
    t = tmp_path / "s.jsonl"
    append(t, [assistant("r1", iso(time.time()), out=100)])
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "S", "transcript_path": str(t)})))
    live.run_statusline("echo mine")
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "mine" and out[1].startswith("⚡ task $")


def _exe(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def test_launcher_never_points_claude_code_at_the_uv_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(live.tempfile, "gettempdir", lambda: "/nonexistent-tmp")  # tmp_path lives in the temp dir
    cached = _exe(tmp_path / "uv" / "archive-v0" / "Fv1" / "bin" / "aimpg")  # what `uvx aimpg` puts first on PATH
    uvx = _exe(tmp_path / "local" / "bin" / "uvx")
    monkeypatch.setenv("PATH", f"{cached.parent}:{uvx.parent}")
    exe, note = live.launcher()
    assert exe == [str(uvx), f"aimpg@{live.metadata.version('aimpg')}"] and "uv tool install aimpg" in note
    tool = _exe(tmp_path / "local" / "bin" / "aimpg")  # after `uv tool install aimpg`
    assert live.launcher() == ([str(tool)], "")
    monkeypatch.setenv("PATH", str(cached.parent))
    exe, note = live.launcher()
    assert exe is None and "uv tool install aimpg" in note


def test_install_repairs_an_earlier_install_from_a_path_that_is_gone(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"statusLine": {"type": "command", "command": "~/my-line.sh"}}))
    live.install(settings, "/cache/archive-v0/GONE/bin/aimpg", confirm=lambda _: "y")
    assert live.install(settings, ["/usr/bin/uvx", "aimpg@0.7.1"], confirm=lambda _: "y").startswith("Installed")
    new = json.loads(settings.read_text())
    assert new["statusLine"]["command"] == "/usr/bin/uvx aimpg@0.7.1 statusline"
    assert [h["command"] for e in new["hooks"]["PostToolUse"] for h in e["hooks"]] == ["/usr/bin/uvx aimpg@0.7.1 hook post-commit"]
    assert live.previous_statusline() == "~/my-line.sh"  # still the user's own, not the old aimpg command
    assert live.install(settings, ["/usr/bin/uvx", "aimpg@0.7.1"], confirm=lambda _: "y") == "aimpg live is already installed."


def test_install_keeps_mode_and_symlink_and_uninstall_restores_the_whole_statusline(tmp_path):
    real = tmp_path / "dotfiles" / "settings.json"
    real.parent.mkdir()
    original = {"statusLine": {"type": "command", "command": "echo MYLINE", "padding": 2}, "env": {"TOKEN": "x"}}
    real.write_text(json.dumps(original))
    real.chmod(0o600)
    settings = tmp_path / "claude" / "settings.json"
    settings.parent.mkdir()
    settings.symlink_to(real)
    live.install(settings, "/bin/aimpg", confirm=lambda _: "y")
    assert settings.is_symlink() and json.loads(real.read_text())["statusLine"]["padding"] == 2
    assert (real.stat().st_mode & 0o777) == 0o600
    assert all((b.stat().st_mode & 0o777) == 0o600 for b in settings.parent.glob("settings.json.aimpg-backup-*"))
    assert live.uninstall(settings).startswith("Removed")
    assert settings.is_symlink() and json.loads(real.read_text()) == original
    assert live.uninstall(settings) == "aimpg live is not installed. Nothing changed."


def test_install_refuses_read_only_or_unexpected_settings(tmp_path):
    settings = tmp_path / "settings.json"
    for text in ['{\n  "model": "opus",\n}\n', '{"statusLine": "echo hi"}', '{"hooks": {"PostToolUse": {"a": 1}}}', "[]"]:
        settings.write_text(text)
        for call in (lambda: live.install(settings, "/bin/aimpg", confirm=lambda _: "y"), lambda: live.uninstall(settings)):
            with pytest.raises(live.SettingsError, match="Nothing changed"):
                call()
        assert settings.read_text() == text
    settings.write_text('{"model": "opus"}')
    settings.chmod(0o444)
    with pytest.raises(live.SettingsError, match="read-only"):
        live.install(settings, "/bin/aimpg", confirm=lambda _: "y")
    assert settings.read_text() == '{"model": "opus"}' and not list(tmp_path.glob("settings.json.aimpg-backup-*"))


def test_install_without_a_terminal_changes_nothing(tmp_path):
    def no_tty(_):
        raise EOFError
    assert live.install(tmp_path / "settings.json", "/bin/aimpg", confirm=no_tty) == "Nothing changed."
    assert not (tmp_path / "settings.json").exists()


def test_status_line_survives_odd_input(tmp_path, monkeypatch, capsys):
    t = tmp_path / "s.jsonl"
    append(t, [assistant("r1", iso(time.time()), out=100), ["usage"]])
    for payload in ("[1, 2]", json.dumps({"session_id": "S", "transcript_path": str(t)})):
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        assert live.run_statusline() == 0
    assert capsys.readouterr().out.splitlines()[-1].startswith("⚡ task $")
    assert SessionState.load("S").offset == t.stat().st_size  # moved past the odd row


def test_uvx_run_says_which_installed_aimpg_claude_code_will_call(tmp_path, monkeypatch):
    exe = tmp_path / "bin" / "aimpg"
    exe.parent.mkdir()
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(exe.parent))
    monkeypatch.setattr(live, "_ephemeral", lambda path: path != str(exe))  # this copy is uvx's, the one on PATH isn't
    cmd, note = live.launcher()
    assert cmd == [str(exe)] and str(exe) in note and "uv tool upgrade aimpg" in note
