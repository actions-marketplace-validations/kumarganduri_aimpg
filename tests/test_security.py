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
