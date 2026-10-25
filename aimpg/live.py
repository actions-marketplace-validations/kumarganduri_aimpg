"""Live signals inside Claude Code: a status line and a post-commit note.

The monthly receipt is read once; behavior changes at the moment of decision.

    status line (after each AI message, ~300ms debounce):
      ⚡ task $1.10 · usual $0.90 · ctx 142k (69% from before your last commit) · 5h 63%

    after the agent runs `git commit` (PostToolUse hook, shown to you only):
      aimpg: that commit cost $2.40 over 31 requests (≈ 2 phone charges).

Speed matters (this runs constantly), so:
  * the session transcript is read incrementally: only bytes added since the
    last call, with the parse state saved in ~/.aimpg/live/<session>.json;
  * "usual" (your median cost per kept commit) comes from a daily cache that is
    refreshed in a detached background process, never inline.
Nothing here talks to the network or changes how the agent works.
"""

from __future__ import annotations

import json
import shlex
import os
import shutil
import stat
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from importlib import metadata
from pathlib import Path

from aimpg.cost import usage_cost
from aimpg.logs import _GIT_COMMIT, _worth_parsing, parse_ts
from aimpg.model import Usage

LIVE_DIR = Path.home() / ".aimpg" / "live"
BASELINE_MAX_AGE = 24 * 3600


@dataclass
class SessionState:
    offset: int = 0
    base_ctx: int = 0  # context at session start (system prompt + tools)
    task: dict = field(default_factory=dict)  # requestId -> [ts, model, fresh, write, read, out, write_1h, sidechain]
    pending: dict = field(default_factory=dict)  # tool_use id of a `git commit` -> start ts
    commits: list = field(default_factory=list)  # [{ts, cost, requests}]
    first_ctx_after_commit: int = 0
    last_ctx: int = 0

    @classmethod
    def load(cls, session: str) -> "SessionState":
        path = LIVE_DIR / f"{_safe(session)}.json"
        try:
            return cls(**json.loads(path.read_text()))
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self, session: str) -> None:
        LIVE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = LIVE_DIR / f"{_safe(session)}.json.tmp"
        tmp.write_text(json.dumps(asdict(self)))
        tmp.replace(LIVE_DIR / f"{_safe(session)}.json")

    # --- what the views need -------------------------------------------------
    def task_cost(self) -> float:
        return sum(usage_cost(_usage(v), v[1]) or 0.0 for v in self.task.values())

    def carried_share(self) -> float:
        """Share of the current context that was already there before the last commit."""
        if not self.commits or not self.last_ctx:
            return 0.0
        carried = max(0, self.first_ctx_after_commit - self.base_ctx)
        return min(1.0, carried / self.last_ctx)

    def stale_share_now(self) -> float:
        """At commit time: share of the current context that the next task doesn't need."""
        if not self.last_ctx:
            return 0.0
        return max(0.0, min(1.0, (self.last_ctx - self.base_ctx) / self.last_ctx))

    def close_task(self, ts: float) -> dict:
        """A commit happened at `ts`: everything so far was that commit's work."""
        done = {"ts": ts, "cost": round(self.task_cost(), 4), "requests": len(self.task),
                "stale_share": round(self.stale_share_now(), 3), "announced": False}
        self.commits.append(done)
        self.task = {}
        self.first_ctx_after_commit = 0
        return done


def _safe(session: str) -> str:
    return "".join(c for c in session if c.isalnum() or c in "-_")[:80] or "unknown"


def _usage(v: list) -> Usage:
    return Usage(fresh_in=v[2], cache_write=v[3], cache_read=v[4], output=v[5], cache_write_1h=v[6])


def update(state: SessionState, transcript: Path) -> SessionState:
    """Read only what was appended since last time. Partial last lines wait for the next call."""
    try:
        size = transcript.stat().st_size
    except OSError:
        return state
    if size < state.offset:  # transcript replaced: start over
        state = SessionState()
    with open(transcript, "rb") as fh:
        fh.seek(state.offset)
        chunk = fh.read()
    end = chunk.rfind(b"\n")
    if end < 0:
        return state
    for line in chunk[: end + 1].splitlines():
        if line.strip() and _worth_parsing(line, state.pending):
            try:
                _row(state, json.loads(line))
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                continue  # an odd row: skip it rather than break the status line on every refresh
    state.offset += end + 1
    return state


def _row(state: SessionState, row: dict) -> None:
    message = row.get("message") if isinstance(row.get("message"), dict) else {}
    ts = parse_ts(row.get("timestamp"))
    for block in message.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use" and block.get("name") == "Bash" and ts is not None:
            if _GIT_COMMIT.search(str((block.get("input") or {}).get("command") or "")):
                state.pending[str(block.get("id"))] = ts
        elif block.get("type") == "tool_result" and str(block.get("tool_use_id")) in state.pending and ts is not None:
            del state.pending[str(block.get("tool_use_id"))]
            if not state.commits or state.commits[-1]["ts"] < ts - 5:  # the hook may have closed it already
                state.close_task(ts)
    usage = message.get("usage")
    if row.get("type") != "assistant" or not isinstance(usage, dict) or ts is None:
        return
    if message.get("model") == "<synthetic>":
        return
    key = row.get("requestId") or message.get("id")
    if not key:
        return
    details = usage.get("output_tokens_details") if isinstance(usage.get("output_tokens_details"), dict) else {}
    split = usage.get("cache_creation") if isinstance(usage.get("cache_creation"), dict) else {}
    values = [
        ts,
        str(message.get("model") or ""),
        int(usage.get("input_tokens") or 0),
        int(usage.get("cache_creation_input_tokens") or 0),
        int(usage.get("cache_read_input_tokens") or 0),
        int(usage.get("output_tokens") or 0) + int(details.get("thinking_tokens") or 0),
        int(split.get("ephemeral_1h_input_tokens") or 0),
        bool(row.get("isSidechain")),
    ]
    current = state.task.get(key)
    if current is None or values[5] > current[5]:
        state.task[key] = values
    if not values[7]:
        ctx = values[2] + values[3] + values[4]
        state.last_ctx = ctx
        if not state.base_ctx:
            state.base_ctx = ctx
        if state.commits and not state.first_ctx_after_commit:
            state.first_ctx_after_commit = ctx


# --- "usual": median cost per kept commit, from a daily cache -------------------

def baseline_path() -> Path:
    return LIVE_DIR / "baseline.json"


def read_baseline() -> float | None:
    try:
        data = json.loads(baseline_path().read_text())
    except (OSError, ValueError):
        data = {}
    if time.time() - data.get("computed_at", 0) > BASELINE_MAX_AGE:
        _refresh_in_background()
    value = data.get("median_usd_per_commit")
    return float(value) if isinstance(value, (int, float)) and value > 0 else None


def _refresh_in_background() -> None:
    lock = LIVE_DIR / "baseline.lock"
    try:
        if lock.exists() and time.time() - lock.stat().st_mtime < 600:
            return  # a refresh is already running
        LIVE_DIR.mkdir(parents=True, exist_ok=True)
        lock.write_text(str(os.getpid()))
        subprocess.Popen(
            [sys.executable, "-m", "aimpg.live", "refresh-baseline"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        pass


def compute_baseline() -> dict:
    from aimpg.attribution import attribute
    from aimpg.logs import iter_log_files, parse_logs
    from aimpg.receipt import KEPT, task_energy

    from aimpg import codex_logs

    now = time.time()
    parsed = codex_logs.merge(parse_logs(iter_log_files()), codex_logs.parse_codex(codex_logs.iter_files()))
    attribution = attribute(parsed, now - 30 * 86400, now)
    all_energies = task_energy(attribution.tasks)
    from aimpg import ledger

    ledger.record(all_energies)  # the daily refresh also keeps the history growing
    energies = [e for e in all_energies if e.task.requests]
    kept = [e for e in energies if e.task.status in KEPT]
    pool = kept if len(kept) >= 5 else energies
    data = {
        "computed_at": now,
        "median_usd_per_commit": round(statistics.median(e.usd for e in pool), 4) if pool else None,
        "commits": len(pool),
    }
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    baseline_path().write_text(json.dumps(data))
    (LIVE_DIR / "baseline.lock").unlink(missing_ok=True)
    return data


# --- views ------------------------------------------------------------------------

AMBER, RED, DIM, RESET = "\033[33m", "\033[31m", "\033[2m", "\033[0m"


def _usd(x: float) -> str:
    return f"${x:,.0f}" if x >= 100 else f"${x:.2f}"


def _k(n: int) -> str:
    return f"{n / 1000:.0f}k" if n >= 1000 else str(n)


def status_line(data: dict, state: SessionState, usual: float | None) -> str:
    task = state.task_cost()
    parts = []
    color = ""
    if usual:
        if task > 3 * usual:
            color = RED
        elif task > 1.5 * usual:
            color = AMBER
    parts.append(f"{color}task {_usd(task)}{RESET if color else ''}")
    if usual:
        parts.append(f"usual {_usd(usual)}")
    ctx = (data.get("context_window") or {}).get("total_input_tokens") or state.last_ctx
    if ctx:
        share = state.carried_share()
        if share >= 0.05:
            parts.append(f"ctx {_k(ctx)} ({share:.0%} from before your last commit)")
        else:
            parts.append(f"ctx {_k(ctx)}")
    five = ((data.get("rate_limits") or {}).get("five_hour") or {}).get("used_percentage")
    if isinstance(five, (int, float)):
        parts.append(f"5h {five:.0f}%")
    return "⚡ " + " · ".join(parts)


def commit_note(done: dict) -> str:
    return f"aimpg: that commit cost {_usd(done['cost'])} over {done['requests']} AI requests."


def _read_stdin_json() -> dict:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def run_statusline(previous: str | None = None) -> int:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw or "{}")
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    out = []
    if previous:  # keep the user's own status line, then add ours
        try:
            prev = subprocess.run(previous, shell=True, input=raw, capture_output=True, text=True, timeout=2)
            if prev.stdout.strip():
                out.append(prev.stdout.rstrip("\n"))
        except (subprocess.TimeoutExpired, OSError):
            pass
    session, transcript = data.get("session_id"), data.get("transcript_path")
    if session and transcript:
        state = update(SessionState.load(session), Path(transcript))
        state.save(session)
        out.append(status_line(data, state, read_baseline()))
    print("\n".join(out))
    return 0


def run_post_commit_hook() -> int:
    data = _read_stdin_json()
    command = str((data.get("tool_input") or {}).get("command") or "")
    if data.get("tool_name") != "Bash" or not _GIT_COMMIT.search(command):
        return 0  # most Bash calls: nothing to do, exit fast
    session, transcript = data.get("session_id"), data.get("transcript_path")
    if not session or not transcript:
        return 0
    state = update(SessionState.load(session), Path(transcript))
    if state.task:
        done = state.close_task(time.time())
    elif state.commits and not state.commits[-1].get("announced") and time.time() - state.commits[-1]["ts"] < 120:
        done = state.commits[-1]  # the status line already saw this commit in the transcript
    else:
        state.save(session)
        return 0
    done["announced"] = True
    state.save(session)
    print(json.dumps({"systemMessage": commit_note(done)}))
    return 0


if __name__ == "__main__":  # python -m aimpg.live refresh-baseline
    if sys.argv[1:] == ["refresh-baseline"]:
        compute_baseline()


# --- install / uninstall into Claude Code settings --------------------------------------

SETTINGS = Path.home() / ".claude" / "settings.json"
PREVIOUS = LIVE_DIR / "previous_statusline.json"
OURS = ("aimpg statusline", "aimpg hook post-commit")


class SettingsError(Exception):
    """settings.json can't be changed safely; the message says why. Nothing was written."""


def _is_our_line(command: str) -> bool:
    return "aimpg" in command and command.endswith("statusline")


def _is_our_hook(command: str) -> bool:
    return "aimpg" in command and command.endswith("hook post-commit")


def _ephemeral(path: str) -> bool:
    """True for an aimpg that uvx (or pipx run) unpacked into a cache or temp dir, which can vanish."""
    real = Path(os.path.realpath(path))
    if any(p.startswith(("archive-v", "builds-v")) for p in real.parts):  # uv's cache layout
        return True
    roots = [os.environ.get("UV_CACHE_DIR"), os.environ.get("PIPX_CACHE_DIR"), tempfile.gettempdir(),
             Path.home() / ".cache" / "uv", Path.home() / ".local" / "pipx" / ".cache"]
    return any(real.is_relative_to(os.path.realpath(r)) for r in roots if r)


def launcher() -> tuple[list[str] | None, str]:
    """The command Claude Code should run aimpg with, and a line for the user about it ("" if none needed).

    `uvx aimpg live install` finds aimpg in uv's cache, which `uv cache clean` deletes: the status line
    and the hook would then break silently. So use a permanent aimpg on PATH, else uvx pinned to this version.
    """
    for d in os.environ.get("PATH", "").split(os.pathsep):
        exe = shutil.which("aimpg", path=d) if d else None
        if exe and not _ephemeral(exe):
            return [exe], ""
    uvx = shutil.which("uvx")
    if uvx and not _ephemeral(uvx):
        pinned = f"aimpg@{metadata.version('aimpg')}"
        return [uvx, pinned], (f"aimpg is running from uv's temporary cache, so Claude Code will call it as `uvx {pinned}`."
                               "\nFor a faster status line, install it for good:  uv tool install aimpg && aimpg live install")
    return None, "Install aimpg permanently first so Claude Code can call it:  uv tool install aimpg"


def _prefix(exe: str | list[str]) -> str:
    # a path with spaces or quotes must stay one argument
    return shlex.join(exe) if isinstance(exe, (list, tuple)) else shlex.quote(exe)


def _load_settings(path: Path) -> dict:
    """settings.json as a dict, or SettingsError if it isn't the shape Claude Code writes."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError) as exc:
        raise SettingsError(f"Couldn't read {path}: {exc}. Nothing changed.") from exc
    except ValueError as exc:
        raise SettingsError(f"{path} isn't valid JSON ({exc}). Nothing changed; fix it first.") from exc
    hooks = (data.get("hooks") or {}) if isinstance(data, dict) else None
    post = (hooks.get("PostToolUse") or []) if isinstance(hooks, dict) else None
    ok = (isinstance(data, dict) and isinstance(data.get("statusLine") or {}, dict) and isinstance(post, list)
          and all(isinstance(e, dict) and isinstance(e.get("hooks") or [], list)
                  and all(isinstance(h, dict) for h in e.get("hooks") or []) for e in post))
    if not ok:
        raise SettingsError(f"{path} has a statusLine or hooks entry in a shape aimpg doesn't expect. Nothing changed.")
    return data


def _check_writable(path: Path) -> None:
    target = path.resolve()
    if target.exists() and not os.access(target, os.W_OK):
        raise SettingsError(f"{target} is read-only. Nothing changed.")


def _write_json(path: Path, data: dict) -> None:
    """Write via a temp file and rename, so Claude Code never reads a half-written settings file.

    A symlinked settings.json (dotfiles) is followed and its target updated, and the file keeps its mode.
    """
    target = path.resolve()
    tmp = target.with_name(f".{target.name}.aimpg-tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2) + "\n")
        if target.exists():
            os.chmod(tmp, stat.S_IMODE(target.stat().st_mode))
        os.replace(tmp, target)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise SettingsError(f"Couldn't write {target}: {exc}. Nothing changed.") from exc


def planned_settings(current: dict, exe: str | list[str]) -> dict:
    """The settings after install: our status line (wrapping any existing one) + a commit hook."""
    new = json.loads(json.dumps(current))
    prefix = _prefix(exe)
    new["statusLine"] = {**(new.get("statusLine") or {}), "type": "command", "command": f"{prefix} statusline"}
    new["hooks"] = new.get("hooks") or {}
    hooks = new["hooks"]["PostToolUse"] = new["hooks"].get("PostToolUse") or []
    ours = [h for e in hooks for h in e.get("hooks") or [] if _is_our_hook(str(h.get("command", "")))]
    for h in ours:  # from an earlier install, maybe from a path that's gone: point it here
        h["command"] = f"{prefix} hook post-commit"
    if not ours:
        hooks.append({"matcher": "Bash", "hooks": [{"type": "command", "command": f"{prefix} hook post-commit", "timeout": 10}]})
    return new


def install(settings: Path | None = None, exe: str | list[str] = "aimpg", *, confirm=input) -> str:
    settings = settings or SETTINGS  # looked up at call time so tests can point it elsewhere
    current = _load_settings(settings)
    line = current.get("statusLine") or {}
    existing = str(line.get("command", ""))
    new = planned_settings(current, exe)
    if new == current:
        return "aimpg live is already installed."
    _check_writable(settings)
    prefix = _prefix(exe)
    if _is_our_line(existing):
        note = f"  (replaces the earlier aimpg command, `{existing}`)"
    else:
        note = f"  (your current one, `{existing}`, keeps showing above it)" if existing else ""
    print(f"This will change {settings}:")
    print(f"  statusLine → {prefix} statusline" + note)
    print(f"  PostToolUse hook (Bash) → {prefix} hook post-commit  (shows you one line after the agent commits)")
    try:
        answer = confirm("Apply? [y/N] ")
    except EOFError:  # no terminal to answer: same as "no"
        answer = ""
    if answer.strip().lower() != "y":
        return "Nothing changed."
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    if existing and not _is_our_line(existing):
        PREVIOUS.write_text(json.dumps(line))  # the whole object, so uninstall puts back exactly this
    if settings.exists():
        backup = settings.with_suffix(f".json.aimpg-backup-{int(time.time())}")
        shutil.copy2(settings.resolve(), backup)  # keeps the mode: settings can hold secrets in "env"
    settings.parent.mkdir(parents=True, exist_ok=True)
    _write_json(settings, new)
    return "Installed. It shows up after the next AI message. Undo any time with `aimpg live uninstall`."


def uninstall(settings: Path | None = None) -> str:
    settings = settings or SETTINGS
    if not settings.exists():
        return "Nothing to remove."
    current = _load_settings(settings)
    new = json.loads(json.dumps(current))
    if _is_our_line(str((new.get("statusLine") or {}).get("command", ""))):
        try:
            prev = json.loads(PREVIOUS.read_text())
        except (OSError, ValueError):
            prev = None
        if isinstance(prev, dict) and prev.get("command"):
            new["statusLine"] = prev if "type" in prev else {"type": "command", **prev}  # older installs saved only the command
        else:
            new.pop("statusLine", None)
    post = (new.get("hooks") or {}).get("PostToolUse") or []
    kept = [e for e in post if not any(_is_our_hook(str(h.get("command", ""))) for h in e.get("hooks") or [])]
    if post:
        if kept:
            new["hooks"]["PostToolUse"] = kept
        else:
            new["hooks"].pop("PostToolUse")
            if not new["hooks"]:
                new.pop("hooks")
    if new == current:
        return "aimpg live is not installed. Nothing changed."
    _check_writable(settings)
    _write_json(settings, new)
    PREVIOUS.unlink(missing_ok=True)
    return "Removed. Your previous status line (if any) is back."


def previous_statusline() -> str | None:
    try:
        return json.loads(PREVIOUS.read_text())["command"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
