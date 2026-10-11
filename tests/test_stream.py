import json

import pytest

from wisp import oracle

SERVER = oracle.Server("http://127.0.0.1:8080", "oracle", "")


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


@pytest.mark.parametrize(
    "server, expected",
    [
        (SERVER, oracle.BUDGET),
        (oracle.APPLE, oracle.APPLE_BUDGET),
    ],
)
def test_budget_for(server, expected):
    assert oracle.budget_for(server) == expected, f"{server} should send {expected} characters"


def test_answer_streams_from_a_server(mocker):
    stream = mocker.patch("wisp.oracle.stream", return_value="done")
    seen = []
    answer = oracle.answer(SERVER, [{"role": "user", "content": "q"}], seen.append, "/data")
    assert answer == "done", "a server answer is what stream returned"
    body = stream.call_args.args[1]
    assert body["model"] == "oracle" and body["messages"] == [{"role": "user", "content": "q"}], (
        "the payload names the model and carries the messages"
    )


def test_answer_asks_apple(mocker):
    respond = mocker.patch("wisp.oracle.apple.respond", return_value="done")
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]
    assert oracle.answer(oracle.APPLE, messages, None, "/data") == "done", (
        "the Apple answer is what respond returned"
    )
    respond.assert_called_once_with(messages, "/data")
