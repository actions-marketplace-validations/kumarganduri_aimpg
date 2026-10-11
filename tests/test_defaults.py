import json
import subprocess
from dataclasses import asdict

from aimpg import defaults
from aimpg.cli import main
from aimpg.replay import setups as S
from aimpg.replay.run import Record
from aimpg.replay.verify import build_record


def git_repo(path):
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "root"], check=True)
    return path


def rec(repo, commit, setup, model, cost, passed=True):
    return Record(f"{commit}{setup}", str(repo), commit, setup, 0, "passed" if passed else "tests_failed", passed, model,
                  cost, 20.0, [[5, 1000, 4000, 200]], "ok", "", True, "claude")


def picker_run(repo):
    folder = defaults.REPLAY_STATE / repo.name
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(4):
        rows.append(rec(repo, f"c{i}", "claude-code@opus", "claude-opus-5-5", 0.30))
        rows.append(rec(repo, f"c{i}", "claude-code@sonnet", "claude-sonnet-5-5", 0.12))
        rows.append(rec(repo, f"c{i}", "claude-code@haiku", "claude-haiku-4-5", 0.05, passed=i < 2))
    (folder / "models-tests-1.jsonl").write_text("".join(json.dumps(asdict(r)) + "\n" for r in rows))


def test_no_evidence_says_how_to_get_some(tmp_path, capsys):
    repo = git_repo(tmp_path / "proj")
    assert main(["defaults", "--repo", str(repo)]) == 0
    assert "No replay evidence" in capsys.readouterr().out
    assert not defaults.settings_path(repo).exists()


def test_model_picker_evidence_proposes_without_writing(tmp_path, capsys):
    repo = git_repo(tmp_path / "proj")
    picker_run(repo)
    assert main(["defaults", "--repo", str(repo)]) == 0
    out = capsys.readouterr().out
    assert '"model": "claude-sonnet-5-5"' in out and "Tentative" in out
    assert not defaults.settings_path(repo).exists()  # proposing never writes


def test_apply_merges_keeps_a_backup_and_is_idempotent(tmp_path, monkeypatch, capsys):
    repo = git_repo(tmp_path / "proj")
    picker_run(repo)
    path = defaults.settings_path(repo)
    path.parent.mkdir()
    path.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}, "model": "claude-opus-5-5"}))
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    assert main(["defaults", "--repo", str(repo), "--apply"]) == 0
    data = json.loads(path.read_text())
    assert data == {"permissions": {"allow": ["Bash(ls)"]}, "model": "claude-sonnet-5-5"}
    (backup,) = path.parent.glob("settings.json.aimpg-backup-*")
    assert json.loads(backup.read_text())["model"] == "claude-opus-5-5"
    capsys.readouterr()
    assert main(["defaults", "--repo", str(repo), "--apply"]) == 0
    assert "already matches" in capsys.readouterr().out


def test_saying_no_changes_nothing(tmp_path, monkeypatch):
    repo = git_repo(tmp_path / "proj")
    picker_run(repo)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert main(["defaults", "--repo", str(repo), "--apply"]) == 1
    assert not defaults.settings_path(repo).exists()


def test_a_supported_cheaper_model_in_verify_counts_as_evidence(tmp_path):
    repo = git_repo(tmp_path / "proj")
    runs = [rec(repo, f"c{i}", "claude-code", "claude-sonnet-5-5", 0.12) for i in range(5)] + [
        rec(repo, f"c{i}", "claude-code@haiku", "claude-haiku-4-5", 0.05) for i in range(5)]
    record = build_record(runs, claim="", baseline=S.BASELINE, challenger=S.with_model("haiku"), repo=str(repo), task_mode="tests", public=False)
    assert record["verdict"]["answer"] == "SUPPORTED"
    defaults.VERIFY_STATE.mkdir(parents=True, exist_ok=True)
    (defaults.VERIFY_STATE / "x.record.json").write_text(json.dumps(record))
    (e,) = defaults.gather(repo)
    assert e.model == "claude-haiku-4-5" and "SUPPORTED" in e.summary and e.tentative


def test_other_repos_evidence_is_ignored(tmp_path):
    mine, other = git_repo(tmp_path / "proj"), git_repo(tmp_path / "other")
    picker_run(other)
    (defaults.REPLAY_STATE / "proj").mkdir()
    (defaults.REPLAY_STATE / "proj" / "models-x.jsonl").write_text(
        (defaults.REPLAY_STATE / "other" / "models-tests-1.jsonl").read_text())  # same folder name, different repo path
    assert defaults.gather(mine) == []
