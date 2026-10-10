import json

import pytest

from conftest import NOW, names
from wisp import cli


@pytest.fixture
def env(folder):
    return {"log_folder": str(folder)}


@pytest.fixture
def run(env, created, capsys):
    def go(*argv):
        code = cli.run(list(argv), env, now=NOW, created=created)
        return code, capsys.readouterr().out

    return go


def rows(out):
    return json.loads(out)["items"]


def titles(out):
    return [row["title"] for row in rows(out)]


def test_bare_filter_lists_every_record_newest_first(run, sample):
    _, out = run("filter", "")
    assert titles(out) == [
        "meeting with L",
        "reading docs",
        "autotests",
        "testing api manually",
        "making API v1",
    ], "bare l should list all records, newest first, with no Keep row"


def test_filter_with_words_puts_the_keep_row_first(run, sample):
    _, out = run("filter", "api")
    assert titles(out) == ['Log "api"', "testing api manually", "making API v1"], (
        "l api should offer to log the text, then the matches newest first"
    )


def test_filter_finds_by_word_prefixes(run, sample):
    _, out = run("filter", "making v1")
    assert titles(out) == ['Log "making v1"', "making API v1"], (
        "every typed word should prefix-match a word of the line"
    )


def test_filter_without_matches_only_offers_to_keep(run, sample):
    _, out = run("filter", "writing standup")
    assert titles(out) == ['Log "writing standup"'], "unmatched text should only be keepable"


def test_filter_of_an_empty_folder(run):
    _, out = run("filter", "")
    assert rows(out) == [], "no folder, no records, no rows"


def test_keep_row_shape(run, sample):
    _, out = run("filter", "  api  ")
    keep = rows(out)[0]
    assert keep["arg"] == "api", "the Keep row should carry the trimmed text"
    assert keep["variables"] == {"action": "keep"}, "↩ on the Keep row should keep"
    assert all(not mod["valid"] for mod in keep["mods"].values()), (
        "modifier keys should do nothing on the Keep row"
    )


def test_record_row_shape(run, sample):
    _, out = run("filter", "meeting")
    row = rows(out)[1]
    path = str(sample[-1])
    assert row["title"] == "meeting with L", "title should be the text"
    assert row["subtitle"] == "14:50 today", "subtitle should be the creation time"
    assert row["arg"] == path and row["type"] == "file", "↩ should open the file"
    assert row["variables"] == {"action": "open"}, "↩ should be the open action"
    assert row["quicklookurl"] == path, "Quick Look should show the file"
    assert row["text"] == {"copy": "meeting with L", "largetype": "meeting with L"}, (
        "⌘C and ⌘L should give the text"
    )
    assert row["mods"]["shift"]["arg"] == "meeting with L", "⇧↩ should pass the text to copy"
    assert row["mods"]["alt"] == {
        "arg": path,
        "subtitle": "Move to Trash",
        "variables": {"action": "trash"},
    }, "⌥↩ should trash the file"
    assert row["mods"]["cmd"] == {
        "arg": "meeting with L",
        "subtitle": "Rename",
        "variables": {"action": "rename", "path": path},
    }, "⌘↩ should open rename with the text prefilled and the path carried along"
    assert "uid" not in row, "no uid, so Alfred keeps the time order instead of learning one"


def test_keep_writes_a_record(run, folder):
    code, out = run("keep", "reading docs")
    assert code == 0 and out.strip() == "reading docs", "keep should echo the text"
    assert names(folder) == ["reading-docs.md"], "keep should create the file"


def test_keep_ignores_blank_text(run, folder):
    code, _out = run("keep", "   ")
    assert code == 1, "blank text is not a log line"
    assert not folder.exists(), "nothing should be written"


def test_rename_filter_offers_the_new_text(run):
    _, out = run("rename-filter", "reading Apache docs")
    (row,) = rows(out)
    assert row["title"] == 'Rename to "reading Apache docs"', "the row should show the new text"
    assert row["arg"] == "reading Apache docs", "↩ should pass the new text on"


def test_rename_filter_with_blank_text_is_invalid(run):
    _, out = run("rename-filter", " ")
    (row,) = rows(out)
    assert row["valid"] is False, "an empty name cannot be accepted"


def test_rename_changes_the_record(run, folder, sample):
    path = sample[3]
    code, out = run("rename", str(path), "reading Apache docs")
    assert code == 0 and out.strip() == "reading Apache docs", "rename should echo the new text"
    assert "reading-apache-docs.md" in names(folder) and not path.exists(), (
        "the file should be renamed"
    )


def test_trash_sends_the_file_to_the_trash(run, sample, mocker):
    trash = mocker.patch("wisp.cli.records.trash")
    path = sample[0]
    code, out = run("trash", str(path))
    assert code == 0 and out.strip() == "making API v1", "trash should echo the text"
    trash.assert_called_once_with(path)


def test_unknown_command(run):
    code, _ = run("frobnicate")
    assert code == 2, "an unknown command should fail loudly"


@pytest.mark.parametrize(
    "env, expected",
    [
        ({"log_folder": "/tmp/x"}, "/tmp/x"),
        ({"log_folder": "~/log"}, "~/log"),
        ({}, "~/log"),
        ({"log_folder": ""}, "~/log"),
    ],
)
def test_log_folder(env, expected, monkeypatch):
    monkeypatch.setenv("HOME", "/Users/me")
    folder = cli.log_folder(env)
    assert str(folder) == expected.replace("~", "/Users/me"), (
        f"{env} should resolve to {expected} with ~ expanded"
    )
