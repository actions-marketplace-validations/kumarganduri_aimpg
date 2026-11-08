import json
import subprocess

import pytest

from aimpg import scoreboard as sb
from aimpg.cli import main
from aimpg.replay import setups as S
from aimpg.replay.run import Record
from aimpg.replay.verify import build_record

SONNET = "claude-sonnet-5-5"


def run(commit, setup, *, passed=True, usages=None, cost=0.10, model=SONNET, repeat=0):
    usages = usages or [[5, 3000, 9000, 400]] * 3
    return Record(f"{commit}-{setup}-{repeat}", "/repo", commit, setup, repeat, "passed" if passed else "tests_failed",
                  passed, model, cost, 33.0, usages, "ok", "", True, "claude")


def record(tmp_path, *, challenger=S.TERSE, chal_cost=0.10, chal_pass=True, public=False, n=3,
           baseline=S.BASELINE, chal_model=SONNET, repo=None):
    if repo is None:
        repo = tmp_path / f"repo{len(list(tmp_path.iterdir()))}"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", f"root {repo.name}"], check=True)
    runs = [run(f"{i:040x}", baseline.name) for i in range(n)] + [
        run(f"{i:040x}", challenger.name, cost=chal_cost, passed=chal_pass, model=chal_model) for i in range(n)]
    return build_record(runs, claim="", baseline=baseline, challenger=challenger, repo=str(repo), task_mode="tests", public=public)


def put(records_dir, login, upload):
    data = sb.encode(upload)
    path = records_dir / login / sb.file_name(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path.stem


# ---------------------------------------------------------------- upload view

def test_private_upload_carries_no_texts_ids_or_exact_numbers(tmp_path):
    mine = S.custom(append_prompt="internal: ask #team-secrets", claude_md="db.internal.corp")
    rec = record(tmp_path, challenger=mine)
    up = sb.upload_view(rec)
    text = json.dumps(up)
    assert "internal" not in text and "sha256" not in text and f"{0:040x}" not in text
    assert up["challenger"] == {"name": "custom", "agent": "claude"}
    assert {r["commit"] for r in up["runs"]} == {0, 1, 2}  # run-local indexes, not commit ids
    assert up["runs"][0]["tokens"] == [15, 9000, 27000, 1200]  # sums, 2 significant figures
    assert up["runs"][0]["requests"] == "1-5" and up["runs"][0]["wall_s"] == 30
    assert up["week"].startswith("20") and "-W" in up["week"] and "created" not in up
    assert up["repo_id"] and len(up["repo_id"]) == 24
    assert sb.validate_upload(tmp_path / "x" / sb.file_name(sb.encode(up)), sb.encode(up)) == []


def test_repo_id_is_stable_per_repo_and_keyed_by_a_local_secret(tmp_path):
    a = record(tmp_path)
    repo = tmp_path / "repo0"
    assert sb.repo_id(str(repo)) == a["repo_id"]
    sb.SECRET.write_text("00" * 32)  # another machine's secret → a different id for the same repo
    assert sb.repo_id(str(repo)) != a["repo_id"]


def test_catalog_setups_keep_their_names():
    for name in ("claude-code+rtk", "claude-code@haiku", "codex@gpt-6.1-sol"):
        assert sb._public_spec({"name": name, "agent": "claude"}, False)["name"] == name


# ---------------------------------------------------------------- validation

def valid(tmp_path, **kw):
    up = sb.upload_view(record(tmp_path, **kw))
    return up


def problems(tmp_path, up, author=None, folder="me"):
    data = sb.encode(up)
    return sb.validate_upload(tmp_path / folder / sb.file_name(data), data, author=author)


def test_validation_rejects_tampering_and_leaks(tmp_path):
    up = valid(tmp_path)
    assert problems(tmp_path, up, author="me") == []
    assert problems(tmp_path, up, author="someone-else")  # wrong folder for the PR author
    data = sb.encode(up)
    assert sb.validate_upload(tmp_path / "me" / "wrong.json", data)  # name must be the content hash

    bad = json.loads(json.dumps(up))
    bad["runs"][0]["passed"] = not bad["runs"][0]["passed"]
    assert any("passed" in p for p in problems(tmp_path, bad))

    leak = json.loads(json.dumps(up))
    leak["challenger"]["claude_md"] = "secret"
    leak["affiliation"] = "see https://corp.example"
    found = problems(tmp_path, leak)
    assert any("only name, agent and model" in p for p in found) and any("URLs" in p for p in found)

    partial = json.loads(json.dumps(up))
    partial["runs"] = partial["runs"][:-1]
    assert any("incomplete" in p for p in problems(tmp_path, partial))

    bidi = json.loads(json.dumps(up))
    bidi["affiliation"] = "acme‮"
    assert any("control" in p for p in problems(tmp_path, bidi))

    html_name = json.loads(json.dumps(up))
    html_name["challenger"]["name"] = "<script>"
    assert any("letters, digits" in p for p in problems(tmp_path, html_name))


def test_validation_rechecks_the_verdict_against_the_runs(tmp_path):
    up = valid(tmp_path, chal_pass=False)
    up["verdict"]["answer"] = "SUPPORTED"
    assert any("solves fewer" in p for p in problems(tmp_path, up))


def test_supported_needs_the_cost_arithmetic_even_when_the_ratio_is_left_out(tmp_path):
    up = valid(tmp_path, challenger=S.with_model("haiku"), chal_model=S.MODELS["haiku"], chal_cost=0.05)
    assert up["verdict"]["answer"] == "SUPPORTED" and problems(tmp_path, up) == []
    for r in up["runs"]:
        if r["setup"] == "claude-code@haiku":
            r["cost_usd"] = 5.0  # the runs now say it costs 50x more
    for ratio in (None, 0, 50.0):  # left out, zero, or honest: SUPPORTED contradicts the runs
        up["verdict"]["cost_ratio"] = ratio
        assert problems(tmp_path, up), ratio
    up["verdict"]["energy"] = {"verdict": "uses less", "effect_mid": -0.5, "interval": [-0.6, -0.4]}
    assert any("energy verdict belongs" in p for p in problems(tmp_path, up))  # energy can't rank different models


def test_validation_types_are_strict(tmp_path):
    up = valid(tmp_path)

    def edited(change):
        bad = json.loads(json.dumps(up))
        change(bad)
        return problems(tmp_path, bad)

    for rerun_of in (["a"], {"a": 1}, "../../etc/passwd", "0" * 63):
        assert any("rerun_of" in p for p in edited(lambda u: u.update(rerun_of=rerun_of))), rerun_of
    assert any("--public" in p for p in edited(lambda u: u.update(rerun_of="0" * 64)))  # reruns are public
    assert edited(lambda u: u["runs"][0].update(cost_usd=True))
    assert edited(lambda u: u["runs"][0].update(wh=[-1e9, 1e12]))
    assert edited(lambda u: u["runs"][0].pop("cost_known"))  # a problem, not a KeyError
    assert edited(lambda u: u["runs"].append("run"))
    assert edited(lambda u: u["runs"][0].update(repeat=[0]))
    assert edited(lambda u: u.update(verdict=["SUPPORTED"]))
    assert edited(lambda u: u.update(baseline="claude-code"))
    assert any("cost_ratio" in p for p in edited(lambda u: u["verdict"].update(cost_ratio="0.11")))
    data = sb.encode(up).replace(b'"cost_usd": 0.1,', b'"cost_usd": NaN,', 1)
    assert b"NaN" in data and any("not JSON" in p for p in sb.validate_upload(tmp_path / "me" / sb.file_name(data), data))


def test_private_uploads_carry_only_known_fields(tmp_path):
    up = valid(tmp_path)
    up["notes"] = "github.com/acme/secret"
    up["runs"][0]["prompt"] = "fix the billing bug"
    found = problems(tmp_path, up)
    assert any("notes" in p for p in found) and any("prompt" in p for p in found)
    upper = valid(tmp_path)
    upper["affiliation"] = "ABCDEF0123" * 4  # a commit id in upper case
    assert any("commit shas" in p for p in problems(tmp_path, upper))
    lookalike = valid(tmp_path)
    lookalike["challenger"]["name"] = "сlaude-code+terse"  # Cyrillic с
    assert any("letters, digits" in p for p in problems(tmp_path, lookalike))


def test_two_private_custom_setups_keep_distinct_names(tmp_path):
    rec = record(tmp_path, baseline=S.custom("acme-internal-prompt", append_prompt="a"),
                 challenger=S.custom("acme-hooks", append_prompt="b"))
    up = sb.upload_view(rec)
    assert (up["baseline"]["name"], up["challenger"]["name"]) == ("custom-1", "custom-2")
    assert {r["setup"] for r in up["runs"]} == {"custom-1", "custom-2"} and problems(tmp_path, up) == []
    d = tmp_path / "records"
    put(d, "ann", up)
    assert sb.aggregate(sb.load(d))["collecting"] == []  # private names are never a public claim


def test_private_upload_repo_id_differs_from_the_public_one(tmp_path):
    public = sb.upload_view(record(tmp_path, public=True))
    private = sb.upload_view(record(tmp_path, repo=tmp_path / "repo0"))
    assert public["repo_id"] and private["repo_id"] and public["repo_id"] != private["repo_id"]
    again = sb.upload_view(record(tmp_path, repo=tmp_path / "repo0"))
    assert again["repo_id"] == private["repo_id"]  # still one repo across your private uploads


# ---------------------------------------------------------------- aggregation

def many(tmp_path, records_dir, logins, **kw):
    shas = []
    for login in logins:
        shas.append(put(records_dir, login, sb.upload_view(record(tmp_path, **kw))))
    return shas


def test_numbers_appear_only_with_5_repos_and_3_people(tmp_path):
    d = tmp_path / "records"
    many(tmp_path, d, ["ann", "bob", "cat", "dan"], chal_cost=0.05)
    data = sb.aggregate(sb.load(d))
    assert data["self_reported"] == [] and data["collecting"] == ["claude-code+terse vs claude-code"]
    many(tmp_path, d, ["eve"], chal_cost=0.05)
    (row,) = sb.aggregate(sb.load(d))["self_reported"]
    assert row["repos"] == 5 and row["submitters"] == 5
    assert row["answers"]["NOT PROVEN"] == 5 and row["median_cost_ratio"] == pytest.approx(0.5)  # same model: energy decides
    assert sb.aggregate(sb.load(d))["reproduced"] == []  # self-reported never reaches the headline


def test_one_account_cannot_carry_a_claim(tmp_path):
    d = tmp_path / "records"
    many(tmp_path, d, ["ann"] * 6 + ["bob", "cat"])  # ann's 6 repos are capped at 3, and 3 of 5 runs > 50%
    data = sb.aggregate(sb.load(d))
    assert data["self_reported"] == []


def test_vendor_claims_dont_count_unless_reproduced(tmp_path):
    d = tmp_path / "records"
    many(tmp_path, d, ["rtk-inc", "ann", "bob", "cat", "dan"], challenger=S.RTK)
    assert sb.aggregate(sb.load(d), {"claude-code+rtk": ["rtk-inc"]})["self_reported"] == []
    assert sb.aggregate(sb.load(d))["self_reported"]  # without the vendor list it would count


def test_tiers_from_independent_reruns(tmp_path):
    d = tmp_path / "records"
    original = put(d, "ann", sb.upload_view(record(tmp_path, public=True)))
    same_person = sb.upload_view(record(tmp_path, public=True))
    same_person["rerun_of"] = original
    put(d, "ann", same_person)
    assert sb.tiers(sb.load(d))[original] == "self-reported"  # rerunning your own record proves nothing
    agree = sb.upload_view(record(tmp_path, public=True))
    agree["rerun_of"] = original
    put(d, "bob", agree)
    assert sb.tiers(sb.load(d))[original] == "reproduced"
    disagree = sb.upload_view(record(tmp_path, public=True, chal_pass=False))
    disagree["rerun_of"] = original
    put(d, "cat", disagree)
    assert sb.tiers(sb.load(d))[original] == "disputed"


def test_a_rerun_counts_only_if_it_reran_that_record(tmp_path):
    d = tmp_path / "records"
    original = put(d, "ann", sb.upload_view(record(tmp_path, public=True)))
    private = put(d, "ann", sb.upload_view(record(tmp_path)))
    for login, kw in (("bob", {"challenger": S.RTK}), ("cat", {"n": 4}), ("dan", {})):
        other = sb.upload_view(record(tmp_path, public=True, **kw))  # another claim, other commits, a private target
        other["rerun_of"] = private if login == "dan" else original
        put(d, login, other)
    tier = sb.tiers(sb.load(d))
    assert tier[original] == "self-reported" and tier[private] == "self-reported"
    real = sb.upload_view(record(tmp_path, public=True))
    real["rerun_of"] = original
    put(d, "eve", real)
    assert sb.tiers(sb.load(d))[original] == "reproduced"
    bad = {"submitter": "x", "sha": "1" * 64, "upload": {**real, "rerun_of": ["a"]}}
    assert sb.tiers(sb.load(d) + [bad])[original] == "reproduced"  # a malformed rerun_of doesn't crash the build


def test_a_copied_repo_id_cannot_replace_someone_elses_record(tmp_path):
    d = tmp_path / "records"
    many(tmp_path, d, ["ann", "ann", "bob", "bob", "cat", "cat"], chal_cost=0.05)
    victim = next(e for e in sb.load(d) if e["submitter"] == "ann")["upload"]
    copy = sb.upload_view(record(tmp_path, chal_pass=False))
    copy.update(repo_id=victim["repo_id"], week="2026-W50")
    path = d / "mal" / sb.file_name(sb.encode(copy))
    path.parent.mkdir()
    path.write_bytes(sb.encode(copy))
    (row,) = sb.aggregate(sb.load(d))["self_reported"]
    assert row["answers"]["NOT PROVEN"] == 6  # ann's record still counts
    assert main(["scoreboard", "validate", str(path), "--author", "mal", "--records", str(d)]) == 1


def test_page_escapes_and_labels(tmp_path):
    d = tmp_path / "records"
    up = sb.upload_view(record(tmp_path, public=True))
    up["affiliation"] = "<b>acme</b>"
    put(d, "ann", up)
    data = sb.build(d, tmp_path / "site", demo=True)
    page = (tmp_path / "site" / "index.html").read_text()
    assert "DEMO DATA" in page and "not audited" in page and data["records"] == 1
    assert "<b>acme" not in page


# ---------------------------------------------------------------- submit

def test_submit_to_a_local_scoreboard_checkout(tmp_path, monkeypatch, capsys):
    rec = record(tmp_path, challenger=S.custom(append_prompt="secret prompt"))
    path = tmp_path / "r.record.json"
    path.write_text(json.dumps(rec))
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    board = tmp_path / "board"
    assert main(["submit", str(path), "--to-dir", str(board), "--login", "ann"]) == 0
    out = capsys.readouterr().out
    assert "This exact file will be published" in out and "secret prompt" not in out
    (written,) = list((board / "records" / "ann").glob("*.json"))
    assert main(["scoreboard", "validate", str(written), "--author", "ann"]) == 0


def test_submit_refuses_an_edited_record(tmp_path, monkeypatch, capsys):
    rec = record(tmp_path)
    rec["runs"][0]["passed"] = not rec["runs"][0]["passed"]
    path = tmp_path / "r.record.json"
    path.write_text(json.dumps(rec))
    assert main(["submit", str(path), "--to-dir", str(tmp_path), "--login", "ann", "--yes"]) == 1
    assert "fails `aimpg verify --check`" in capsys.readouterr().out


def test_submit_without_a_terminal_sends_nothing(tmp_path, monkeypatch, capsys):
    path = tmp_path / "r.record.json"
    path.write_text(json.dumps(record(tmp_path)))

    def closed(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", closed)
    assert main(["submit", str(path), "--to-dir", str(tmp_path / "board"), "--login", "ann"]) == 1
    assert "Nothing was sent" in capsys.readouterr().out and not (tmp_path / "board").exists()
