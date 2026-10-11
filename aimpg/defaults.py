"""`aimpg defaults`: turn a repo's replay evidence into a Claude Code setting the whole team gets.

    aimpg defaults --repo .            what the evidence says, and the setting it supports
    aimpg defaults --repo . --apply    write it to <repo>/.claude/settings.json (asks; keeps a backup)

Evidence, newest first, for this repo only:
  * model-picker runs (`aimpg replay models`): the cheapest model per solved
    task that solves within 10 points of the best;
  * `aimpg verify` records comparing two Claude models: a SUPPORTED cheaper challenger.

The setting is the project's default model. It's committed with the repo, so
everyone on the team starts with it; anyone can still switch with /model, and
a personal choice goes in .claude/settings.local.json instead. Evidence from
fewer than 20 runs per model is marked tentative, and nothing is written
without a yes.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from aimpg.replay import picker
from aimpg.replay.run import load_results

REPLAY_STATE = Path.home() / ".aimpg" / "replay"
VERIFY_STATE = Path.home() / ".aimpg" / "verify"


@dataclass
class Evidence:
    source: str  # file it came from
    model: str  # model id it supports as the default
    summary: str
    runs_per_model: int
    when: float

    @property
    def tentative(self) -> bool:
        return self.runs_per_model < picker.MIN_RUNS


def gather(repo: Path) -> list[Evidence]:
    repo = repo.resolve()
    found: list[Evidence] = []
    folder = REPLAY_STATE / repo.name
    for path in sorted(folder.glob("models-*.jsonl")) if folder.is_dir() else []:
        records, _ = load_results(path)
        records = [r for r in records if Path(r.repo).resolve() == repo]
        if not records:
            continue
        table = picker.rows(records)
        choice = picker.pick(table)
        if choice is None:
            continue
        found.append(Evidence(str(path), choice.model, picker.recommend(table), min(r.runs for r in table), path.stat().st_mtime))
    found += _from_verify(repo)
    return sorted(found, key=lambda e: e.when, reverse=True)


def _from_verify(repo: Path) -> list[Evidence]:
    from aimpg.scoreboard import repo_id

    rid = repo_id(str(repo))
    out = []
    for path in sorted(VERIFY_STATE.glob("*.record.json")) if VERIFY_STATE.is_dir() else []:
        try:
            rec = json.loads(path.read_text())
        except ValueError:
            continue
        b, c, v = rec.get("baseline", {}), rec.get("challenger", {}), rec.get("verdict", {})
        if rid is None or rec.get("repo_id") != rid or not (b.get("agent", "claude") == c.get("agent", "claude") == "claude"):
            continue
        models = v.get("challenger", {}).get("models") or []
        if v.get("answer") != "SUPPORTED" or len(models) != 1 or models == v.get("baseline", {}).get("models"):
            continue
        ratio = v.get("cost_ratio")
        summary = (f"verify: {c['name']} vs {b['name']} → SUPPORTED"
                   + (f", {1 - ratio:.0%} lower cost per solved task" if ratio else ""))
        runs = min(v.get("baseline", {}).get("runs", 0), v.get("challenger", {}).get("runs", 0))
        out.append(Evidence(str(path), models[0], summary, runs, path.stat().st_mtime))
    return out


def settings_path(repo: Path) -> Path:
    return repo / ".claude" / "settings.json"


def current_model(repo: Path) -> str | None:
    try:
        return json.loads(settings_path(repo).read_text()).get("model")
    except (OSError, ValueError, AttributeError):
        return None


def apply(repo: Path, model: str) -> Path | None:
    """Merge {"model": model} into the project settings. Returns the backup path, if a file existed."""
    path = settings_path(repo)
    data, backup = {}, None
    if path.exists():
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError(f"{path} isn't a JSON object")
        backup = path.with_name(f"settings.json.aimpg-backup-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(path, backup)
    data["model"] = model
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    return backup


def add_parser(sub) -> None:
    d = sub.add_parser("defaults", help="turn replay evidence into the repo's default Claude Code model (asks first)")
    d.add_argument("--repo", type=Path, default=Path("."))
    d.add_argument("--apply", action="store_true", help="write it to <repo>/.claude/settings.json")
    d.add_argument("--yes", action="store_true", help="skip the confirmation")


def main(args) -> int:
    repo = args.repo.expanduser().resolve()
    evidence = gather(repo)
    now = current_model(repo)
    print(f"Repo: {repo}")
    print(f"Current team default model: {now or 'none set (each person uses their own)'}")
    if not evidence:
        print("\nNo replay evidence for this repo yet. Find out which model is good enough on your own commits:")
        print(f"  aimpg replay select {repo}")
        print(f"  aimpg replay models {repo} --cap 10 --task-mode tests")
        return 0
    print("\nEvidence (newest first):")
    for e in evidence:
        print(f"  • {e.summary}" + (" (tentative)" if e.tentative and "Tentative" not in e.summary else ""))
        print(f"    from {e.source}")
    top = evidence[0]
    if now == top.model:
        print(f"\nThe default already matches the evidence: {now}.")
        return 0
    print(f"\nProposed: {settings_path(repo)}")
    print(f'  "model": "{top.model}"' + (f'   (was "{now}")' if now else ""))
    print("Commit it and everyone on the repo starts with this model; anyone can still switch with /model.")
    if top.tentative:
        print(f"Tentative: fewer than {picker.MIN_RUNS} runs per model. A bigger run makes this safer to roll out.")
    if not args.apply:
        print("\nTo write it:  aimpg defaults --apply" + (f" --repo {args.repo}" if args.repo != Path(".") else ""))
        return 0
    if not args.yes and input("Write it? [y/N] ").strip().lower() != "y":
        print("Stopped. Nothing was changed.")
        return 1
    try:
        backup = apply(repo, top.model)
    except ValueError as exc:
        print(f"Can't update the settings file: {exc}")
        return 1
    print(f"Written. {'Backup: ' + str(backup) if backup else ''}\nReview and commit {settings_path(repo).relative_to(repo)}.")
    return 0
