"""Read OpenAI Codex CLI session logs (~/.codex/sessions/**/rollout-*.jsonl).

Verified on real files (codex-cli 0.159):
  * `event_msg` / `token_count` events carry `info.last_token_usage` for each
    model call: input_tokens (includes cached), cached_input_tokens,
    cache_write_input_tokens, output_tokens, reasoning_output_tokens.
  * `turn_context` carries the model (e.g. gpt-6-luna) and cwd; `session_meta`
    carries the session id and starting cwd.

Not yet verified on a real file (no local session ran shell commands): how a
`git commit` tool call is recorded. Detection is tolerant: any response_item
tool call whose arguments contain `git ... commit`, closed by an output item
with the same call_id. Commits made by hand are still matched by the fuzzy tier.

Codex token usage is mapped onto the same buckets as Claude Code:
    fresh_in = input − cached − cache_write · cache_read = cached
    cache_write = cache_write_input · output = output + reasoning (generated text)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator

from aimpg.logs import _GIT_COMMIT, commit_cwd, parse_ts
from aimpg.model import CommitCall, ParseResult, Request, Usage

DEFAULT_ROOT = Path.home() / ".codex" / "sessions"
TOOL_CALLS = ("function_call", "custom_tool_call", "local_shell_call")
TOOL_OUTPUTS = ("function_call_output", "custom_tool_call_output", "local_shell_call_output")


def iter_files(root: Path | None = None) -> Iterator[Path]:
    root = root or DEFAULT_ROOT  # looked up at call time so tests can point it elsewhere
    if root.is_dir():
        yield from sorted(p for p in root.rglob("*.jsonl") if p.is_file())


def _command_text(payload: dict) -> str:
    for key in ("arguments", "input", "action"):
        value = payload.get(key)
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                return value
        if isinstance(value, dict):
            cmd = value.get("command") or value.get("cmd")
            if isinstance(cmd, list):
                return " ".join(str(c) for c in cmd)
            if cmd:
                return str(cmd)
    return ""


def _tokens(usage: dict, key: str) -> int:
    """A token count, or ValueError for anything that isn't a non-negative integer."""
    value = int(usage.get(key) or 0)  # TypeError / ValueError / OverflowError on bad shapes
    if value < 0:
        raise ValueError(f"negative {key}")
    return value


def parse_codex(files: Iterable[Path]) -> ParseResult:
    result = ParseResult()
    stats = {"files": 0, "rows": 0, "unique_requests": 0, "corrupt_rows": 0, "unreadable_files": 0}
    versions: dict[str, int] = {}
    for path in files:
        stats["files"] += 1
        session, cwd, model = path.stem, "", ""
        pending: dict[str, tuple[float, str]] = {}
        n = 0
        try:
            fh = open(path, "rb")
        except OSError:  # deleted since it was listed, permission denied, ...
            stats["unreadable_files"] += 1
            continue
        with fh:
            for line in fh:
                if not line.strip():
                    continue
                stats["rows"] += 1
                try:
                    row = json.loads(line)
                except ValueError:
                    stats["corrupt_rows"] += 1
                    continue
                if not isinstance(row, dict):
                    stats["corrupt_rows"] += 1
                    continue
                # Codex's format isn't documented: a row of an unexpected shape is skipped, never fatal
                kind, payload = row.get("type"), row.get("payload")
                if not isinstance(payload, dict):
                    payload = {}
                ts = parse_ts(row.get("timestamp"))
                if kind == "session_meta":
                    session = str(payload.get("session_id") or payload.get("id") or session)
                    cwd = str(payload.get("cwd") or cwd)
                    if payload.get("cli_version"):
                        versions["codex " + str(payload["cli_version"])] = versions.get("codex " + str(payload["cli_version"]), 0) + 1
                elif kind == "turn_context":
                    model = str(payload.get("model") or model)
                    cwd = str(payload.get("cwd") or cwd)
                elif kind == "event_msg" and payload.get("type") == "token_count" and ts is not None:
                    info = payload.get("info")
                    usage = info.get("last_token_usage") if isinstance(info, dict) else None
                    if not usage:
                        continue
                    try:
                        if not isinstance(usage, dict):
                            raise TypeError("last_token_usage is not an object")
                        cached = _tokens(usage, "cached_input_tokens")
                        written = _tokens(usage, "cache_write_input_tokens")
                        total_in = _tokens(usage, "input_tokens")
                        output = _tokens(usage, "output_tokens") + _tokens(usage, "reasoning_output_tokens")
                    except (TypeError, ValueError, OverflowError):
                        stats["skipped_requests"] = stats.get("skipped_requests", 0) + 1
                        continue
                    n += 1
                    result.requests.append(Request(
                        id=f"codex:{session}:{n}",
                        session_id=f"codex:{session}",
                        model=model or "codex-unknown",
                        ts=ts,
                        usage=Usage(
                            fresh_in=max(0, total_in - cached - written),
                            cache_write=written,
                            cache_read=cached,
                            output=output,
                        ),
                        cwd=cwd,
                    ))
                elif kind == "response_item" and ts is not None:
                    ptype = payload.get("type")
                    if ptype in TOOL_CALLS:
                        command = _command_text(payload)
                        if _GIT_COMMIT.search(command):
                            repo_dir = commit_cwd(command, cwd) or cwd
                            pending[str(payload.get("call_id") or payload.get("id"))] = (ts, repo_dir)
                    elif ptype in TOOL_OUTPUTS:
                        call = pending.pop(str(payload.get("call_id")), None)
                        if call:
                            result.commit_calls.append(CommitCall(f"codex:{session}", call[1], call[0], ts))
        stats["unique_requests"] += n
    result.requests.sort(key=lambda r: r.ts)
    result.commit_calls.sort(key=lambda c: c.start)
    result.stats = stats
    result.versions = versions
    return result


def merge(*parts: ParseResult) -> ParseResult:
    """One ParseResult from several agents' logs."""
    out = ParseResult()
    stats: dict[str, int] = {}
    for p in parts:
        out.requests.extend(p.requests)
        out.commit_calls.extend(p.commit_calls)
        for k, v in p.files_touched.items():
            out.files_touched.setdefault(k, set()).update(v)
        for k, v in p.stats.items():
            stats[k] = stats.get(k, 0) + v
        for k, v in p.versions.items():
            out.versions[k] = out.versions.get(k, 0) + v
    out.requests.sort(key=lambda r: r.ts)
    out.commit_calls.sort(key=lambda c: c.start)
    out.stats = stats
    return out
