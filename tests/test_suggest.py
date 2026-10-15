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


@pytest.mark.parametrize(
    "word, expected",
    [
        ("articles", "article"),
        ("modules", "module"),
        ("stories", "story"),
        ("testing", "test"),
        ("wanted", "want"),
        ("used", "used"),
        ("bus", "bus"),
        ("clojure", "clojure"),
    ],
)
def test_stem(word, expected):
    assert suggest.stem(word) == expected, f"{word!r} should stem to {expected!r}"


@pytest.mark.parametrize(
    "word, part, expected",
    [
        ("article", "articles", True),
        ("articles", "article", True),
        ("modul", "modules", True),
        ("stories", "story", True),
        ("post", "postgres", True),
        ("art", "articles", False),
        ("cat", "category", False),
        ("modules", "articles", False),
    ],
)
def test_related(word, part, expected):
    assert suggest.related(word, part) is expected, (
        f"{word!r} and {part!r} should {'be' if expected else 'not be'} related"
    )


@pytest.mark.parametrize(
    "text, expected",
    [
        ("wrote small article on modules", ["wrote small article on modules #articles"]),
        ("project notes", ["project notes #side-project"]),
        ("story time", ["story time #stories"]),
        ("wrote art", []),
        ("article #articles", []),
        ("an article #zz", []),
        ("an article @fl", []),
    ],
)
def test_a_line_naming_a_tag_is_offered_it(text, expected):
    vocab = known("x #articles", "y #side-project", "z #stories")
    assert offered(text, vocab) == expected, f"{text!r} should be offered {expected}"


def test_named_tags_come_most_used_first():
    vocab = known("a #post", "b #postgres", "c #postgres")
    assert offered("post it", vocab) == ["post it #postgres", "post it #post"], (
        "tags a line names are offered most used first"
    )


def test_a_named_suggestion_says_why():
    (named,) = suggest.suggestions("an article", known("x #articles"))
    assert (named.adds, named.why) == ("#articles", "names it"), (
        "a name match should say it adds the tag because the line names it"
    )


def test_a_word_seen_once_with_a_tag_is_not_enough():
    vocab = known("essay on modules #articles")
    assert offered("essay draft", vocab) == [], "one record is not a habit yet"


def test_a_word_seen_twice_with_a_tag_offers_it():
    vocab = known("essay on modules #articles", "essay on types #articles")
    (seen,) = suggest.suggestions("essay draft", vocab)
    assert (seen.text, seen.why) == ("essay draft #articles", "seen with essay"), (
        "a word that came with a tag twice should offer it and say which word"
    )


def test_a_word_seen_mostly_without_the_tag_offers_nothing():
    vocab = known(
        "essay one #articles",
        "essay two #articles",
        "essay three",
        "essay four",
        "essay five",
    )
    assert offered("essay draft", vocab) == [], (
        "a word must come with the tag more than half the time"
    )


def test_half_the_time_is_not_more_than_half():
    vocab = known("essay one #articles", "essay two #articles", "essay three", "essay four")
    assert offered("essay draft", vocab) == [], "exactly half is not a majority"


def test_seen_with_names_every_word_that_counted():
    vocab = known("wrote essay #articles", "wrote essay again #articles")
    (seen,) = suggest.suggestions("wrote an essay", vocab)
    assert seen.why == "seen with essay, wrote", "the reason lists the words that counted, sorted"


def test_named_tags_come_before_seen_ones():
    vocab = known(
        "essay #articles",
        "essay again #articles",
        "macros #clojure",
    )
    assert offered("essay on clojure", vocab) == [
        "essay on clojure #clojure",
        "essay on clojure #articles",
    ], "a tag the line names is a stronger hint than one it was seen with"


def test_seen_tags_rank_by_how_strongly_they_go_with_the_line():
    vocab = known(
        "essay draft #articles",
        "essay draft #articles",
        "talk review #critique",
        "book review #critique",
        "review again #critique",
    )
    assert offered("essay draft review", vocab)[0] == "essay draft review #articles", (
        "the tag more of the line's words go with comes first"
    )


def test_a_tag_is_offered_once_whatever_the_reasons():
    vocab = known("article draft #articles", "article draft #articles")
    assert offered("article draft", vocab) == ["article draft #articles"], (
        "a tag both named and seen is offered once"
    )
