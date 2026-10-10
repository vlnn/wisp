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


def test_read_folder_lists_newest_first(folder, sample, created):
    texts = [r.text for r in records.read_folder(folder, created)]
    assert texts == [
        "meeting with L",
        "reading docs",
        "autotests",
        "testing api manually",
        "making API v1",
    ], "records should be sorted by creation time, newest first"


def test_read_folder_uses_the_first_non_empty_line(folder, created, stamps):
    path = folder / "note.md"
    folder.mkdir()
    path.write_text("\n\n  the real line  \nmore\n")
    stamps[path.name] = NOW
    (record,) = records.read_folder(folder, created)
    assert record.text == "the real line", "text should be the first non-empty line, stripped"


def test_read_folder_ignores_other_files(folder, created, stamps):
    folder.mkdir()
    (folder / "keep.md").write_text("kept\n")
    (folder / ".hidden.md").write_text("hidden\n")
    (folder / "notes.txt").write_text("text\n")
    (folder / "sub").mkdir()
    stamps["keep.md"] = NOW
    texts = [r.text for r in records.read_folder(folder, created)]
    assert texts == ["kept"], "only visible .md files should become records"


def test_read_folder_of_a_missing_folder_is_empty(folder, created):
    assert records.read_folder(folder, created) == [], "a missing folder has no records"


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


def test_trash_asks_finder(folder, mocker):
    run = mocker.patch("wisp.records.subprocess.run")
    path = folder / 'it"s.md'
    records.trash(path)
    (argv,), kwargs = run.call_args
    assert argv[:2] == ["osascript", "-e"], "trash should go through osascript"
    assert 'POSIX file "' + str(path).replace('"', '\\"') + '"' in argv[2], (
        "the path should be quoted for AppleScript"
    )
    assert kwargs["check"] is True, "a failed trash should raise"


@pytest.mark.parametrize(
    "path, quoted",
    [
        ("/a/b.md", "/a/b.md"),
        ('/a/say "hi".md', '/a/say \\"hi\\".md'),
        ("/a/back\\slash.md", "/a/back\\\\slash.md"),
    ],
)
def test_applescript_string(path, quoted):
    assert records.applescript_string(path) == quoted, (
        f"{path!r} should be escaped as {quoted!r} inside an AppleScript string"
    )
