import urllib.error
from pathlib import Path

import pytest
from hoard.alfred import apple, chat

from wisp import oracle

SERVER = oracle.Llama("http://127.0.0.1:8080", "oracle", "")
MESSAGES = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]


def test_llama_asks_the_toolkit_with_its_own_budget_of_options(mocker):
    respond = mocker.patch("hoard.alfred.chat.respond", return_value="done")
    seen = []
    assert SERVER.respond(MESSAGES, seen.append) == "done", (
        "the toolkit's visible answer comes back"
    )
    server, messages, on_text = respond.call_args.args
    assert (server, messages, on_text) == (
        chat.Server("http://127.0.0.1:8080", "oracle", ""),
        MESSAGES,
        seen.append,
    ), "the server, the messages and the callback pass through"
    assert respond.call_args.kwargs == {
        "timeout": oracle.TIMEOUT,
        "temperature": oracle.TEMPERATURE,
        "max_tokens": oracle.MAX_TOKENS,
    }, "wisp decides how long, how warm and how much"


@pytest.mark.parametrize(
    "error, message",
    [
        (
            chat.ModelError("refused", "http://127.0.0.1:8080/v1/chat/completions"),
            "Model not reachable at http://127.0.0.1:8080",
        ),
        (
            chat.ModelError("timed out", "http://127.0.0.1:8080/v1/chat/completions"),
            "Model not reachable at http://127.0.0.1:8080",
        ),
        (
            chat.ModelError("HTTP 401 nope", "http://127.0.0.1:8080/v1/chat/completions"),
            "Model answered 401 at http://127.0.0.1:8080",
        ),
        (chat.ModelError("context too long"), "Model refused: context too long"),
    ],
    ids=["unreachable", "timeout", "answered", "refused"],
)
def test_llama_failures_keep_wisps_wording(mocker, error, message):
    mocker.patch("hoard.alfred.chat.respond", side_effect=error)
    with pytest.raises(oracle.ModelError, match=message):
        SERVER.respond(MESSAGES, None)


def test_apple_asks_the_helper_and_streams(mocker):
    respond = mocker.patch("hoard.alfred.apple.respond", return_value="<think>x</think>done")
    seen = []
    assert oracle.Apple(Path("/data")).respond(MESSAGES, seen.append) == "done", (
        "the visible part of the helper's answer"
    )
    respond.assert_called_once_with(MESSAGES, "/data", seen.append)


def test_apple_failures_are_model_errors(mocker):
    mocker.patch("hoard.alfred.apple.respond", side_effect=apple.AppleError("not enabled"))
    with pytest.raises(oracle.ModelError, match="not enabled"):
        oracle.Apple(Path("/data")).respond(MESSAGES, None)


@pytest.mark.parametrize(
    "outcome, expected",
    [
        (None, "server http://127.0.0.1:8080 (model oracle): reachable"),
        (
            urllib.error.URLError("refused"),
            "server http://127.0.0.1:8080 (model oracle): not reachable",
        ),
    ],
    ids=["up", "down"],
)
def test_llama_check(mocker, outcome, expected):
    opened = mocker.MagicMock()
    opened.__enter__.return_value.read.return_value = b'{"data": []}'
    urlopen = mocker.patch("urllib.request.urlopen", side_effect=outcome or [opened])
    assert SERVER.check() == expected, "check says whether the server answers"
    assert urlopen.call_args.args[0].full_url == "http://127.0.0.1:8080/v1/models", (
        "the models endpoint is the probe"
    )


@pytest.mark.parametrize(
    "compiled, swiftc, expected",
    [
        (True, None, "Apple Intelligence: helper compiled"),
        (False, "/usr/bin/swiftc", "Apple Intelligence: helper compiles on first ask"),
        (False, None, f"Apple Intelligence: {apple.TOOLS_MISSING}"),
    ],
    ids=["compiled", "tools", "no-tools"],
)
def test_apple_check(tmp_path, mocker, compiled, swiftc, expected):
    if compiled:
        binary = apple.binary(str(tmp_path))
        binary.parent.mkdir(parents=True)
        binary.write_text("fake")
    mocker.patch("wisp.oracle.shutil.which", return_value=swiftc)
    assert oracle.Apple(tmp_path).check() == expected, "check says what the helper needs"
