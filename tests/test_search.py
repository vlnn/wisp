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
def test_rule_reads_an_at_day(token, first, last):
    assert search.rule(f"@{token}", TODAY) == (first, last), f"@{token} should span {first}..{last}"
    assert search.rule(token, TODAY) is None, f"bare {token!r} should not be a rule in a query"


@pytest.mark.parametrize(
    "token, first",
    [
        ("yesterday", TODAY - timedelta(days=1)),
        ("@yesterday", TODAY - timedelta(days=1)),
        ("fri", TODAY - timedelta(days=1)),
        ("@2026-10-03", date(2026, 10, 3)),
        ("2026-10-03", date(2026, 10, 3)),
    ],
)
def test_spoken_reads_bare_days_and_rules(token, first):
    assert search.spoken(token, TODAY) == (first, first), (
        f"{token!r} should be a day in a question to the model"
    )


@pytest.mark.parametrize(
    "token",
    [
        "api",
        "2026-13",
        "2026-10-99",
        "mondays",
        "20261003",
        "to",
        "@api",
        "@2026-13",
        "@",
        "@@today",
    ],
)
def test_rules_leave_other_words_alone(token):
    assert search.rule(token, TODAY) is None, f"{token!r} is not a rule"
    assert search.spoken(token, TODAY) is None, f"{token!r} is not a day"


@pytest.mark.parametrize(
    "token, expected",
    [
        ("@today", True),
        ("@Week", True),
        ("@2026-09", True),
        ("@2026-10-03", True),
        ("@flash", False),
        ("today", False),
        ("#week", False),
        ("@2026-13", False),
    ],
)
def test_is_rule_needs_no_date(token, expected):
    assert search.is_rule(token) is expected, (
        f"{token!r} should {'be' if expected else 'not be'} a rule"
    )


@pytest.mark.parametrize(
    "text, words, span",
    [
        ("api", "api", None),
        ("@today", "", (TODAY, TODAY)),
        ("api @today", "api", (TODAY, TODAY)),
        ("@yesterday api v1", "api v1", (TODAY - timedelta(days=1), TODAY - timedelta(days=1))),
        ("@today @yesterday", "@yesterday", (TODAY, TODAY)),
        (". @today", "", (TODAY, TODAY)),
        ("today standup", "today standup", None),
        ("talked to @Flash", "talked to @Flash", None),
    ],
)
def test_query_takes_the_first_rule_as_a_window(text, words, span):
    asked = search.query(text, TODAY)
    assert (asked.words, asked.span) == (words, span), f"{text!r} should narrow to {span}"


def test_query_without_a_day_keeps_rules_as_words():
    assert search.query("@today api") == search.Query(None, "@today api"), (
        "with no day to count from, nothing is a date"
    )


def test_a_question_reads_bare_days():
    asked = search.query("what did I do yesterday", TODAY, search.spoken)
    assert (asked.words, asked.span) == ("what did I do", (TODAY - timedelta(days=1),) * 2), (
        "a question to the model keeps its natural day words"
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
        ("@today", ["day 0"]),
        ("@yesterday", ["day 1"]),
        ("@thursday", ["day 2"]),
        ("day @today", ["day 0"]),
        ("day", ["day 0", "day 1", "day 2", "day 3"]),
        ("@2026-10", ["day 0", "day 1", "day 2", "day 3"]),
        ("@2026-09", []),
        ("today", []),
    ],
)
def test_search_within_a_window(week, text, expected):
    assert [r.text for r in search.search(text, week, TODAY)] == expected, (
        f"{text!r} should list {expected}"
    )


def test_scope_is_kind_and_window_without_the_words(week):
    asked = search.query(". @today api", TODAY)
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
    asked = search.query("api -v2 @today", TODAY)
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
        ("@today", TODAY, TODAY),
        ("@week", date(2026, 10, 5), date(2026, 10, 11)),
        ("@month", date(2026, 10, 1), date(2026, 10, 31)),
        ("@year", date(2026, 1, 1), date(2026, 12, 31)),
        ("@Week", date(2026, 10, 5), date(2026, 10, 11)),
    ],
)
def test_rule_reads_a_range(token, first, last):
    assert search.rule(token, TODAY) == (first, last), f"{token!r} should span {first}..{last}"


@pytest.mark.parametrize("token", ["week", "#week", "#month", "#year", "@weeks", "@"])
def test_a_range_needs_the_at_and_the_whole_word(token):
    assert search.rule(token, TODAY) is None, f"{token!r} is not a range"


def test_query_takes_a_range_as_the_window():
    asked = search.query("api @week", TODAY)
    assert (asked.words, asked.span) == ("api", (date(2026, 10, 5), date(2026, 10, 11))), (
        "a range word should leave the words and become the window"
    )


def logged_on(when: date) -> Record:
    moment = NOW.replace(year=when.year, month=when.month, day=when.day)
    return Record.parsed(Path(f"/log/{when}.md"), f"on {when}", moment, moment)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("@today", ["on 2026-10-10"]),
        ("@week", ["on 2026-10-10", "on 2026-10-05"]),
        ("@month", ["on 2026-10-10", "on 2026-10-05", "on 2026-10-04", "on 2026-10-01"]),
        (
            "@year",
            ["on 2026-10-10", "on 2026-10-05", "on 2026-10-04", "on 2026-10-01", "on 2026-09-30"],
        ),
    ],
)
def test_search_within_a_range(text, expected):
    days = [date(2026, 10, 10), date(2026, 10, 5), date(2026, 10, 4), date(2026, 10, 1)]
    days += [date(2026, 9, 30), date(2025, 12, 31)]
    found = search.search(text, [logged_on(day) for day in days], TODAY)
    assert [r.text for r in found] == expected, f"{text!r} should list {expected}"


@pytest.mark.parametrize(
    "text, kind, words, tags, without_tags",
    [
        ("#art api", None, "api", ("art",), ()),
        ("api #Articles", None, "api", ("articles",), ()),
        ("#a #b", None, "", ("a", "b"), ()),
        ("api -#draft", None, "api", (), ("draft",)),
        (". #work fix", Kind.TASK, "fix", ("work",), ()),
        ("# release", Kind.CHECKLIST, "release", (), ()),
        ("#", Kind.CHECKLIST, "", (), ()),
        ("C# notes #123", None, "C# notes #123", (), ()),
    ],
)
def test_query_reads_tags(text, kind, words, tags, without_tags):
    asked = search.query(text)
    assert (asked.kind, asked.words, asked.tags, asked.without_tags) == (
        kind,
        words,
        tags,
        without_tags,
    ), f"{text!r} should read as {kind}, {words!r}, tags {tags}, without {without_tags}"


@pytest.mark.parametrize(
    "tag, key",
    [("#articles", "articles"), ("#Réunion", "reunion"), ("#side-project", "side-project")],
)
def test_tag_key_folds(tag, key):
    assert search.tag_key(tag) == key, f"{tag} should be known as {key}"


TAGGED = (
    "essay on modules #articles",
    "art history notes #art-history",
    "gallery visit #arts",
    "articles to read later",
    ". write #Articles #clojure",
)


@pytest.fixture
def tagged():
    return [
        Record.parsed(
            Path(f"/log/{n}.md"), text, NOW - timedelta(minutes=n), NOW - timedelta(minutes=n)
        )
        for n, text in enumerate(TAGGED)
    ]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("#articles", ["essay on modules #articles", ". write #Articles #clojure"]),
        (
            "#art",
            [
                "essay on modules #articles",
                "art history notes #art-history",
                "gallery visit #arts",
                ". write #Articles #clojure",
            ],
        ),
        (
            "articles",
            ["essay on modules #articles", "articles to read later", ". write #Articles #clojure"],
        ),
        (
            "-#articles",
            ["art history notes #art-history", "gallery visit #arts", "articles to read later"],
        ),
        ("#articles #clojure", [". write #Articles #clojure"]),
        (". #articles", [". write #Articles #clojure"]),
        ("#articles essay", ["essay on modules #articles"]),
        ("#nothing", []),
    ],
)
def test_search_by_tag(tagged, text, expected):
    assert [r.text for r in search.search(text, tagged)] == expected, (
        f"{text!r} should list {expected}"
    )


def test_tags_combine_with_a_rule():
    old = Record.parsed(Path("/log/o.md"), "plan #work", NOW - timedelta(days=1), NOW)
    new = Record.parsed(Path("/log/n.md"), "plan #work", NOW, NOW)
    assert search.search("#work @today plan", [old, new], TODAY) == [new], (
        "a tag, a rule and words narrow together"
    )


@pytest.mark.parametrize(
    "text, expected",
    [
        ("wrote article #Articles @week -draft", "wrote article #Articles"),
        ("@today standup", "standup"),
        ("talked to @Flash", "talked to @Flash"),
        (". fix it -#later", ". fix it"),
        ("pushed --force", "pushed --force"),
        ("x-ray results @2026-10-03", "x-ray results"),
    ],
)
def test_logged_keeps_the_record_and_drops_the_query(text, expected):
    assert search.logged(text) == expected, f"logging {text!r} should write {expected!r}"
