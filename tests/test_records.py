from datetime import datetime, timedelta
from pathlib import Path

import pytest

from conftest import NOW, names
from wisp import records


@pytest.mark.parametrize(
    "text, expected",
    [
        ("making API v1", "making-api-v1"),
        ("reading fucking docs again", "reading-fucking-docs-again"),
        ("  meeting with L  ", "meeting-with-l"),
        ("get -R /remote/dir /local/dst", "get-r-remote-dir-local-dst"),
        ("читаю доки", "читаю-доки"),
        ("!!!", "note"),
        ("x" * 100, "x" * 60),
    ],
)
def test_slug(text, expected):
    assert records.slug(text) == expected, f"slug of {text!r} should be {expected!r}"


def test_keep_writes_the_text_as_a_markdown_file(folder):
    path = records.keep(folder, "reading docs")
    assert path.name == "reading-docs.md", "file should be named after the text"
    assert path.read_text() == "reading docs\n", "file should hold the text and nothing else"


def test_keep_creates_the_folder(folder):
    records.keep(folder, "first")
    assert folder.is_dir(), "a missing log folder should be created on first keep"


def test_keep_numbers_colliding_names(folder):
    for _ in range(3):
        records.keep(folder, "reading docs")
    assert names(folder) == ["reading-docs-2.md", "reading-docs-3.md", "reading-docs.md"], (
        "same text kept thrice should give three files with numbered suffixes"
    )


def test_read_folder_lists_newest_first(folder, sample, clock):
    texts = [r.text for r in records.read_folder(folder, clock)]
    assert texts == [
        "meeting with L",
        "reading docs",
        "autotests",
        "testing api manually",
        "making API v1",
    ], "records should be sorted by creation time, newest first"


def test_read_folder_uses_the_first_non_empty_line(folder, clock, stamps):
    path = folder / "note.md"
    folder.mkdir()
    path.write_text("\n\n  the real line  \nmore\n")
    stamps[path.name] = NOW
    (record,) = records.read_folder(folder, clock)
    assert record.text == "the real line", "text should be the first non-empty line, stripped"


def test_read_folder_ignores_other_files(folder, clock, stamps):
    folder.mkdir()
    (folder / "keep.md").write_text("kept\n")
    (folder / ".hidden.md").write_text("hidden\n")
    (folder / "notes.txt").write_text("text\n")
    (folder / "sub").mkdir()
    stamps["keep.md"] = NOW
    texts = [r.text for r in records.read_folder(folder, clock)]
    assert texts == ["kept"], "only visible .md files should become records"


def test_read_folder_of_a_missing_folder_is_empty(folder, clock):
    assert records.read_folder(folder, clock) == [], "a missing folder has no records"


def test_rename_in_place_when_the_slug_stays(folder):
    path = records.keep(folder, "reading docs")
    renamed = records.rename(path, "Reading Docs")
    assert renamed == path, "a text change that keeps the slug should keep the file"
    assert path.read_text() == "Reading Docs\n", "file should hold the new text"


def test_rename_moves_the_file_when_the_slug_changes(folder):
    path = records.keep(folder, "reading docs")
    renamed = records.rename(path, "reading Apache docs")
    assert renamed.name == "reading-apache-docs.md", "file should follow the new text"
    assert not path.exists(), "old file should be gone"
    assert renamed.read_text() == "reading Apache docs\n", "new file should hold the new text"


def test_rename_keeps_the_inode(folder):
    path = records.keep(folder, "reading docs")
    before = path.stat().st_ino
    renamed = records.rename(path, "reading Apache docs")
    assert renamed.stat().st_ino == before, (
        "rename should move the same file so the filesystem creation time survives"
    )


def test_rename_avoids_an_existing_name(folder):
    records.keep(folder, "reading Apache docs")
    path = records.keep(folder, "reading docs")
    renamed = records.rename(path, "reading Apache docs")
    assert renamed.name == "reading-apache-docs-2.md", "rename should not overwrite another record"


@pytest.mark.parametrize(
    "text, kind, line",
    [
        ("some text", records.Kind.LOG, "some text"),
        (". another task", records.Kind.TASK, "another task"),
        ("* another task", records.Kind.DONE, "another task"),
        ("! remember this", records.Kind.NOTE, "remember this"),
        ("? postgres or sqlite", records.Kind.QUESTION, "postgres or sqlite"),
        ("= postgres, concurrent writers", records.Kind.DECISION, "postgres, concurrent writers"),
        (".   spaced out", records.Kind.TASK, "spaced out"),
        (".", records.Kind.TASK, ""),
        ("?will it work", records.Kind.QUESTION, "will it work"),
        ("!important", records.Kind.NOTE, "important"),
        ("=42", records.Kind.DECISION, "42"),
        (".gitignore moved", records.Kind.LOG, ".gitignore moved"),
        ("*args again", records.Kind.LOG, "*args again"),
        ("...", records.Kind.LOG, "..."),
        ("", records.Kind.LOG, ""),
    ],
)
def test_parse_reads_a_leading_sigil(text, kind, line):
    assert records.parse(text) == (kind, line), f"{text!r} should parse as {kind} {line!r}"


@pytest.mark.parametrize(
    "kind, line, expected",
    [
        (records.Kind.LOG, "some text", "some text"),
        (records.Kind.TASK, "another task", ". another task"),
        (records.Kind.DONE, "another task", "* another task"),
        (records.Kind.NOTE, "remember this", "! remember this"),
        (records.Kind.QUESTION, "why", "? why"),
        (records.Kind.DECISION, "because", "= because"),
    ],
)
def test_compose_puts_the_sigil_back(kind, line, expected):
    assert records.compose(kind, line) == expected, f"{kind} {line!r} should become {expected!r}"


def test_keep_normalises_the_sigil_spacing(folder):
    path = records.keep(folder, ".   fix the build")
    assert path.name == "fix-the-build.md", "the sigil should not reach the file name"
    assert path.read_text() == ". fix the build\n", "file should hold sigil, one space, line"


def test_record_knows_its_kind_and_line(folder, clock, stamps):
    path = records.keep(folder, ". fix the build")
    stamps[path.name] = NOW
    (record,) = records.read_folder(folder, clock)
    assert record.kind is records.Kind.TASK, "a line starting with '. ' is an open task"
    assert record.line == "fix the build", "line should be the text without the sigil"
    assert record.text == ". fix the build", "text should be the whole first line"


def test_read_folder_reads_when_a_record_changed(folder, clock, stamps, touched):
    path = records.keep(folder, "* fix the build")
    stamps[path.name] = NOW - timedelta(hours=3)
    touched[path.name] = NOW
    (record,) = records.read_folder(folder, clock)
    assert record.changed == NOW, "changed should come from the injected callable"


def test_record_text_is_the_line_in_its_normal_spelling():
    record = records.Record(Path("/log/x.md"), records.Kind.QUESTION, "why", NOW, NOW)
    assert record.text == "? why", "text is composed from kind and line"


def test_record_parsed_reads_a_first_line():
    record = records.Record.parsed(Path("/log/x.md"), "?why", NOW, NOW)
    assert (record.kind, record.line, record.text) == (records.Kind.QUESTION, "why", "? why"), (
        "a tight sigil is read and shown with its space"
    )


def test_file_stamps_read_birth_and_modification(mocker):
    stat = mocker.Mock(st_birthtime=1_700_000_000.0, st_mtime=1_700_000_600.0)
    mocker.patch.object(Path, "stat", return_value=stat)
    created, changed = records.file_stamps(Path("/log/x.md"))
    assert (created, changed) == (
        datetime.fromtimestamp(1_700_000_000),
        datetime.fromtimestamp(1_700_000_600),
    ), "created is the birth time, changed the modification time"


def test_file_stamps_fall_back_to_modification_time(mocker):
    stat = mocker.Mock(spec=["st_mtime"], st_mtime=1_700_000_600.0)
    mocker.patch.object(Path, "stat", return_value=stat)
    created, changed = records.file_stamps(Path("/log/x.md"))
    assert created == changed == datetime.fromtimestamp(1_700_000_600), (
        "without a birth time, a file is as old as its last change"
    )


@pytest.mark.parametrize(
    "before, after",
    [
        (". fix the build", "* fix the build"),
        ("* fix the build", ". fix the build"),
        ("= why is the sky green | it is blue", "? why is the sky green | it is blue"),
    ],
)
def test_mark_flips_a_task_between_open_and_done(folder, before, after):
    path = records.keep(folder, before)
    marked = records.mark(path)
    assert marked == after, "mark hands back the line it wrote"
    assert path.read_text() == f"{after}\n", f"{before!r} marked should read {after!r}"


@pytest.mark.parametrize("text", ["plain log", "! remember this", "? why is the sky green"])
def test_mark_leaves_other_kinds_alone(folder, text):
    path = records.keep(folder, text)
    assert records.mark(path) == text, "an untouched line comes back as it is"
    assert path.read_text() == f"{text}\n", "a question is settled by decide, not by a flip"


@pytest.mark.parametrize(
    "before, answer, after",
    [
        ("? why is the sky green", "it is blue", "= why is the sky green | it is blue"),
        ("? why is the sky green", "  it is blue  ", "= why is the sky green | it is blue"),
        (
            "= postgres or sqlite | postgres",
            "sqlite after all",
            "= postgres or sqlite | postgres | sqlite after all",
        ),
    ],
)
def test_decide_appends_the_resolution_and_settles_the_question(folder, before, answer, after):
    path = records.keep(folder, before)
    decided = records.decide(path, answer)
    assert decided == after, "decide hands back the line it wrote"
    assert path.read_text() == f"{after}\n", f"{before!r} decided {answer!r} should read {after!r}"


@pytest.mark.parametrize("text", ["plain log", ". fix the build", "! remember this"])
def test_decide_leaves_other_kinds_alone(folder, text):
    path = records.keep(folder, text)
    assert records.decide(path, "whatever") == text, "an untouched line comes back as it is"
    assert path.read_text() == f"{text}\n", "only questions take a resolution"


def test_mark_keeps_the_body(folder):
    path = records.keep(folder, ". fix the build")
    path.write_text(". fix the build\n\nsee the CI log\n")
    records.mark(path)
    assert path.read_text() == "* fix the build\n\nsee the CI log\n", "mark touches line one only"


@pytest.mark.parametrize("verb", [records.keep, records.rename])
@pytest.mark.parametrize("text", ["", "   ", ".", "! ", "="])
def test_keep_and_rename_refuse_a_blank_line(folder, verb, text):
    target = records.keep(folder, "x") if verb is records.rename else folder
    with pytest.raises(records.Blank):
        verb(target, text)


def test_decide_refuses_a_blank_resolution(folder):
    path = records.keep(folder, "? why")
    with pytest.raises(records.Blank):
        records.decide(path, "  ")
    assert path.read_text() == "? why\n", "the question stays open"


@pytest.mark.parametrize(
    "kind, sigil, offer, tag, icon",
    [
        (records.Kind.LOG, "", "Log", "", "icons/log.png"),
        (records.Kind.TASK, ".", "Task", "TODO", "icons/task.png"),
        (records.Kind.DONE, "*", "Done", "DONE", "icons/done.png"),
        (records.Kind.NOTE, "!", "Note", "NOTE", "icons/note.png"),
        (records.Kind.QUESTION, "?", "Question", "QUESTION", "icons/question.png"),
        (records.Kind.DECISION, "=", "Decision", "DECIDED", "icons/decision.png"),
    ],
)
def test_a_kind_knows_its_words(kind, sigil, offer, tag, icon):
    assert (kind.sigil, kind.offer, kind.tag, kind.icon) == (sigil, offer, tag, icon), (
        f"{kind} should carry its sigil, offer word, model tag and icon"
    )


def test_settled_kinds_are_the_closed_ends_of_the_state_machine():
    assert records.SETTLED == {records.Kind.DONE, records.Kind.DECISION}, (
        "done tasks and decisions are what mark reopens"
    )


def test_keep_never_overwrites_a_file_that_appears_in_between(folder, mocker):
    folder.mkdir()
    taken = folder / "reading-docs.md"
    taken.write_text("someone else\n")
    mocker.patch.object(Path, "exists", return_value=False)
    path = records.keep(folder, "reading docs")
    assert path.name == "reading-docs-2.md" and taken.read_text() == "someone else\n", (
        "a name that is taken by the time keep writes is skipped, not overwritten"
    )


TEMPLATE = "# release checklist\n- [ ] bump version\n- [x] tag\n\nnotes between\n* [X] build\n"


def a_checklist(folder, text=TEMPLATE):
    folder.mkdir(exist_ok=True)
    path = folder / "release-checklist.md"
    path.write_text(text)
    return path


@pytest.mark.parametrize(
    "text, kind, line",
    [
        ("# release", records.Kind.CHECKLIST, "release"),
        ("#", records.Kind.CHECKLIST, ""),
        ("#api", records.Kind.LOG, "#api"),
        ("#   spaced", records.Kind.CHECKLIST, "spaced"),
    ],
)
def test_parse_reads_the_checklist_sigil_only_with_a_space(text, kind, line):
    assert records.parse(text) == (kind, line), f"{text!r} should parse as {kind} {line!r}"


def test_normalise_spaces_the_checklist_sigil():
    assert records.normalise("#   release") == "# release", "one space follows the sigil"


def test_checklist_kind_knows_its_words():
    kind = records.Kind.CHECKLIST
    assert (kind.sigil, kind.offer, kind.tag, kind.icon) == (
        "#",
        "Checklist",
        "CHECKLIST",
        "icons/checklist.png",
    ), "a checklist carries its sigil, offer word, model tag and icon"


def test_checklist_slug_ignores_the_sigil(folder):
    path = records.keep(folder, "# release checklist")
    assert path.name == "release-checklist.md", "the sigil should not reach the file name"


def test_read_record_keeps_the_body(folder, clock, stamps):
    path = a_checklist(folder)
    stamps[path.name] = NOW
    record = records.read_record(path, clock)
    assert record.line == "release checklist", "the line is still the first line only"
    assert record.body == TEMPLATE.split("\n", 1)[1], "the body is everything after the first line"


def test_parsed_defaults_to_an_empty_body():
    record = records.Record.parsed(Path("/log/x.md"), "# release", NOW, NOW)
    assert record.body == "", "a record read from a line alone has no body"


def test_first_line_still_ignores_the_body():
    assert records.first_line(TEMPLATE) == "# release checklist", "first_line is the line"


def test_items_number_the_box_lines(folder, clock, stamps):
    path = a_checklist(folder)
    stamps[path.name] = NOW
    record = records.read_record(path, clock)
    assert records.items(record) == [
        records.Item(1, "bump version", False),
        records.Item(2, "tag", True),
        records.Item(5, "build", True),
    ], "items are the box lines, numbered by body line, ticked by their mark"


@pytest.mark.parametrize(
    "body, expected",
    [
        ("", (0, 0)),
        ("- [ ] a\n- [ ] b\n", (0, 2)),
        ("- [x] a\n- [ ] b\n", (1, 2)),
        ("  - [X] a\n* [x] b\nplain\n", (2, 2)),
    ],
)
def test_progress_counts_ticked_over_total(body, expected):
    record = records.Record(Path("/log/x.md"), records.Kind.TASK, "r", NOW, NOW, body)
    assert records.progress(record) == expected, f"{body!r} should progress to {expected}"


def a_record(text, created, body="", name="x.md"):
    return records.Record.parsed(Path("/log") / name, text, created, created, body)


def test_runs_are_the_tasks_and_done_tasks_with_the_template_line():
    template = a_record("# release", NOW)
    older = a_record(". release", NOW - timedelta(days=2), name="release-2.md")
    newer = a_record("* release", NOW - timedelta(days=1), name="release-3.md")
    logs = [
        older,
        a_record("release", NOW),
        a_record(". Release", NOW),
        a_record(". release notes", NOW),
        newer,
        template,
    ]
    assert records.runs(template, logs) == [newer, older], (
        "runs share the exact line, are tasks or done tasks, and come newest first"
    )


def test_open_run_is_the_newest_open_task_with_the_line():
    template = a_record("# release", NOW)
    done = a_record("* release", NOW - timedelta(days=1))
    assert records.open_run(template, [done, template]) is None, "a finished run is not open"
    open_one = a_record(". release", NOW - timedelta(hours=1))
    assert records.open_run(template, [done, open_one]) is open_one, "an open task is the run"


def test_start_copies_the_body_with_boxes_cleared(folder, clock, stamps):
    template_path = a_checklist(folder)
    stamps[template_path.name] = NOW
    run = records.start(folder, records.read_record(template_path, clock))
    assert run.name == "release-checklist-2.md", "a run takes the next free name"
    assert run.read_text() == (
        ". release checklist\n- [ ] bump version\n- [ ] tag\n\nnotes between\n* [ ] build\n"
    ), "a run is a task with the template's body and every box cleared"
    assert template_path.read_text() == TEMPLATE, "the template is untouched"


@pytest.mark.parametrize(
    "number, after",
    [
        (1, "# release checklist\n- [x] bump version\n- [x] tag\n\nnotes between\n* [X] build\n"),
        (2, "# release checklist\n- [ ] bump version\n- [ ] tag\n\nnotes between\n* [X] build\n"),
        (5, "# release checklist\n- [ ] bump version\n- [x] tag\n\nnotes between\n* [ ] build\n"),
    ],
)
def test_tick_flips_one_box_and_nothing_else(folder, number, after):
    path = a_checklist(folder)
    line = records.tick(path, number)
    assert path.read_text() == after, f"ticking {number} should only flip that box"
    assert line == after.splitlines()[number], "tick hands back the line it wrote"


@pytest.mark.parametrize("number", [0, 3, 4, 6, -1])
def test_tick_refuses_a_line_that_is_not_a_box(folder, number):
    path = a_checklist(folder)
    with pytest.raises(records.NoSuchItem):
        records.tick(path, number)
    assert path.read_text() == TEMPLATE, "a refused tick changes nothing"


def test_no_such_item_is_a_value_error():
    assert issubclass(records.NoSuchItem, ValueError), "like Blank, it is a bad argument"


@pytest.mark.parametrize(
    "before, after",
    [
        (TEMPLATE, TEMPLATE + "- [ ] publish\n"),
        ("# empty\n", "# empty\n- [ ] publish\n"),
        ("# no newline", "# no newline\n- [ ] publish\n"),
    ],
)
def test_add_appends_one_cleared_box(folder, before, after):
    path = a_checklist(folder, before)
    line = records.add(path, "  publish  ")
    assert path.read_text() == after, "add appends a box line and keeps the rest"
    assert line == "- [ ] publish", "add hands back the line it wrote"


def test_add_refuses_blank_text(folder):
    path = a_checklist(folder)
    with pytest.raises(records.Blank):
        records.add(path, "  ")


def test_mark_leaves_a_template_alone(folder):
    path = a_checklist(folder)
    assert records.mark(path) == "# release checklist", "a template is never finished"
    assert path.read_text() == TEMPLATE, "mark on a template is a no-op"


@pytest.mark.parametrize(
    "text, body, expected",
    [
        (". plain", "", []),
        (". run", "- [ ] a\n", ["checklist"]),
        ("# release", "", []),
        ("* run", "- [x] a\n", ["checklist"]),
    ],
)
def test_tags_say_when_a_task_is_a_run(text, body, expected):
    record = a_record(text, NOW, body)
    assert records.tags(record) == expected, f"{text!r} with {body!r} should tag {expected}"
