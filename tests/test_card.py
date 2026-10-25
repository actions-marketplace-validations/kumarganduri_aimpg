from aimpg import card


def numbers(**kw):
    base = dict(days=30, usd=1606.9, commits=471, kwh=(17.8, 161.0), typical_usd=1.66, typical_label="per kept commit",
                tip="57% of my agents' tokens re-read conversation from before my last commit", cost_per_working=None)
    return card.CardNumbers(**{**base, **kw})


def test_card_shows_totals_only_and_escapes_text():
    svg = card.svg(numbers(tip="<script>x</script> & more"))
    assert "$1.66" in svg and "per kept commit" in svg and "$1,607" in svg and "471" in svg
    assert "<script>" not in svg and "&lt;script&gt;" in svg
    assert 'width="1200" height="630"' in svg and "uvx aimpg report" in svg


def test_working_change_number_leads_when_it_exists():
    svg = card.svg(numbers(cost_per_working=3.10))
    assert "$3.10" in svg and "per working change" in svg
    assert "per working change" in card.post_text(numbers(cost_per_working=3.10))


def test_post_text_is_one_line_with_the_command():
    text = card.post_text(numbers())
    assert "\n" not in text and "uvx aimpg report" in text and "list prices" in text


def test_median_is_labelled_as_a_median():
    # "$1.71 per kept commit" next to "$1,938 over 382 commits" reads as a division that doesn't add up
    from types import SimpleNamespace

    from aimpg.model import Request, Task, Usage

    tasks = []
    for i in range(5):
        t = Task("/r", f"{i:040x}", 1.0, "s", "exact", "kept", author="a")
        t.add(Request(str(i), "s", "claude-sonnet-5", 0, Usage(output=1000 * (i + 1)), "/r"))
        tasks.append(t)
    n = card.numbers(SimpleNamespace(requests=[]), SimpleNamespace(tasks=tasks, unattributed={}), 0, 30 * 86400)
    assert n.typical_label == "median per kept commit"
    assert "median per kept commit" in card.post_text(n) and "median per kept commit" in card.svg(n)


def test_tip_speaks_as_the_cards_owner(monkeypatch):
    from types import SimpleNamespace

    tip = SimpleNamespace(measured="100% of your AI energy ran on the largest models (Opus/Fable class)")
    monkeypatch.setattr(card, "coach_tips", lambda *a: [tip])
    n = card.numbers(SimpleNamespace(requests=[]), SimpleNamespace(tasks=[]), 0, 86400)
    assert n.tip == "100% of my AI energy ran on the largest models (Opus/Fable class)"
    assert "↺" not in card.svg(n)


def test_post_keeps_all_history_cost_apart_from_the_window_totals():
    text = card.post_text(numbers(cost_per_working=75.5, days=3, usd=110, commits=5))
    assert "$75.50 per working change (all my judged commits, 30+ days old). Last 3 days: $110 over 5 commits" in text
    assert "all history" in card.svg(numbers(cost_per_working=75.5))


def test_write_creates_the_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(card, "to_png", lambda p: None)
    svg_path, _ = card.write(numbers(), tmp_path / "nodir" / "c.svg")
    assert svg_path.exists()


def test_write_always_gives_an_svg(tmp_path, monkeypatch):
    monkeypatch.setattr(card, "to_png", lambda p: None)
    svg_path, png = card.write(numbers(), tmp_path / "r.png")
    assert svg_path.suffix == ".svg" and svg_path.exists() and png is None
