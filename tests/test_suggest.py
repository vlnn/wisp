from datetime import timedelta
from pathlib import Path

import pytest

from conftest import NOW
from wisp import suggest
from wisp.records import Record


def a_record(text, minutes_ago=0):
    when = NOW - timedelta(minutes=minutes_ago)
    return Record.parsed(Path(f"/log/{minutes_ago}.md"), text, when, when)


def known(*lines):
    return suggest.vocabulary(a_record(line, n) for n, line in enumerate(lines))


def offered(text, vocab):
    return [s.text for s in suggest.suggestions(text, vocab)]


def test_vocabulary_spells_a_tag_in_lowercase():
    vocab = known("one #Articles", "two #articles", "three #Réunion")
    assert suggest.spelling("articles", vocab.spellings) == "#articles", (
        "a tag is suggested in lowercase whatever case it was once written in"
    )
    assert suggest.spelling("reunion", vocab.spellings) == "#réunion", (
        "lowercasing keeps the diacritics"
    )


def test_vocabulary_counts_records_not_repeats():
    vocab = known("essay essay #articles #articles", "draft #articles")
    assert vocab.count("articles") == 2, "a tag counts once per record that carries it"
    assert vocab.seen["essay"] == 1, "a word counts once per record it appears in"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("wrote #art", ["wrote #articles", "wrote #art-history"]),
        ("wrote #ARTI", ["wrote #articles"]),
        ("wrote #articles", []),
        ("wrote #zz", []),
        ("wrote art", []),
    ],
)
def test_completions_finish_the_tag_being_typed(text, expected):
    vocab = known("a #articles", "b #articles", "c #art-history")
    assert offered(text, vocab) == expected, f"{text!r} should be completed as {expected}"


def test_completions_offer_longer_tags_past_a_complete_one():
    vocab = known("a #art", "b #articles", "c #articles")
    assert offered("#art", vocab) == ["#articles"], (
        "a typed tag that exists still offers the tags it is a prefix of"
    )


@pytest.mark.parametrize(
    "text, expected",
    [
        ("met @fl", ["met @Flash"]),
        ("met @FLA", ["met @Flash"]),
        ("met @Flash", []),
        ("met @to", []),
    ],
)
def test_completions_finish_a_mention_in_its_usual_spelling(text, expected):
    vocab = known("with @Flash", "with @Flash again", "with @flash", "@today plans")
    assert offered(text, vocab) == expected, f"{text!r} should be completed as {expected}"


def test_completions_never_repeat_a_tag_already_in_the_line():
    vocab = known("a #articles", "b #art-history")
    assert offered("#articles about #art", vocab) == ["#articles about #art-history"], (
        "a tag the line already carries is not offered again"
    )


def test_suggestions_stop_at_the_limit():
    vocab = known(*(f"x #a{n}" for n in range(5)))
    assert len(suggest.suggestions("x #a", vocab)) == suggest.LIMIT, (
        "no more than LIMIT suggestions are offered"
    )


def test_completions_order_by_how_often_a_tag_is_used():
    vocab = known("a #arts", "b #articles", "c #articles")
    assert offered("#art", vocab) == ["#articles", "#arts"], "the more used tag comes first"


def test_nothing_known_offers_nothing():
    assert offered("wrote small article #art", known()) == [], "an empty log suggests nothing"
