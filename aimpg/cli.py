"""aimpg: energy receipts for AI coding.

    report    the fuel receipt for your Claude Code usage, with measured tips
    pr        AI energy + cost of the current branch's commits (markdown; --post to the PR)
    export    one CSV row per AI-assisted commit, for teams and sustainability reports
    replay    compare agent setups and models on your own past commits
    live      install/uninstall the live status line + post-commit note in Claude Code
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from aimpg import share
from aimpg.attribution import attribute
from aimpg.gitkept import DAY
from aimpg.logs import DEFAULT_ROOT, iter_log_files, parse_logs
from aimpg.receipt import render
from aimpg.replay import cli as replay_cli
from aimpg import defaults as defaults_mod
from aimpg import scoreboard as scoreboard_mod
from aimpg.replay import verify as verify_mod


def _common(p: argparse.ArgumentParser, days: int) -> None:
    p.add_argument("--days", type=int, default=days, help=f"window size in days (default {days})")
    p.add_argument("--logs", type=Path, default=DEFAULT_ROOT, help="Claude Code projects dir")
    p.add_argument("--codex-logs", type=Path, default=None, help="Codex sessions dir (default ~/.codex/sessions)")
    p.add_argument("--cursor-usage", type=Path, action="append", default=[], metavar="CSV",
                   help="Cursor usage export (cursor.com/dashboard → Usage → Export CSV); repeatable")
    p.add_argument("--cursor-repo", type=Path, default=None, help="repo the Cursor work was in (matches it to your commits by time)")
    p.add_argument("--cursor-user", default=None, help="only this User's rows (team exports)")
    p.add_argument("--fetch", action="store_true", help="git fetch each repo first (uses the network)")


def _analyze(args):
    from aimpg import codex_logs, cursor_usage

    now = time.time()
    since = now - args.days * DAY
    cursor_repo = str(args.cursor_repo.expanduser().resolve()) if args.cursor_repo else ""
    parsed = codex_logs.merge(
        parse_logs(iter_log_files(args.logs)),
        codex_logs.parse_codex(codex_logs.iter_files(args.codex_logs)),
        cursor_usage.parse_cursor([p.expanduser() for p in args.cursor_usage], cursor_repo, args.cursor_user),
    )
    return parsed, attribute(parsed, since, now, refresh=args.fetch), since, now


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aimpg", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    _common(sub.add_parser("report", help="print the energy receipt"), 30)

    pr = sub.add_parser("pr", help="AI energy and cost of this branch's commits, as a PR comment")
    _common(pr, 90)
    pr.add_argument("--repo", type=Path, default=Path("."), help="repo to summarize (default: current folder)")
    pr.add_argument("--base", default="main", help="base branch (default main)")
    pr.add_argument("--post", action="store_true", help="add the summary as a comment on the open PR (uses gh)")

    export = sub.add_parser("export", help="one CSV row per AI-assisted commit")
    _common(export, 30)
    export.add_argument("--csv", type=Path, required=True, help="output file")
    export.add_argument("--no-subjects", action="store_true", help="leave commit messages out (privacy)")
    export.add_argument("--no-authors", action="store_true", help="leave author emails out (privacy)")

    sci_p = sub.add_parser("sci", help="carbon intensity in the GSF SCI for AI format (per token, commit, working change)")
    _common(sci_p, 30)
    sci_p.add_argument("--grid", type=float, default=None, help="grid intensity in g CO2e/kWh (default: world average)")
    sci_p.add_argument("--json", type=Path, default=None, help="also write the full disclosure as JSON")

    notes_p = sub.add_parser("notes", help="share your AI cost per commit with your team, as git notes (metadata only)")
    notes_p.add_argument("action", choices=("push", "write"), help="push: write notes on your commits and push them; write: local only")
    _common(notes_p, 30)
    notes_p.add_argument("--repo", type=Path, default=Path("."), help="repo to note (default: here)")
    notes_p.add_argument("--remote", default="origin")

    team_p = sub.add_parser("team", help="team numbers from aimpg git notes (used by the GitHub Action)")
    team_sub = team_p.add_subparsers(dest="team_command", required=True)
    tpr = team_sub.add_parser("pr", help="AI cost of this branch's commits")
    tpr.add_argument("--repo", type=Path, default=Path("."))
    tpr.add_argument("--base", default="origin/main", help="base ref (default origin/main)")
    trl = team_sub.add_parser("rollup", help="cost per working change and waste ratio for the team")
    trl.add_argument("--repo", type=Path, default=Path("."))
    trl.add_argument("--days", type=int, default=90)
    trl.add_argument("--min-group", type=int, default=5, help="people needed before numbers show (default 5)")

    live = sub.add_parser("live", help="live status line + post-commit note inside Claude Code")
    live.add_argument("action", choices=("install", "uninstall"))
    sub.add_parser("statusline", help=argparse.SUPPRESS)  # called by Claude Code
    hook = sub.add_parser("hook", help=argparse.SUPPRESS)  # called by Claude Code
    hook.add_argument("event", choices=("post-commit",))

    replay_cli.add_parser(sub)
    verify_mod.add_parser(sub)
    scoreboard_mod.add_parsers(sub)
    defaults_mod.add_parser(sub)
    from aimpg.replay import study_cli

    study_cli.add_parser(sub)
    args = parser.parse_args(argv)
    if args.command == "replay":
        return replay_cli.main(args)
    if args.command == "verify":
        return verify_mod.main(args)
    if args.command in ("submit", "scoreboard"):
        return scoreboard_mod.main(args)
    if args.command == "defaults":
        return defaults_mod.main(args)
    if args.command == "study":
        from aimpg.replay import study_cli

        return study_cli.main(args)
    if args.command in ("statusline", "hook", "live"):
        from aimpg import live as live_mod

        if args.command == "statusline":
            return live_mod.run_statusline(live_mod.previous_statusline())
        if args.command == "hook":
            return live_mod.run_post_commit_hook()
        if args.action == "install":
            import shutil

            exe = shutil.which("aimpg")
            if exe is None:
                print("Install aimpg permanently first so Claude Code can call it:  uv tool install aimpg")
                return 1
            print(live_mod.install(exe=exe))
        else:
            print(live_mod.uninstall())
        return 0

    if args.command == "team":
        from aimpg import team

        repo = str(args.repo.resolve())
        if args.team_command == "pr":
            try:
                shas = share.branch_commits(args.repo, args.base)
            except RuntimeError as exc:
                print(f"Can't list this branch's commits: {exc}")
                return 1
            sys.stdout.write(team.pr_markdown(team.pr_summary(repo, shas)))
        else:
            sys.stdout.write(team.rollup_markdown(team.rollup(repo, days=args.days, min_group=args.min_group)))
        return 0

    if args.days <= 0:
        parser.error("--days must be positive")
    from aimpg import codex_logs
    from aimpg.cursor_usage import CursorExportError

    if not (args.logs.is_dir() or args.cursor_usage or (args.codex_logs or codex_logs.DEFAULT_ROOT).is_dir()):
        print(f"No Claude Code logs found at {args.logs}. Nothing to report.")
        return 0
    for path in args.cursor_usage:
        if not path.expanduser().is_file():
            print(f"Cursor export not found: {path}")
            return 1
    try:
        parsed, attribution, since, now = _analyze(args)
    except (CursorExportError, UnicodeDecodeError) as exc:
        print(f"Can't read the Cursor export: {exc}")
        return 1

    if args.command == "export":
        rows = share.csv_rows(attribution, subjects=not args.no_subjects, authors=not args.no_authors)
        share.write_csv(rows, args.csv)
        print(f"Wrote {len(rows)} commits to {args.csv}")
        return 0
    if args.command == "pr":
        try:
            shas = share.branch_commits(args.repo, args.base)
        except RuntimeError as exc:
            print(f"Can't list this branch's commits: {exc}")
            return 1
        markdown = share.pr_markdown(attribution, shas, args.repo.resolve().name)
        sys.stdout.write(markdown)
        if args.post:
            try:
                share.post_comment(markdown, args.repo)
            except RuntimeError as exc:
                print(f"\nNot posted: {exc}")
                return 1
            print("\nPosted to the pull request.")
        return 0

    from aimpg import durable, ledger
    from aimpg.receipt import task_energy

    if args.command == "notes":
        from aimpg import team
        from aimpg.gitkept import GitError, repo_root

        repo = repo_root(str(args.repo.resolve()))
        if repo is None:
            print(f"{args.repo} is not a git repo.")
            return 1
        try:
            written, _ = team.write_notes(repo, task_energy(attribution.tasks))
            print(f"Wrote {written} notes on your AI-assisted commits in {repo} ({team.FULL_REF}; metadata only).")
            if args.action == "push":
                print(team.push(repo, args.remote) + ". Your team's GitHub Action can now include them.")
        except GitError as exc:
            print(f"notes: {exc}")
            return 1
        return 0

    if args.command == "sci":
        from aimpg import sci

        ledger.record(task_energy(attribution.tasks))
        judged = durable.judge(ledger.load(), now)
        in_window = [r for r in parsed.requests if r.ts >= since]
        result = sci.compute(in_window, len(attribution.tasks), judged,
                             grid=args.grid if args.grid is not None else sci.default_grid(), period=(since, now))
        sys.stdout.write(sci.render(result))
        if args.json:
            sci.write(result, args.json)
            print(f"\nFull disclosure (boundary, inputs, sources, ranges): {args.json}")
        return 0

    ledger.record(task_energy(attribution.tasks))
    judged = durable.judge(ledger.load(), now)
    sys.stdout.write(render(parsed, attribution, since, now, judged))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
