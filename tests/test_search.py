from datetime import date, timedelta
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


TODAY = NOW.date()


@pytest.mark.parametrize(
    "token, first, last",
    [
        ("today", TODAY, TODAY),
        ("Today", TODAY, TODAY),
        ("yesterday", TODAY - timedelta(days=1), TODAY - timedelta(days=1)),
        ("saturday", TODAY, TODAY),
        ("sat", TODAY, TODAY),
        ("friday", TODAY - timedelta(days=1), TODAY - timedelta(days=1)),
        ("sunday", TODAY - timedelta(days=6), TODAY - timedelta(days=6)),
        ("2026-10-03", date(2026, 10, 3), date(2026, 10, 3)),
        ("2026-09", date(2026, 9, 1), date(2026, 9, 30)),
        ("2024-02", date(2024, 2, 1), date(2024, 2, 29)),
    ],
)
def test_days_reads_a_date_word(token, first, last):
    assert search.days(token, TODAY) == (first, last), f"{token!r} should span {first}..{last}"


@pytest.mark.parametrize("token", ["api", "2026-13", "2026-10-99", "mondays", "20261003", "to"])
def test_days_leaves_other_words_alone(token):
    assert search.days(token, TODAY) is None, f"{token!r} is not a date"


@pytest.mark.parametrize(
    "text, words, span",
    [
        ("api", "api", None),
        ("today", "", (TODAY, TODAY)),
        ("api today", "api", (TODAY, TODAY)),
        ("yesterday api v1", "api v1", (TODAY - timedelta(days=1), TODAY - timedelta(days=1))),
        ("today yesterday", "yesterday", (TODAY, TODAY)),
        (". today", "", (TODAY, TODAY)),
    ],
)
def test_query_takes_the_first_date_word_as_a_window(text, words, span):
    asked = search.query(text, TODAY)
    assert (asked.words, asked.span) == (words, span), f"{text!r} should narrow to {span}"


def test_query_without_a_day_keeps_date_words_as_words():
    assert search.query("today api") == search.Query(None, "today api"), (
        "with no day to count from, nothing is a date"
    )


@pytest.fixture
def week():
    return [
        Record.parsed(Path(f"/log/{n}.md"), f"day {n}", NOW - timedelta(days=n), NOW)
        for n in range(4)
    ]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("today", ["day 0"]),
        ("yesterday", ["day 1"]),
        ("thursday", ["day 2"]),
        ("day today", ["day 0"]),
        ("day", ["day 0", "day 1", "day 2", "day 3"]),
        ("2026-10", ["day 0", "day 1", "day 2", "day 3"]),
        ("2026-09", []),
    ],
)
def test_search_within_a_window(week, text, expected):
    assert [r.text for r in search.search(text, week, TODAY)] == expected, (
        f"{text!r} should list {expected}"
    )


def test_scope_is_kind_and_window_without_the_words(week):
    asked = search.query(". today api", TODAY)
    task = Record.parsed(Path("/log/t.md"), ". fix", NOW, NOW)
    assert search.in_scope(asked, task) is True, "a task from today is in scope"
    assert search.in_scope(asked, week[0]) is False, "a log is not, whatever its words"
    assert (
        search.in_scope(
            asked, Record.parsed(Path("/log/o.md"), ". old", NOW - timedelta(days=1), NOW)
        )
        is False
    ), "yesterday's task is not"


def test_query_reads_the_checklist_sigil():
    asked = search.query("# rel")
    assert (asked.kind, asked.words) == (Kind.CHECKLIST, "rel"), "# scopes to checklists"


def test_a_bare_checklist_sigil_scopes_to_templates():
    template = Record.parsed(Path("/log/t.md"), "# release", NOW, NOW)
    run = Record.parsed(Path("/log/r.md"), ". release", NOW, NOW)
    assert search.search("#", [run, template]) == [template], "l # lists templates only"


@pytest.mark.parametrize(
    "text, kind, words, without",
    [
        ("api -v2", None, "api", ("v2",)),
        ("-v2", None, "", ("v2",)),
        ("-v2 -patch api", None, "api", ("v2", "patch")),
        (". -build", Kind.TASK, "", ("build",)),
        ("-", None, "-", ()),
        ("--force", None, "--force", ()),
        ("x-ray", None, "x-ray", ()),
    ],
)
def test_query_takes_dashed_words_out_as_exclusions(text, kind, words, without):
    assert search.query(text) == search.Query(kind, words, None, without), (
        f"{text!r} should ask for {words!r} without {without}"
    )


def test_query_takes_a_window_and_an_exclusion_together():
    asked = search.query("api -v2 today", TODAY)
    assert (asked.words, asked.span, asked.without) == ("api", (TODAY, TODAY), ("v2",)), (
        "a day word and a dashed word should both leave the words"
    )


@pytest.mark.parametrize(
    "query, expected",
    [
        (
            "api -v2",
            ["! api keys are in 1password", "* test api manually", ". document api", "api v1"],
        ),
        ("api -v", ["! api keys are in 1password", "* test api manually", ". document api"]),
        ("-api", [". fix the build"]),
        (". -doc", [". fix the build"]),
        ("-api -fix", []),
        (
            "api -V2",
            ["! api keys are in 1password", "* test api manually", ". document api", "api v1"],
        ),
    ],
)
def test_search_leaves_out_lines_matching_a_dashed_word(mixed, query, expected):
    assert [r.text for r in search.search(query, mixed)] == expected, (
        f"{query!r} should list {expected}"
    )


def test_an_exclusion_narrows_the_scope():
    asked = search.query("-api")
    line = Record.parsed(Path("/log/a.md"), "api v1", NOW, NOW)
    assert search.in_scope(asked, line) is False, (
        "an excluded line should be out of scope, so the model never sees it either"
    )


@pytest.mark.parametrize(
    "token, first, last",
    [
        ("#today", TODAY, TODAY),
        ("#week", date(2026, 10, 5), date(2026, 10, 11)),
        ("#month", date(2026, 10, 1), date(2026, 10, 31)),
        ("#year", date(2026, 1, 1), date(2026, 12, 31)),
        ("#Week", date(2026, 10, 5), date(2026, 10, 11)),
    ],
)
def test_days_reads_a_range_word(token, first, last):
    assert search.days(token, TODAY) == (first, last), f"{token!r} should span {first}..{last}"


@pytest.mark.parametrize("token", ["week", "month", "year", "#weeks", "#api", "#"])
def test_days_needs_the_hash_and_the_whole_range_word(token):
    assert search.days(token, TODAY) is None, f"{token!r} is not a range word"


def test_query_takes_a_range_word_as_the_window():
    asked = search.query("api #week", TODAY)
    assert (asked.words, asked.span) == ("api", (date(2026, 10, 5), date(2026, 10, 11))), (
        "a range word should leave the words and become the window"
    )


def logged_on(when: date) -> Record:
    moment = NOW.replace(year=when.year, month=when.month, day=when.day)
    return Record.parsed(Path(f"/log/{when}.md"), f"on {when}", moment, moment)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("#today", ["on 2026-10-10"]),
        ("#week", ["on 2026-10-10", "on 2026-10-05"]),
        ("#month", ["on 2026-10-10", "on 2026-10-05", "on 2026-10-04", "on 2026-10-01"]),
        (
            "#year",
            ["on 2026-10-10", "on 2026-10-05", "on 2026-10-04", "on 2026-10-01", "on 2026-09-30"],
        ),
    ],
)
def test_search_within_a_range(text, expected):
    days = [date(2026, 10, 10), date(2026, 10, 5), date(2026, 10, 4), date(2026, 10, 1)]
    days += [date(2026, 9, 30), date(2025, 12, 31)]
    found = search.search(text, [logged_on(day) for day in days], TODAY)
    assert [r.text for r in found] == expected, f"{text!r} should list {expected}"
