from datetime import timedelta
from pathlib import Path

import pytest

from conftest import NOW
from wisp import search
from wisp.records import Kind, Record

MIXED = (
    "! api keys are in 1password",
    "* test api manually",
    ". document api",
    ". fix the build",
    "? api v2 or patch v1",
    "= patch v1, api v2 in spring",
    "api v1",
)


@pytest.fixture
def mixed():
    return [
        Record.parsed(
            Path(f"/log/{n}.md"), text, NOW - timedelta(minutes=n), NOW - timedelta(minutes=n)
        )
        for n, text in enumerate(MIXED)
    ]


@pytest.mark.parametrize(
    "query, text, hit",
    [
        ("making v1", "making API v1", True),
        ("api", "making API v1", True),
        ("api", "testing api manually", True),
        ("api", "autotests", False),
        ("v1", "making API v1", True),
        ("v1", "making API v10", True),
        ("v2", "making API v1", False),
        ("l", "meeting with L", True),
        ("meeting l", "meeting with L", True),
        ("docs reading", "reading docs", True),
        ("", "anything", True),
        ("   ", "anything", True),
        ("réunion", "Reunion", True),
        ("reunion", "Réunion", True),
        ("ДОКИ", "читаю доки", True),
        ("make", "making API v1", False),
    ],
)
def test_matches(query, text, hit):
    assert search.matches(query, text) is hit, (
        f"{query!r} should {'match' if hit else 'not match'} {text!r}"
    )


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Making API v1", ["making", "api", "v1"]),
        ("get -R /remote/dir", ["get", "r", "remote", "dir"]),
        ("Crème Brûlée", ["creme", "brulee"]),
    ],
)
def test_words(text, expected):
    assert search.words(text) == expected, f"words of {text!r} should be {expected}"


@pytest.mark.parametrize(
    "query, kind, words",
    [
        ("api", None, "api"),
        ("", None, ""),
        (".", Kind.TASK, ""),
        (". api", Kind.TASK, "api"),
        ("*", Kind.DONE, ""),
        ("! api", Kind.NOTE, "api"),
        ("?", Kind.QUESTION, ""),
        ("?api", Kind.QUESTION, "api"),
        ("= api", Kind.DECISION, "api"),
        (".gitignore", None, ".gitignore"),
    ],
)
def test_query_splits_a_leading_sigil_from_the_words(query, kind, words):
    assert search.query(query) == search.Query(kind, words), (
        f"{query!r} should ask for kind {kind} and words {words!r}"
    )


def test_search_without_a_sigil_matches_every_kind(mixed):
    found = [r.text for r in search.search("api", mixed)]
    expected = [text for text in MIXED if text != ". fix the build"]
    assert found == expected, "words alone should match the line of any kind"


@pytest.mark.parametrize(
    "query, expected",
    [
        (".", [". document api", ". fix the build"]),
        (". api", [". document api"]),
        ("*", ["* test api manually"]),
        ("!", ["! api keys are in 1password"]),
        ("?", ["? api v2 or patch v1"]),
        ("= spring", ["= patch v1, api v2 in spring"]),
        ("! build", []),
    ],
)
def test_search_with_a_sigil_keeps_that_kind_only(mixed, query, expected):
    assert [r.text for r in search.search(query, mixed)] == expected, (
        f"{query!r} should list {expected}"
    )


def test_a_sigil_word_does_not_match_the_sigil_itself(mixed):
    assert search.search("* document", mixed) == [], "the sigil is not part of the searched line"
