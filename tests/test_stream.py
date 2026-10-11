import json
import urllib.error
from pathlib import Path

import pytest

from wisp import apple, oracle

SERVER = oracle.Llama("http://127.0.0.1:8080", "oracle", "")
MESSAGES = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]


def sse(*chunks):
    lines = [
        b"data: " + json.dumps({"choices": [{"delta": {"content": c}}]}).encode() for c in chunks
    ]
    return [*lines, b"", b"data: [DONE]"]


@pytest.mark.parametrize(
    "lines, expected",
    [
        (sse("Hel", "lo"), ["Hel", "lo"]),
        ([b": keep-alive", b"data: [DONE]"], []),
        ([b'data: {"choices": [{"delta": {"role": "assistant"}}]}'], []),
        ([b"data: not json"], []),
    ],
)
def test_deltas(lines, expected):
    assert list(oracle.deltas(lines)) == expected, f"{lines} should yield {expected}"


def test_stream_feeds_text_as_it_arrives(mocker):
    opened = mocker.MagicMock()
    opened.__enter__.return_value = iter(sse("You ", "read ", "docs."))
    urlopen = mocker.patch("wisp.oracle.urllib.request.urlopen", return_value=opened)
    seen = []
    answer = oracle.stream(SERVER, {"messages": []}, seen.append)
    assert answer == "You read docs.", "the full answer is returned"
    assert seen == ["You ", "You read ", "You read docs."], "each step gets the text so far"
    assert json.loads(urlopen.call_args.args[0].data)["stream"] is True, (
        "the request asks to stream"
    )


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Three things.", "Three things."),
        ("<think>hmm</think>\nThree things.", "Three things."),
        ("<think>still thin", ""),
        ("  spaced ", "spaced"),
    ],
)
def test_visible(text, expected):
    assert oracle.visible(text) == expected, f"{text!r} should show as {expected!r}"


def test_llama_streams_the_answer(mocker):
    stream = mocker.patch("wisp.oracle.stream", return_value="<think>x</think>done")
    seen = []
    assert SERVER.respond(MESSAGES, seen.append) == "done", "the visible part of the stream"
    body = stream.call_args.args[1]
    assert body["model"] == "oracle" and body["messages"] == MESSAGES, (
        "the payload names the model and carries the messages"
    )


@pytest.mark.parametrize(
    "error, message",
    [
        (urllib.error.URLError("refused"), "Model not reachable at http://127.0.0.1:8080"),
        (TimeoutError(), "Model not reachable at http://127.0.0.1:8080"),
        (ConnectionResetError(), "Model not reachable at http://127.0.0.1:8080"),
        (
            urllib.error.HTTPError("http://127.0.0.1:8080", 401, "nope", {}, None),
            "Model answered 401 at http://127.0.0.1:8080",
        ),
    ],
    ids=["unreachable", "timeout", "reset", "refused"],
)
def test_llama_failures_are_model_errors(mocker, error, message):
    mocker.patch("wisp.oracle.stream", side_effect=error)
    with pytest.raises(oracle.ModelError, match=message):
        SERVER.respond(MESSAGES, None)


def test_apple_asks_the_helper(mocker):
    respond = mocker.patch("wisp.oracle.apple.respond", return_value="done")
    assert oracle.Apple(Path("/data")).respond(MESSAGES, None) == "done", (
        "the Apple answer is what the helper returned"
    )
    respond.assert_called_once_with(MESSAGES, Path("/data"))


def test_apple_failures_are_model_errors(mocker):
    mocker.patch("wisp.oracle.apple.respond", side_effect=apple.AppleError("not enabled"))
    with pytest.raises(oracle.ModelError, match="not enabled"):
        oracle.Apple(Path("/data")).respond(MESSAGES, None)
