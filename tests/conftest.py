"""Builders for fixture log rows that mirror the real Claude Code JSONL shape."""

from __future__ import annotations

import json
import os
import pwd
import sys
from pathlib import Path

import pytest


def assistant(
    request_id: str | None,
    ts: str,
    *,
    session: str = "s1",
    cwd: str = "/repo",
    model: str = "claude-sonnet-5",
    fresh: int = 10,
    write: int = 100,
    read: int = 1000,
    out: int = 50,
    content: list | None = None,
    sidechain: bool = False,
    message_id: str = "msg_1",
    version: str = "2.1.280",
) -> dict:
    row = {
        "type": "assistant",
        "sessionId": session,
        "cwd": cwd,
        "timestamp": ts,
        "isSidechain": sidechain,
        "version": version,
        "message": {
            "id": message_id,
            "model": model,
            "content": content or [{"type": "text", "text": "ok"}],
            "usage": {
                "input_tokens": fresh,
                "cache_creation_input_tokens": write,
                "cache_read_input_tokens": read,
                "output_tokens": out,
            },
        },
    }
    if request_id is not None:
        row["requestId"] = request_id
    return row


def bash_call(tool_id: str, command: str, ts: str, *, session: str = "s1", cwd: str = "/repo") -> dict:
    return assistant(
        f"req_{tool_id}",
        ts,
        session=session,
        cwd=cwd,
        content=[{"type": "tool_use", "id": tool_id, "name": "Bash", "input": {"command": command}}],
    )


def tool_result(tool_id: str, ts: str, *, session: str = "s1", cwd: str = "/repo") -> dict:
    return {
        "type": "user",
        "sessionId": session,
        "cwd": cwd,
        "timestamp": ts,
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": "done"}],
        },
    }


@pytest.fixture
def write_log(tmp_path: Path):
    def _write(rows: list, name: str = "session.jsonl", raw_lines: list[str] | None = None) -> Path:
        path = tmp_path / "projects" / "-folder" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(r) for r in rows] + list(raw_lines or [])
        path.write_text("\n".join(lines) + "\n")
        return path

    return _write


# The developer's real agent and aimpg state. No test may read or write it: suite runs
# once leaked fixture commits into ~/.aimpg/ledger.json and skewed the real receipt.
REAL_HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)
GUARDED = tuple(str(REAL_HOME / d) for d in (".aimpg", ".codex", ".claude"))
# These prove the sandbox hides the real $HOME, so they keep it (the constants are still patched)
KEEPS_REAL_HOME = {"test_replay_sandbox", "test_replay_e2e"}
touched: list[str] = []  # "event path" for each access under GUARDED by this process

_EVENTS = {"open", "os.listdir", "os.scandir", "os.mkdir", "os.rename", "os.replace", "os.remove", "os.rmdir",
           "os.symlink", "os.truncate", "shutil.rmtree"}


def guarded(path) -> bool:
    if not isinstance(path, (str, bytes, os.PathLike)):
        return False  # a file descriptor
    path = os.path.abspath(os.fsdecode(path))
    return any(path == g or path.startswith(g + os.sep) for g in GUARDED)


def _audit(event: str, args: tuple) -> None:
    if event in _EVENTS:
        for a in args[:2]:  # the path, or src and dst
            if guarded(a):
                touched.append(f"{event} {os.fsdecode(a)}")


sys.addaudithook(_audit)  # this process only; subprocesses (git, uv) get a temp $HOME below


@pytest.fixture(autouse=True)
def _never_touch_the_real_home(request, tmp_path_factory, monkeypatch):
    """Tests must not depend on (or read, or write) the developer's real ~/.claude, ~/.codex or ~/.aimpg."""
    if request.module.__name__.rsplit(".", 1)[-1] not in KEEPS_REAL_HOME:
        monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))
    from aimpg import cli, codex_logs, ledger, live, logs
    from aimpg.replay import cli as replay_cli
    from aimpg.replay import verify

    # module-level paths were bound to the real home at import: point each one elsewhere
    monkeypatch.setattr(logs, "DEFAULT_ROOT", tmp_path_factory.mktemp("no-claude") / "projects")
    monkeypatch.setattr(cli, "DEFAULT_ROOT", logs.DEFAULT_ROOT)  # its own `from aimpg.logs import` copy
    monkeypatch.setattr(codex_logs, "DEFAULT_ROOT", tmp_path_factory.mktemp("no-codex") / "sessions")
    monkeypatch.setattr(ledger, "LEDGER", tmp_path_factory.mktemp("ledger") / "ledger.json")
    live_dir = tmp_path_factory.mktemp("live")
    monkeypatch.setattr(live, "LIVE_DIR", live_dir)
    monkeypatch.setattr(live, "PREVIOUS", live_dir / "previous_statusline.json")
    monkeypatch.setattr(live, "SETTINGS", tmp_path_factory.mktemp("claude-settings") / "settings.json")
    monkeypatch.setattr(replay_cli, "STATE", tmp_path_factory.mktemp("replay-state"))
    monkeypatch.setattr(verify, "STATE", tmp_path_factory.mktemp("verify-state"))
    from aimpg import scoreboard

    monkeypatch.setattr(scoreboard, "SECRET", tmp_path_factory.mktemp("aimpg-id") / "id")
    from aimpg import defaults

    monkeypatch.setattr(defaults, "REPLAY_STATE", tmp_path_factory.mktemp("defaults-replay"))
    monkeypatch.setattr(defaults, "VERIFY_STATE", tmp_path_factory.mktemp("defaults-verify"))
    from aimpg.replay import study_cli

    monkeypatch.setattr(study_cli, "STATE", tmp_path_factory.mktemp("study-state"))
    before = len(touched)
    yield
    if len(touched) > before:
        pytest.fail("touched the real home: " + "; ".join(touched[before:before + 5]))
