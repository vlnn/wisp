from datetime import datetime
from pathlib import Path

import pytest

from conftest import NOW
from wisp import present
from wisp.records import Record


@pytest.mark.parametrize(
    "created, expected",
    [
        (datetime(2026, 10, 10, 14, 2), "14:02 today"),
        (datetime(2026, 10, 10, 0, 0), "00:00 today"),
        (datetime(2026, 10, 9, 16, 0), "yesterday 16:00"),
        (datetime(2026, 10, 8, 9, 5), "Thu 8 Oct 09:05"),
        (datetime(2026, 1, 1, 9, 5), "Thu 1 Jan 09:05"),
        (datetime(2025, 12, 31, 23, 59), "31 Dec 2025 23:59"),
        (datetime(2026, 10, 11, 1, 0), "11 Oct 2026 01:00"),
    ],
)
def test_when(created, expected):
    assert present.when(created, NOW) == expected, (
        f"{created} seen at {NOW} should read {expected!r}"
    )


def test_no_server_names_both_ways_to_get_one():
    assert present.NO_SERVER == (
        "Set Model server or turn on Apple Intelligence in the workflow configuration"
    ), "the hint covers the URL field and the checkbox"


@pytest.mark.parametrize(
    "text, title, arg",
    [
        ("api", 'Log "api"', "api"),
        (". fix the build", 'Task "fix the build"', ". fix the build"),
        (".   fix the build", 'Task "fix the build"', ". fix the build"),
        ("! keys in 1password", 'Note "keys in 1password"', "! keys in 1password"),
        ("* did it already", 'Done "did it already"', "* did it already"),
    ],
)
def test_keep_row_names_the_kind(text, title, arg):
    row = present.keep_row(text)
    assert row["title"] == title, f"{text!r} should be offered as {title!r}"
    assert row["arg"] == arg, f"↩ should keep {arg!r}"


@pytest.mark.parametrize("query", [".", "*", "!", "  .  "])
def test_a_bare_sigil_only_filters(query):
    assert present.rows(query, [], NOW) == [], f"{query!r} has nothing to keep"


def a_record(text, created, changed=None):
    return Record(Path("/log/x.md"), text, created, changed or created)


def test_task_row_marks_done_on_shift():
    row = present.record_row(a_record(". fix the build", NOW), NOW)
    assert row["title"] == ". fix the build", "the sigil stays visible in the list"
    assert row["subtitle"] == "15:00 today", "an open task shows when it was written"
    assert row["mods"]["shift"] == {
        "arg": "/log/x.md",
        "subtitle": "Mark done",
        "variables": {"action": "mark"},
    }, "⇧↩ on a task should mark it done"


def test_done_row_shows_both_times_and_reopens_on_shift():
    opened = datetime(2026, 10, 9, 9, 12)
    row = present.record_row(a_record("* fix the build", opened, NOW), NOW)
    assert row["subtitle"] == "done 15:00 today · yesterday 09:12", (
        "a done task shows when it was done and when it was written"
    )
    assert row["mods"]["shift"]["subtitle"] == "Reopen", "⇧↩ on a done task reopens it"
    assert row["mods"]["shift"]["variables"] == {"action": "mark"}, "the same action flips back"


@pytest.mark.parametrize("text", ["plain log", "! keys in 1password"])
def test_other_rows_still_copy_on_shift(text):
    row = present.record_row(a_record(text, NOW), NOW)
    assert row["mods"]["shift"] == {"arg": text, "subtitle": "Copy to clipboard"}, (
        "⇧↩ keeps copying on anything that is not a task"
    )
