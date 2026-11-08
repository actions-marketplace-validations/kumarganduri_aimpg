"""Regression tests for the pre-launch security review (2026-10-11)."""

import os
import subprocess

import pytest

from aimpg.replay import sandbox
from aimpg.replay import setups as S
from aimpg.replay.sandbox import Profile, SandboxUnavailable
from aimpg.replay.verify import VerifyError, setup_from_spec
from aimpg.replay.workspace import Commit, WorkspaceError, overlay_commit_tests, safe_write


def test_record_names_cannot_break_out_of_the_sandbox_profile():
    evil = 'x"))(allow default)(allow file-read* (literal "y'
    with pytest.raises(S.SetupUnavailable):
        setup_from_spec({"name": evil, "agent": "claude"})
    with pytest.raises(SandboxUnavailable):
        Profile(writable=[f"/private/tmp/{evil}"]).render()


@pytest.mark.parametrize("spec", [
    {"name": "codex", "agent": "codex", "model": "m --dangerously-anything"},
    {"name": "c", "agent": "cmd", "command": "t {task}", "hosts": ["api.openai.com"], "key_env": "AWS_SECRET_ACCESS_KEY"},
    {"name": "c", "agent": "cmd", "command": "t {task}", "hosts": ["localhost:22"], "key_env": ""},
])
def test_record_fields_are_strictly_shaped(spec):
    with pytest.raises(S.SetupUnavailable):
        setup_from_spec(spec)


def test_rerun_refuses_commit_ids_that_are_git_options(tmp_path):
    from aimpg.replay.select import commit_at

    with pytest.raises(WorkspaceError):
        commit_at(str(tmp_path), "--output=../../.ssh/authorized_keys")


def test_planted_symlinks_are_never_followed(tmp_path):
    work, outside = tmp_path / "work", tmp_path / "outside"
    work.mkdir(), outside.mkdir()
    victim = outside / "authorized_keys"
    victim.write_text("original")
    (work / "tests").mkdir()
    (work / "tests" / "test_x.py").symlink_to(victim)          # file symlink
    (work / "pkg").symlink_to(outside, target_is_directory=True)  # folder symlink
    safe_write(work, "tests/test_x.py", b"written")
    safe_write(work, "pkg/authorized_keys", b"written")
    assert victim.read_text() == "original"
    assert (work / "tests" / "test_x.py").read_text() == "written" and not (work / "pkg").is_symlink()
    with pytest.raises(WorkspaceError):
        safe_write(work, "../escape.txt", b"x")


def test_overlay_of_commit_tests_ignores_a_symlinked_test(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "tests").mkdir()
    (repo / "tests" / "test_a.py").write_text("def test_a(): pass\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "t"], check=True)
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    work, victim = tmp_path / "work", tmp_path / "victim"
    (work / "tests").mkdir(parents=True)
    victim.write_text("keep")
    (work / "tests" / "test_a.py").symlink_to(victim)
    overlay_commit_tests(Commit(str(repo), sha, sha, "s", "", ["tests/test_a.py"], []), work)
    assert victim.read_text() == "keep" and "def test_a" in (work / "tests" / "test_a.py").read_text()


def test_live_install_quotes_the_executable(tmp_path):
    from aimpg.live import planned_settings

    new = planned_settings({}, "/Users/a b/bin/aimpg")
    assert new["statusLine"]["command"] == "'/Users/a b/bin/aimpg' statusline"


def test_replay_folder_is_private_and_owned(tmp_path):
    from aimpg.replay.cli import secure_root

    root = secure_root(tmp_path / "r")
    assert (root.stat().st_mode & 0o777) == 0o700 and root.stat().st_uid == os.getuid()


def test_scoreboard_rejects_option_shaped_commits(tmp_path):
    import json

    from aimpg import scoreboard as sb
    from test_scoreboard import record

    up = sb.upload_view(record(tmp_path, public=True))
    up["runs"][0]["commit"] = "--output=x"
    data = sb.encode(up)
    assert any("40-character" in p for p in sb.validate_upload(tmp_path / "me" / sb.file_name(data), data))


# ---- pre-launch QA (2026-10-25)

def _fake_home(tmp_path, monkeypatch, *tools: str):
    home = tmp_path / "home"
    home.mkdir()
    for t in tools:
        (home / t).parent.mkdir(parents=True, exist_ok=True)
        (home / t).write_text("#!/bin/sh\n")
        (home / t).chmod(0o755)
    monkeypatch.setenv("HOME", str(home))
    return home.resolve()


def test_a_record_command_with_dotdot_cannot_make_the_disk_readable(tmp_path, monkeypatch):
    home = _fake_home(tmp_path, monkeypatch)
    (home / "proj").mkdir()
    monkeypatch.chdir(home / "proj")  # the victim runs --rerun from inside their home folder
    climb = "../" * 12 + "bin/cat"
    spec = {"name": "fast-agent", "agent": "cmd", "command": f"{climb} {{task}}", "hosts": ["api.anthropic.com"]}
    with pytest.raises(S.SetupUnavailable):
        setup_from_spec(spec)
    with pytest.raises(S.SetupUnavailable):
        S.command(f"{climb} {{task}}", ["api.anthropic.com"])  # your own command can't either
    assert sandbox.tool_dirs((climb,)) == []  # normalized to /bin/cat: nothing under $HOME to grant
    for broad in ("/", home, home.parent):
        with pytest.raises(SandboxUnavailable):
            Profile(writable=[tmp_path / "w"], readable=[broad]).render()
        with pytest.raises(SandboxUnavailable):
            sandbox.bwrap_args(Profile(writable=[tmp_path / "w"], readable=[broad]), tmp_path)


def test_a_bin_folder_directly_in_home_is_granted_alone(tmp_path, monkeypatch):
    # ~/.cargo/credentials.toml holds the crates.io token; rtk is usually installed with cargo
    home = _fake_home(tmp_path, monkeypatch, ".cargo/bin/rtk", ".nvm/versions/node/v22/bin/node")
    monkeypatch.setenv("PATH", f"{home}/.cargo/bin:{home}/.nvm/versions/node/v22/bin:/usr/bin:/bin")
    assert sandbox.tool_dirs(("rtk", "node")) == [home / ".cargo/bin", home / ".nvm/versions/node/v22"]


def test_linuxbrew_installs_stay_readable(tmp_path, monkeypatch):
    _fake_home(tmp_path, monkeypatch)
    brew = tmp_path / "linuxbrew" / ".linuxbrew"
    (brew / "Cellar/node/22/bin").mkdir(parents=True)
    (brew / "Cellar/node/22/bin/node").write_text("#!/bin/sh\n")
    (brew / "Cellar/node/22/bin/node").chmod(0o755)
    (brew / "bin").mkdir()
    (brew / "bin/node").symlink_to("../Cellar/node/22/bin/node")
    monkeypatch.setattr(sandbox, "LINUXBREW", brew)
    monkeypatch.setenv("PATH", f"{brew}/bin:/usr/bin:/bin")
    assert brew.resolve() in sandbox.tool_dirs(("node",))  # its own ld.so and libraries live in the prefix


def test_linux_sandbox_hides_mounted_drives(tmp_path, monkeypatch):
    drive = tmp_path / "mnt"
    (drive / "c" / "Users").mkdir(parents=True)  # WSL: the Windows home
    monkeypatch.setattr(sandbox, "LINUX_DRIVES", (str(drive),))
    args = sandbox.bwrap_args(Profile(writable=[tmp_path / "w"]), tmp_path)
    assert args[args.index(str(drive)) - 1] == "--tmpfs"
    with pytest.raises(SandboxUnavailable):
        sandbox.bwrap_args(Profile(writable=[tmp_path / "w"], readable=[drive]), tmp_path)
