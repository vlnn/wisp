from datetime import datetime
from pathlib import Path

import pytest

from conftest import NOW
from wisp import oracle, present
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
    return Record.parsed(Path("/log/x.md"), text, created, changed or created)


def test_task_row_marks_done_on_shift():
    row = present.record_row(a_record(". fix the build", NOW), NOW)
    assert row["title"] == ". fix the build", "the sigil stays visible in the list"
    assert row["subtitle"] == "15:00 today", "an open task shows when it was written"
    assert row["mods"]["shift"] == {
        "arg": "/log/x.md",
        "subtitle": "Finish",
        "variables": {"action": "mark"},
    }, "⇧↩ on a task should finish it, with the word the menu uses"


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
        "variables": {"action": "menu", "path": "/log/x.md"},
    }, "⇧↩ on a question opens the menu, which is the answer field, empty"
    decision = present.record_row(a_record("= ship friday", asked, NOW), NOW)
    assert decision["subtitle"] == "decided 15:00 today · yesterday 09:12", (
        "a decision shows when it was made and when the question was raised"
    )
    assert decision["mods"]["shift"]["subtitle"] == "Reopen", "⇧↩ on a decision reopens it"


@pytest.mark.parametrize("text", ["plain log", "! keys in 1password"])
def test_other_rows_still_copy_on_shift(text):
    row = present.record_row(a_record(text, NOW), NOW)
    assert row["mods"]["shift"] == {
        "arg": text,
        "subtitle": "Copy to clipboard",
        "variables": {"action": "copy"},
    }, "⇧↩ keeps copying on anything that is not a task"


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
    (ask,) = present.question_rows("today", [], NOW, oracle.Evidence([], [], []))
    assert ask["icon"] == {"path": "icons/question.png"}, "the Ask row wears the question ring"


@pytest.mark.parametrize(
    "lines, matching, subtitle",
    [
        (5, [], "↩ asks the model about 5 lines"),
        (1, [], "↩ asks the model about 1 line"),
        (2, ["api"], "↩ asks the model about 2 lines matching api"),
        (3, ["logs", "wisp"], "↩ asks the model about 3 lines matching logs, wisp"),
    ],
)
def test_ask_row_says_what_goes(lines, matching, subtitle):
    assert present.ask_row("q", lines, matching)["subtitle"] == subtitle, (
        "the row counts the lines and names the words they match"
    )


def test_unserved_row_cannot_be_actioned():
    row = present.unserved_row()
    assert row["title"] == present.NO_SERVER and row["valid"] is False, (
        "without a model the row only says how to get one"
    )


def test_every_kind_has_an_icon_file():
    for kind in Kind:
        path = Path(__file__).parent.parent / "workflow" / kind.icon
        assert path.is_file(), f"{kind} needs {path.name} in the bundle"


STEPS = "- [ ] bump version\n- [x] tag\nnotes\n- [ ] build\n"
ALL_TICKED = "- [x] bump version\n- [x] tag\n"
STARTED = datetime(2026, 10, 10, 9, 12)
FINISHED = datetime(2026, 10, 10, 14, 30)


def template(name="release checklist", body=STEPS):
    return Record.parsed(Path("/log/template.md"), f"# {name}", STARTED, STARTED, body)


def a_run(body=STEPS, created=STARTED, name="release checklist"):
    return Record.parsed(Path("/log/run.md"), f". {name}", created, created, body)


def a_finished_run(body=ALL_TICKED, created=STARTED, finished=FINISHED):
    return Record.parsed(Path("/log/done.md"), "* release checklist", created, finished, body)


@pytest.mark.parametrize(
    "record, logs, subtitle",
    [
        (template(), [], "3 steps · 09:12 today"),
        (template(body=""), [], "0 steps · 09:12 today"),
        (template(), [a_run()], "3 steps · run open since 09:12 today"),
        (template(), [a_finished_run()], "3 steps · last done 14:30 today"),
        (template(), [a_finished_run(), a_run()], "3 steps · run open since 09:12 today"),
        (a_run(), [], "1/3 · started 09:12 today"),
        (a_finished_run(), [], "done 14:30 today · 2/2 · 09:12 today"),
        (a_run(body=""), [], "09:12 today"),
    ],
)
def test_checklist_subtitles_count_steps_and_runs(record, logs, subtitle):
    row = present.record_row(record, NOW, logs)
    assert row["subtitle"] == subtitle, f"{record.text!r} should read {subtitle!r}"


def test_run_rows_still_finish_on_shift():
    row = present.record_row(a_run(), NOW)
    assert row["mods"]["shift"]["subtitle"] == "Finish", "a run is a task and finishes like one"
    assert row["icon"] == {"path": "icons/task.png"}, "a run wears the task ring"


def test_template_row_cannot_be_marked():
    row = present.record_row(template(), NOW)
    assert row["mods"]["shift"]["subtitle"] == "Copy to clipboard", "⇧↩ never finishes a template"
    assert row["icon"] == {"path": "icons/checklist.png"}, "a template wears its own icon"


def test_rows_offer_the_checklist_before_the_matches():
    offered, listed = present.rows("# rel", [template()], NOW)
    assert offered["title"] == 'Checklist "rel"', "the first row is the offer"
    assert listed["title"] == "# release checklist", "the prefix match is listed under it"


def test_checklist_offer_creates_a_missing_template():
    row = present.checklist_offer("rel", [template()], NOW)
    assert row["title"] == 'Checklist "rel"', "no exact template, so the offer is to create one"
    assert row["subtitle"] == "↩ creates it", "the subtitle says what ↩ does"
    assert row["arg"] == "# rel", "↩ passes the template's text"
    assert row["variables"] == {"action": "start"}, "start with text creates the template"
    assert row["icon"] == {"path": "icons/checklist.png"}, "the offer wears the checklist icon"


def test_checklist_offer_starts_an_exact_template():
    row = present.checklist_offer("Release Checklist", [template()], NOW)
    assert row["title"] == 'Start "release checklist"', "an exact match, case folded, starts"
    assert row["subtitle"] == "↩ starts a run · 3 steps", "the subtitle counts the steps"
    assert row["arg"] == "/log/template.md", "↩ passes the template's path"
    assert row["variables"] == {"action": "start"}, "↩ is the start action"
    assert row["mods"]["cmd"] == {
        "arg": "/log/template.md",
        "subtitle": "Start a fresh run",
        "variables": {"action": "start", "fresh": "1"},
    }, "⌘↩ starts a run whatever is open"


def test_checklist_offer_continues_an_open_run():
    row = present.checklist_offer("release checklist", [template(), a_run()], NOW)
    assert row["title"] == 'Continue "release checklist"', "an open run is continued"
    assert row["subtitle"] == "1/3 since 09:12 today", "the subtitle shows the run's progress"
    assert row["arg"] == "", "the steps open with nothing typed"
    assert row["variables"] == {"action": "items", "path": "/log/run.md"}, "↩ opens the run's steps"
    assert row["mods"]["cmd"]["variables"] == {"action": "start", "fresh": "1"}, (
        "⌘↩ starts a fresh run anyway"
    )
    assert row["mods"]["cmd"]["arg"] == "/log/template.md", "the fresh run is from the template"


@pytest.mark.parametrize(
    "record, logs, titles",
    [
        (template(), [], ["Start", "Steps", "Open", "Rename", "Copy", "Trash"]),
        (template(), [a_run()], ["Continue", "Steps", "Open", "Rename", "Copy", "Trash"]),
        (a_run(), [], ["Steps", "Finish", "Open", "Rename", "Copy", "Trash"]),
        (a_finished_run(), [], ["Steps", "Reopen", "Open", "Rename", "Copy", "Trash"]),
    ],
)
def test_checklist_menus_lead_with_the_steps(record, logs, titles):
    menu = present.menu_rows(record, "", logs)
    assert [row["title"] for row in menu] == titles, f"{record.text!r} should offer {titles}"


def test_template_menu_start_and_steps_carry_their_actions():
    by_title = {row["title"]: row for row in present.menu_rows(template(), "", [a_run()])}
    assert by_title["Continue"]["variables"] == {"action": "items", "path": "/log/run.md"}, (
        "Continue opens the open run's steps"
    )
    assert by_title["Steps"] == {
        "title": "Steps",
        "subtitle": "# release checklist",
        "arg": "",
        "variables": {"action": "items", "path": "/log/template.md"},
    }, "Steps opens the template's own steps, to edit them"
    (start,) = [row for row in present.menu_rows(template(), "", []) if row["title"] == "Start"]
    assert (start["arg"], start["variables"]) == ("/log/template.md", {"action": "start"}), (
        "Start is the start action on the template"
    )


def test_item_rows_show_every_step_with_its_box():
    rows = present.item_rows(a_run(), "")
    assert [row["title"] for row in rows] == ["☐ bump version", "notes", "☐ build", "☑ tag"], (
        "one row per body line, boxes drawn, ticked ones last"
    )
    assert [row.get("valid", True) for row in rows] == [True, False, True, True], (
        "a line without a box cannot be ticked"
    )
    assert [row.get("arg") for row in rows] == ["1", None, "4", "2"], "↩ passes the line number"
    assert rows[0]["subtitle"] == "↩ ticks" and rows[3]["subtitle"] == "↩ unticks", (
        "the subtitle says which way the box flips"
    )
    assert rows[0]["variables"] == {"action": "tick", "path": "/log/run.md"}, (
        "a step row is the tick action on the file"
    )


def test_item_rows_narrow_as_you_type():
    rows = present.item_rows(a_run(), "bu")
    assert [row["title"] for row in rows] == ["☐ bump version", "☐ build"], "typed words narrow"


def test_item_rows_offer_to_add_what_matches_nothing():
    (add,) = present.item_rows(a_run(), "publish notes")
    assert add["title"] == 'Add "publish notes"', "an unmatched text is a new step"
    assert add["subtitle"] == "↩ adds a step", "the subtitle says so"
    assert add["arg"] == "publish notes", "↩ passes the text"
    assert add["variables"] == {"action": "add", "path": "/log/run.md"}, "the row adds to the file"


def test_item_rows_of_an_empty_checklist_ask_for_a_step():
    (hint,) = present.item_rows(template(body=""), "")
    assert hint["title"] == 'Type a step to add to "release checklist"', "nothing to tick yet"
    assert hint["valid"] is False, "the hint cannot be actioned"


def test_item_rows_finish_a_run_once_every_box_is_ticked():
    (finish, *steps) = present.item_rows(a_run(body=ALL_TICKED), "")
    assert finish["title"] == "Finish", "the last tick leaves Finish one ↩ away"
    assert finish["arg"] == "/log/run.md" and finish["variables"] == {"action": "mark"}, (
        "Finish is the mark action on the run"
    )
    assert len(steps) == 2, "the steps stay listed under it"


@pytest.mark.parametrize(
    "record, typed",
    [
        (template(body=ALL_TICKED), ""),
        (a_run(body=ALL_TICKED), "bump"),
        (a_run(body=STEPS), ""),
        (a_finished_run(), ""),
    ],
)
def test_item_rows_do_not_finish_otherwise(record, typed):
    titles = [row["title"] for row in present.item_rows(record, typed)]
    assert "Finish" not in titles, "only an open run with every box ticked and nothing typed"


def test_item_rows_put_the_next_step_first():
    rows = present.item_rows(a_run(body="- [x] bump version\n- [ ] tag\nnotes\n- [x] build\n"), "")
    assert [row["title"] for row in rows] == ["☐ tag", "notes", "☑ bump version", "☑ build"], (
        "ticked steps sink to the bottom, so ↩ lands on the next step to do"
    )


@pytest.mark.parametrize(
    "record, title, arg",
    [
        (template(body=ALL_TICKED), 'Start "release checklist"', "/log/template.md"),
        (template(), 'Start "release checklist"', "/log/template.md"),
        (a_finished_run(), 'Run "release checklist" again', "/log/done.md"),
    ],
)
def test_item_rows_lead_to_a_fresh_run(record, title, arg):
    (lead, *steps) = present.item_rows(record, "")
    assert lead["title"] == title, "a template or a finished run starts a run from its steps"
    assert lead["subtitle"] == "↩ starts a run with every box cleared", "the subtitle says so"
    assert (lead["arg"], lead["variables"]) == (arg, {"action": "start"}), (
        "the row is the start action on this file"
    )
    assert len(steps) == len(present.body_rows(record)), "the steps stay listed under it"


def test_item_rows_lead_row_steps_aside_when_typing():
    titles = [row["title"] for row in present.item_rows(template(), "bu")]
    assert titles == ["☐ bump version", "☐ build"], "typing narrows to steps only"
