import subprocess

import pytest

from wisp import apple

MESSAGES = [{"role": "system", "content": "be brief"}, {"role": "user", "content": "q\n\nLog:\nx"}]


def test_source_ships_with_the_package():
    source = apple.SOURCE
    assert source.exists() and "FoundationModels" in source.read_text(), (
        "the Swift helper's source is part of the package"
    )


def test_binary_lives_in_the_data_folder(tmp_path):
    assert apple.binary(tmp_path) == tmp_path / "bin" / "wisp-apple", "one binary per data folder"


def test_compile_command(tmp_path):
    binary = tmp_path / "bin" / "wisp-apple"
    argv = apple.compile_command(binary)
    assert argv[0] == "swiftc" and str(binary) in argv and str(apple.SOURCE) in argv, (
        "swiftc builds the helper from the shipped source into the binary"
    )


def test_respond_compiles_once_then_runs(tmp_path, mocker):
    binary = apple.binary(tmp_path)

    def run(argv, **kwargs):
        if argv[0] == "swiftc":
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_text("fake")
            return subprocess.CompletedProcess(argv, 0, "", "")
        assert argv == [str(binary), "be brief"], "the binary gets the instructions as argv"
        assert kwargs["input"] == "q\n\nLog:\nx", "and the prompt on stdin"
        return subprocess.CompletedProcess(argv, 0, "You read docs.\n", "")

    mocked = mocker.patch("wisp.apple.subprocess.run", side_effect=run)
    assert apple.respond(MESSAGES, tmp_path) == "You read docs.", "the answer is the stdout"
    assert apple.respond(MESSAGES, tmp_path) == "You read docs.", "and the second call reuses it"
    assert [c.args[0][0] for c in mocked.call_args_list] == ["swiftc", str(binary), str(binary)], (
        "swiftc runs once, the binary every time"
    )


def test_respond_recompiles_when_the_source_is_newer(tmp_path, mocker):
    binary = apple.binary(tmp_path)
    binary.parent.mkdir(parents=True)
    binary.write_text("old")
    mocker.patch("wisp.apple.stale", return_value=True)
    mocked = mocker.patch(
        "wisp.apple.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "ok", "")
    )
    apple.respond(MESSAGES, tmp_path)
    assert mocked.call_args_list[0].args[0][0] == "swiftc", "a newer source triggers a rebuild"


def test_respond_without_command_line_tools(tmp_path, mocker):
    mocker.patch("wisp.apple.subprocess.run", side_effect=FileNotFoundError("swiftc"))
    with pytest.raises(apple.AppleError, match="xcode-select --install"):
        apple.respond(MESSAGES, tmp_path)


def test_respond_when_the_build_fails(tmp_path, mocker):
    failed = subprocess.CalledProcessError(1, ["swiftc"], "", "error: no such module")
    mocker.patch("wisp.apple.subprocess.run", side_effect=failed)
    with pytest.raises(apple.AppleError, match="no such module"):
        apple.respond(MESSAGES, tmp_path)


def test_respond_when_the_model_refuses(tmp_path, mocker):
    binary = apple.binary(tmp_path)
    binary.parent.mkdir(parents=True)
    binary.write_text("fake")
    mocker.patch("wisp.apple.stale", return_value=False)
    failed = subprocess.CalledProcessError(
        2, [str(binary)], "", "Apple Intelligence is not enabled"
    )
    mocker.patch("wisp.apple.subprocess.run", side_effect=failed)
    with pytest.raises(apple.AppleError, match="not enabled"):
        apple.respond(MESSAGES, tmp_path)


def test_stale_compares_times(tmp_path):
    binary = tmp_path / "wisp-apple"
    assert apple.stale(binary) is True, "a missing binary is stale"
    binary.write_text("x")
    assert apple.stale(binary) is False, "a binary newer than the source is fresh"
