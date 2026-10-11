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


def test_write_always_gives_an_svg(tmp_path, monkeypatch):
    monkeypatch.setattr(card, "to_png", lambda p: None)
    svg_path, png = card.write(numbers(), tmp_path / "r.png")
    assert svg_path.suffix == ".svg" and svg_path.exists() and png is None
