import pytest

from wisp import macos


def test_trash_asks_finder(tmp_path, mocker):
    run = mocker.patch("wisp.macos.subprocess.run")
    path = tmp_path / 'it"s.md'
    macos.trash(path)
    (argv,), kwargs = run.call_args
    assert argv[:2] == ["osascript", "-e"], "trash should go through osascript"
    assert 'POSIX file "' + str(path).replace('"', '\\"') + '"' in argv[2], (
        "the path should be quoted for AppleScript"
    )
    assert kwargs["check"] is True, "a failed trash should raise"


def test_notify_posts_a_notification(mocker):
    run = mocker.patch("wisp.macos.subprocess.run")
    macos.notify('Asked about 12 lines "today"')
    (argv,), kwargs = run.call_args
    assert argv[:2] == ["osascript", "-e"], "notify should go through osascript"
    assert 'display notification "Asked about 12 lines \\"today\\""' in argv[2], (
        "the text should be quoted for AppleScript"
    )
    assert 'with title "Wisp"' in argv[2], "the notification should carry the workflow's name"
    assert kwargs["check"] is False, "a failed notification should not break the command"


def test_notify_is_silent_without_osascript(mocker):
    mocker.patch("wisp.macos.subprocess.run", side_effect=FileNotFoundError("osascript"))
    macos.notify("hello")


@pytest.mark.parametrize(
    "text, quoted",
    [
        ("/a/b.md", "/a/b.md"),
        ('/a/say "hi".md', '/a/say \\"hi\\".md'),
        ("/a/back\\slash.md", "/a/back\\\\slash.md"),
    ],
)
def test_applescript_string(text, quoted):
    assert macos.applescript_string(text) == quoted, (
        f"{text!r} should be escaped as {quoted!r} inside an AppleScript string"
    )
