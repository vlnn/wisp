import io
import json
import subprocess

import pytest

from wisp import apple

MESSAGES = [{"role": "system", "content": "be brief"}, {"role": "user", "content": "q\n\nLog:\nx"}]


def snapshots(*texts):
    return "".join(json.dumps(text) + "\n" for text in texts)


class Stdin(io.StringIO):
    def close(self):
        self.written = self.getvalue()
        super().close()


class FakeHelper:
    def __init__(self, stdout="", stderr="", code=0):
        self.stdin = Stdin()
        self.stdout = io.StringIO(stdout)
        self.stderr = io.StringIO(stderr)
        self.returncode = code
        self.argv = None

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        pass


@pytest.fixture
def compiled(tmp_path, mocker):
    binary = apple.binary(tmp_path)
    binary.parent.mkdir(parents=True)
    binary.write_text("fake")
    mocker.patch("wisp.apple.stale", return_value=False)
    return binary


@pytest.fixture
def helper(mocker):
    def run(argv, **kwargs):
        fake = helper.process
        fake.argv = argv
        return fake

    mocker.patch("wisp.apple.subprocess.Popen", side_effect=run)
    helper.process = FakeHelper()
    return helper


def test_source_ships_with_the_package():
    source = apple.SOURCE
    assert source.exists() and "streamResponse" in source.read_text(), (
        "the Swift helper's source is part of the package and streams"
    )


def test_binary_lives_in_the_data_folder(tmp_path):
    assert apple.binary(tmp_path) == tmp_path / "bin" / "wisp-apple", "one binary per data folder"


def test_compile_command(tmp_path):
    binary = tmp_path / "bin" / "wisp-apple"
    argv = apple.compile_command(binary)
    assert argv[0] == "swiftc" and str(binary) in argv and str(apple.SOURCE) in argv, (
        "swiftc builds the helper from the shipped source into the binary"
    )


def test_respond_feeds_each_snapshot_and_returns_the_last(tmp_path, compiled, helper):
    helper.process = FakeHelper(snapshots("You ", "You read", "You read docs.\n"))
    seen = []
    answer = apple.respond(MESSAGES, tmp_path, seen.append)
    assert answer == "You read docs.", "the answer is the last snapshot, stripped"
    assert seen == ["You ", "You read", "You read docs.\n"], "each snapshot reaches on_text as is"
    assert helper.process.argv == [str(compiled), "be brief"], "the binary gets the instructions"
    assert helper.process.stdin.written == "q\n\nLog:\nx", "and the prompt on stdin"


def test_respond_without_on_text(tmp_path, compiled, helper):
    helper.process = FakeHelper(snapshots("done"))
    assert apple.respond(MESSAGES, tmp_path) == "done", "on_text is optional"


def test_respond_skips_lines_that_are_not_snapshots(tmp_path, compiled, helper):
    helper.process = FakeHelper("warning: something\n" + snapshots("done"))
    assert apple.respond(MESSAGES, tmp_path) == "done", "stray output is ignored"


def test_respond_compiles_once_then_runs(tmp_path, mocker, helper):
    binary = apple.binary(tmp_path)

    def build(argv, **kwargs):
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("fake")
        return subprocess.CompletedProcess(argv, 0, "", "")

    swiftc = mocker.patch("wisp.apple.subprocess.run", side_effect=build)
    helper.process = FakeHelper(snapshots("done"))
    apple.respond(MESSAGES, tmp_path)
    helper.process = FakeHelper(snapshots("done"))
    apple.respond(MESSAGES, tmp_path)
    assert swiftc.call_count == 1 and swiftc.call_args.args[0][0] == "swiftc", (
        "swiftc runs once, the binary every time"
    )


def test_respond_recompiles_when_the_source_is_newer(tmp_path, mocker, helper):
    binary = apple.binary(tmp_path)
    binary.parent.mkdir(parents=True)
    binary.write_text("old")
    mocker.patch("wisp.apple.stale", return_value=True)
    swiftc = mocker.patch(
        "wisp.apple.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "", "")
    )
    helper.process = FakeHelper(snapshots("done"))
    apple.respond(MESSAGES, tmp_path)
    assert swiftc.call_args.args[0][0] == "swiftc", "a newer source triggers a rebuild"


def test_respond_without_command_line_tools(tmp_path, mocker):
    mocker.patch("wisp.apple.subprocess.run", side_effect=FileNotFoundError("swiftc"))
    with pytest.raises(apple.AppleError, match="xcode-select --install"):
        apple.respond(MESSAGES, tmp_path)


def test_respond_when_the_build_fails(tmp_path, mocker):
    failed = subprocess.CalledProcessError(1, ["swiftc"], "", "error: no such module")
    mocker.patch("wisp.apple.subprocess.run", side_effect=failed)
    with pytest.raises(apple.AppleError, match="no such module"):
        apple.respond(MESSAGES, tmp_path)


def test_respond_when_the_model_refuses(tmp_path, compiled, helper):
    helper.process = FakeHelper("", "Apple Intelligence is not enabled", 2)
    with pytest.raises(apple.AppleError, match="not enabled"):
        apple.respond(MESSAGES, tmp_path)


def test_respond_when_the_helper_dies_silently(tmp_path, compiled, helper):
    helper.process = FakeHelper("", "", 1)
    with pytest.raises(apple.AppleError, match="failed"):
        apple.respond(MESSAGES, tmp_path)


def test_respond_when_the_helper_hangs(tmp_path, compiled, helper, mocker):
    helper.process = FakeHelper(snapshots("part"))
    mocker.patch.object(
        FakeHelper, "wait", side_effect=subprocess.TimeoutExpired(["wisp-apple"], apple.TIMEOUT)
    )
    with pytest.raises(apple.AppleError, match="did not answer in time"):
        apple.respond(MESSAGES, tmp_path)


def test_stale_compares_times(tmp_path):
    binary = tmp_path / "wisp-apple"
    assert apple.stale(binary) is True, "a missing binary is stale"
    binary.write_text("x")
    assert apple.stale(binary) is False, "a binary newer than the source is fresh"
