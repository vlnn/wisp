from datetime import datetime
from pathlib import Path

import pytest

from conftest import NOW
from wisp import present
from wisp.records import Kind, Record


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
        ("? ship friday", 'Question "ship friday"', "? ship friday"),
        ("?ship friday", 'Question "ship friday"', "? ship friday"),
        ("= ship friday", 'Decision "ship friday"', "= ship friday"),
    ],
)
def test_keep_row_names_the_kind(text, title, arg):
    row = present.keep_row(text)
    assert row["title"] == title, f"{text!r} should be offered as {title!r}"
    assert row["arg"] == arg, f"↩ should keep {arg!r}"


@pytest.mark.parametrize("query", [".", "*", "!", "?", "=", "  .  "])
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


def test_question_row_decides_on_shift_and_a_decision_reopens():
    asked = datetime(2026, 10, 9, 9, 12)
    question = present.record_row(a_record("? ship friday", asked), NOW)
    assert question["mods"]["shift"] == {
        "arg": "",
        "subtitle": "Decide",
        "variables": {"action": "decide", "path": "/log/x.md"},
    }, "⇧↩ on a question opens the decide field for the file, empty"
    decision = present.record_row(a_record("= ship friday", asked, NOW), NOW)
    assert decision["subtitle"] == "decided 15:00 today · yesterday 09:12", (
        "a decision shows when it was made and when the question was raised"
    )
    assert decision["mods"]["shift"]["subtitle"] == "Reopen", "⇧↩ on a decision reopens it"


@pytest.mark.parametrize("text", ["plain log", "! keys in 1password"])
def test_other_rows_still_copy_on_shift(text):
    row = present.record_row(a_record(text, NOW), NOW)
    assert row["mods"]["shift"] == {"arg": text, "subtitle": "Copy to clipboard"}, (
        "⇧↩ keeps copying on anything that is not a task"
    )


@pytest.mark.parametrize(
    "text, titles",
    [
        ("plain log", ["Open", "Rename", "Copy", "Trash"]),
        ("! keys in 1password", ["Open", "Rename", "Copy", "Trash"]),
        (". fix the build", ["Finish", "Open", "Rename", "Copy", "Trash"]),
        ("* fix the build", ["Reopen", "Open", "Rename", "Copy", "Trash"]),
        (
            "? ship friday",
            ['Type the resolution for "ship friday"', "Open", "Rename", "Copy", "Trash"],
        ),
        ("= ship friday", ["Reopen", "Open", "Rename", "Copy", "Trash"]),
    ],
)
def test_menu_lists_what_the_kind_can_do(text, titles):
    menu = present.menu_rows(a_record(text, NOW), "")
    assert [row["title"] for row in menu] == titles, f"{text!r} should offer {titles}"


def test_question_menu_takes_the_answer_as_you_type():
    (decide, *rest) = present.menu_rows(a_record("? ship friday", NOW), "yes, at noon")
    assert decide["title"] == 'Decide "ship friday | yes, at noon"', "the first row shows the line"
    assert decide["arg"] == "yes, at noon", "↩ passes the answer on"
    assert decide["variables"] == {"action": "decide", "path": "/log/x.md"}, (
        "the row is the decide action on the file"
    )
    assert [row["title"] for row in rest] == ["Open", "Rename", "Copy", "Trash"], (
        "typing the answer never hides the other actions"
    )


def test_question_menu_waits_for_an_answer():
    (decide, *_) = present.menu_rows(a_record("? ship friday", NOW), "")
    assert decide["title"] == 'Type the resolution for "ship friday"', "the row names the question"
    assert decide["valid"] is False, "an empty answer cannot settle the question"


@pytest.mark.parametrize(
    "answer, title, valid",
    [
        ("", 'Type the resolution for "why is the sky green"', False),
        ("  ", 'Type the resolution for "why is the sky green"', False),
        ("it is blue", 'Decide "why is the sky green | it is blue"', True),
    ],
)
def test_decide_row_shows_what_will_be_written(answer, title, valid):
    row = present.decide_row(a_record("? why is the sky green", NOW), answer)
    assert row["title"] == title, f"{answer!r} should show {title!r}"
    assert row.get("valid", True) is valid, "only a non-empty resolution can be accepted"
    if valid:
        assert row["arg"] == "it is blue", "↩ passes the resolution on"
    assert row["variables"] == {"action": "decide", "path": "/log/x.md"}, (
        "the row names the file it settles, whichever way it was reached"
    )


def test_menu_rows_carry_the_same_actions_as_the_keys():
    record = a_record(". fix the build", NOW)
    by_title = {row["title"]: row for row in present.menu_rows(record, "")}
    assert by_title["Finish"]["arg"] == "/log/x.md", "finish acts on the file"
    assert by_title["Finish"]["variables"] == {"action": "mark"}, "finish is the mark action"
    assert by_title["Open"]["variables"] == {"action": "open"}, "open is the open action"
    assert by_title["Rename"]["arg"] == ". fix the build", "rename prefills the text"
    assert by_title["Rename"]["variables"] == {"action": "rename", "path": "/log/x.md"}, (
        "rename carries the path along"
    )
    assert by_title["Copy"]["arg"] == ". fix the build", "copy passes the text"
    assert by_title["Copy"]["variables"] == {"action": "copy"}, "copy is its own action"
    assert by_title["Trash"]["variables"] == {"action": "trash"}, "trash is the trash action"


def test_menu_rows_say_which_record_they_act_on():
    (row, *_) = present.menu_rows(a_record("plain log", NOW), "")
    assert row["subtitle"] == "plain log", "the subtitle names the record"


def test_menu_narrows_as_you_type():
    menu = present.menu_rows(a_record(". fix the build", NOW), "re")
    assert [row["title"] for row in menu] == ["Rename"], "typed words filter the menu by title"


def test_record_row_opens_the_menu_on_enter():
    row = present.record_row(a_record("plain log", NOW), NOW)
    assert row["arg"] == "", "the menu should open with an empty query"
    assert row["variables"] == {"action": "menu", "path": "/log/x.md"}, (
        "↩ should open the menu for the file, the path travelling as a variable"
    )
    assert row["quicklookurl"] == "/log/x.md", "Quick Look still shows the file"
    assert "ctrl" not in row["mods"], "⌃↩ is Alfred's own key and is left alone"


@pytest.mark.parametrize(
    "text, icon",
    [
        ("plain log", "icons/log.png"),
        (". fix the build", "icons/task.png"),
        ("* fix the build", "icons/done.png"),
        ("! keys in 1password", "icons/note.png"),
        ("? ship friday", "icons/question.png"),
        ("= ship friday", "icons/decision.png"),
    ],
)
def test_rows_carry_the_icon_of_their_kind(text, icon):
    row = present.record_row(a_record(text, NOW), NOW)
    assert row["icon"] == {"path": icon}, f"{text!r} should show {icon}"
    assert present.keep_row(text)["icon"] == {"path": icon}, "the offer row shows the kind too"


def test_ask_row_is_an_open_question():
    (ask,) = present.question_rows("today", [], NOW, 5, served=True)
    assert ask["icon"] == {"path": "icons/question.png"}, "the Ask row wears the question ring"


def test_every_kind_has_an_icon_file():
    for kind in Kind:
        path = Path(__file__).parent.parent / "workflow" / present.ICONS[kind]
        assert path.is_file(), f"{kind} needs {path.name} in the bundle"
