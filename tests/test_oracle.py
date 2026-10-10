import json
from datetime import timedelta
from pathlib import Path

import pytest

from conftest import NOW
from wisp import oracle, records

SERVER = oracle.Server("http://127.0.0.1:8080", "oracle", "")


def record(text, minutes_ago):
    when = NOW - timedelta(minutes=minutes_ago)
    return records.Record(Path(f"/log/{text}.md"), text, when, when)


@pytest.mark.parametrize(
    "env, expected",
    [
        ({}, None),
        ({"oracle_url": ""}, None),
        ({"oracle_url": "http://127.0.0.1:8080/"}, oracle.Server("http://127.0.0.1:8080", "", "")),
        (
            {"oracle_url": "http://h:1", "oracle_model": "qwen", "oracle_key": "s3cret"},
            oracle.Server("http://h:1", "qwen", "s3cret"),
        ),
        ({"oracle_apple": "1"}, oracle.APPLE),
        ({"oracle_apple": "1", "oracle_url": "http://h:1"}, oracle.APPLE),
        ({"oracle_apple": "0", "oracle_url": "http://h:1"}, oracle.Server("http://h:1", "", "")),
        ({"oracle_apple": "0"}, None),
    ],
)
def test_server_from_env(env, expected):
    assert oracle.server(env) == expected, f"{env} should give {expected}"


def test_apple_is_not_a_url():
    assert oracle.APPLE.apple and not oracle.APPLE.url, "Apple Intelligence needs no server URL"


def test_line_is_date_time_and_text():
    assert oracle.line(record("reading docs", 10)) == "2026-10-10 14:50  reading docs", (
        "a log line should carry its full date and time before the text"
    )


@pytest.mark.parametrize(
    "text, expected",
    [
        (". fix the build", "2026-10-10 14:50  TODO  fix the build"),
        ("! keys in 1password", "2026-10-10 14:50  NOTE  keys in 1password"),
        (".gitignore moved", "2026-10-10 14:50  .gitignore moved"),
    ],
)
def test_line_spells_the_kind_out(text, expected):
    assert oracle.line(record(text, 10)) == expected, f"{text!r} should be sent as {expected!r}"


def test_done_line_carries_the_time_it_was_done():
    opened = NOW - timedelta(days=1, minutes=10)
    done = records.Record(Path("/log/x.md"), "* fix the build", opened, NOW)
    assert oracle.line(done) == "2026-10-09 14:50  DONE 2026-10-10 15:00  fix the build", (
        "a done task should show when it was written and when it was finished"
    )


def test_system_prompt_explains_the_kinds():
    system, _ = (m["content"] for m in oracle.prompt("q", [], NOW))
    assert "TODO" in system and "DONE" in system and "NOTE" in system, (
        "the model should be told what the kind words mean"
    )


def test_evidence_lists_newest_first():
    lines = oracle.evidence([record("old", 60), record("new", 1)]).splitlines()
    assert [line.split("  ", 1)[1] for line in lines] == ["new", "old"], (
        "evidence should start with the newest line"
    )


def test_evidence_stops_at_the_budget_on_a_line_boundary():
    logs = [record(f"line {n}", n) for n in range(1, 50)]
    text = oracle.evidence(logs, budget=100)
    assert 0 < len(text) <= 100, "evidence should fit the budget"
    assert all(line.startswith("2026-") for line in text.splitlines()), (
        "a cut should never leave half a line"
    )
    assert text.splitlines()[0].endswith("line 1"), "the newest line is always sent"


def test_evidence_of_nothing_is_empty():
    assert oracle.evidence([]) == "", "an empty log sends nothing"


def test_prompt_carries_question_date_and_log():
    messages = oracle.prompt("today summary", [record("reading docs", 10)], NOW)
    system, user = (m["content"] for m in messages)
    assert "2026-10-10" in system and "Saturday" in system, "the model should be told today's date"
    assert user.startswith("today summary"), "the question comes first"
    assert "2026-10-10 14:50  reading docs" in user, "the log follows the question"


@pytest.mark.parametrize(
    "server, has_model",
    [(SERVER, True), (oracle.Server("http://h", "", ""), False)],
)
def test_payload(server, has_model):
    payload = oracle.payload(server, [{"role": "user", "content": "q"}])
    assert ("model" in payload) is has_model, "model is named only when configured"
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}, (
        "the template is asked not to think so the answer is not spent inside <think>"
    )
    assert payload["messages"] == [{"role": "user", "content": "q"}], "messages pass through"


@pytest.mark.parametrize(
    "content, expected",
    [
        ("Three things.\n", "Three things."),
        ("<think>\nhmm\n</think>\n\nThree things.", "Three things."),
        ("  spaced  ", "spaced"),
    ],
)
def test_answer_text(content, expected):
    response = {"choices": [{"message": {"content": content}}]}
    assert oracle.answer_text(response) == expected, f"{content!r} should read as {expected!r}"


def test_post_sends_json_with_bearer_key(mocker):
    opened = mocker.MagicMock()
    opened.__enter__.return_value.read.return_value = b'{"choices": []}'
    urlopen = mocker.patch("wisp.oracle.urllib.request.urlopen", return_value=opened)
    server = oracle.Server("http://h:1", "m", "s3cret")
    result = oracle.post(server, {"a": 1})
    request = urlopen.call_args.args[0]
    assert request.full_url == "http://h:1/v1/chat/completions", "chat completions endpoint"
    assert json.loads(request.data) == {"a": 1}, "payload goes as the JSON body"
    assert request.get_header("Authorization") == "Bearer s3cret", "the key is a bearer token"
    assert request.get_header("Content-type") == "application/json", "body is declared as JSON"
    assert result == {"choices": []}, "the JSON answer is returned decoded"


def test_post_without_key_sends_no_authorization(mocker):
    opened = mocker.MagicMock()
    opened.__enter__.return_value.read.return_value = b"{}"
    urlopen = mocker.patch("wisp.oracle.urllib.request.urlopen", return_value=opened)
    oracle.post(SERVER, {})
    assert urlopen.call_args.args[0].get_header("Authorization") is None, "no key, no header"


def test_ask_returns_the_model_answer():
    def post(server, payload):
        assert "today summary" in payload["messages"][-1]["content"], "the question is sent"
        return {"choices": [{"message": {"content": "You read docs."}}]}

    answer = oracle.ask("today summary", [record("reading docs", 5)], NOW, SERVER, post)
    assert answer == "You read docs.", "ask should hand back the model's text"


def test_remember_writes_question_then_answer(tmp_path):
    path = oracle.remember(tmp_path / "answers", "today summary", "You read docs.\nTwice.")
    assert path.name == "today-summary.md", "the file is named after the question"
    assert path.read_text() == "today summary\n\nYou read docs.\nTwice.\n", (
        "question on the first line, a blank line, then the answer"
    )


def test_read_answers_pairs_question_with_answer(tmp_path):
    folder = tmp_path / "answers"
    path = oracle.remember(folder, "today summary", "You read docs.\nTwice.")
    (answer,) = oracle.read_answers(folder, lambda p: NOW)
    assert answer == oracle.Answer(path, "today summary", "You read docs.\nTwice.", NOW), (
        "an answer file should read back as question, answer and time"
    )


def test_read_answers_of_a_missing_folder_is_empty(tmp_path):
    assert oracle.read_answers(tmp_path / "none", lambda p: NOW) == [], "no folder, no answers"


@pytest.mark.parametrize(
    "env, expected",
    [
        ({"alfred_workflow_data": "/data"}, "/data/answers"),
        ({}, "/Users/me/Library/Application Support/wisp/answers"),
    ],
)
def test_answers_folder(env, expected, monkeypatch):
    monkeypatch.setenv("HOME", "/Users/me")
    assert str(oracle.answers_folder(env)) == expected, f"{env} should keep answers in {expected}"
