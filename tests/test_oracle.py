from datetime import timedelta
from pathlib import Path

import pytest

from conftest import NOW
from wisp import oracle, records

SERVER = oracle.Llama("http://127.0.0.1:8080", "oracle", "")
DATA = Path("/Users/me/Library/Application Support/wisp")


def record(text, minutes_ago):
    when = NOW - timedelta(minutes=minutes_ago)
    return records.Record.parsed(Path(f"/log/{text}.md"), text, when, when)


@pytest.mark.parametrize(
    "env, expected",
    [
        ({}, None),
        ({"oracle_url": ""}, None),
        ({"oracle_url": "http://127.0.0.1:8080/"}, oracle.Llama("http://127.0.0.1:8080", "", "")),
        (
            {"oracle_url": "http://h:1", "oracle_model": "qwen", "oracle_key": "s3cret"},
            oracle.Llama("http://h:1", "qwen", "s3cret"),
        ),
        ({"oracle_apple": "1"}, oracle.Apple(DATA)),
        ({"oracle_apple": "1", "oracle_url": "http://h:1"}, oracle.Apple(DATA)),
        ({"oracle_apple": "1", "alfred_workflow_data": "/data"}, oracle.Apple(Path("/data"))),
        ({"oracle_apple": "0", "oracle_url": "http://h:1"}, oracle.Llama("http://h:1", "", "")),
        ({"oracle_apple": "0"}, None),
    ],
)
def test_backend_from_env(env, expected, monkeypatch):
    monkeypatch.setenv("HOME", "/Users/me")
    assert oracle.backend(env) == expected, f"{env} should give {expected}"


@pytest.mark.parametrize(
    "backend, expected",
    [(SERVER, oracle.BUDGET), (oracle.Apple(DATA), oracle.APPLE_BUDGET)],
)
def test_each_backend_has_its_budget(backend, expected):
    assert backend.budget == expected, f"{backend} should send {expected} characters"


def test_line_is_date_time_and_text():
    assert oracle.line(record("reading docs", 10)) == "2026-10-10 14:50  reading docs", (
        "a log line should carry its full date and time before the text"
    )


@pytest.mark.parametrize(
    "text, expected",
    [
        (". fix the build", "2026-10-10 14:50  TODO  fix the build"),
        ("! keys in 1password", "2026-10-10 14:50  NOTE  keys in 1password"),
        ("? ship friday", "2026-10-10 14:50  QUESTION  ship friday"),
        (".gitignore moved", "2026-10-10 14:50  .gitignore moved"),
    ],
)
def test_line_spells_the_kind_out(text, expected):
    assert oracle.line(record(text, 10)) == expected, f"{text!r} should be sent as {expected!r}"


def test_done_line_carries_the_time_it_was_done():
    opened = NOW - timedelta(days=1, minutes=10)
    done = records.Record.parsed(Path("/log/x.md"), "* fix the build", opened, NOW)
    assert oracle.line(done) == "2026-10-09 14:50  DONE 2026-10-10 15:00  fix the build", (
        "a done task should show when it was written and when it was finished"
    )


def test_decision_line_carries_the_time_it_was_made():
    asked = NOW - timedelta(days=1, minutes=10)
    decision = records.Record.parsed(Path("/log/x.md"), "= ship friday", asked, NOW)
    assert oracle.line(decision) == "2026-10-09 14:50  DECIDED 2026-10-10 15:00  ship friday", (
        "a decision should show when it was raised and when it was settled"
    )


@pytest.mark.parametrize("word", ["TODO", "DONE", "NOTE", "QUESTION", "DECIDED"])
def test_system_prompt_explains_the_kinds(word):
    system, _ = (m["content"] for m in oracle.prompt("q", [], NOW))
    assert word in system, f"the model should be told what {word} means"


def test_evidence_lists_newest_first():
    lines = oracle.evidence("", [record("old", 60), record("new", 1)]).lines()
    assert [line.split("  ", 1)[1] for line in lines] == ["new", "old"], (
        "evidence should start with the newest line"
    )


def test_evidence_stops_at_the_budget_on_a_line_boundary():
    logs = [record(f"line {n}", n) for n in range(1, 50)]
    text = oracle.evidence("", logs, budget=100).text()
    assert 0 < len(text) <= 100, "evidence should fit the budget"
    assert all(line.startswith("2026-") for line in text.splitlines()), (
        "a cut should never leave half a line"
    )
    assert text.splitlines()[0].endswith("line 1"), "the newest line is always sent"


def test_evidence_sends_the_newest_line_even_past_the_budget():
    (line,) = oracle.evidence("", [record("a line longer than the budget", 1)], budget=5).lines()
    assert line.endswith("a line longer than the budget"), "one line is better than none"


def test_evidence_lines_are_what_text_joins():
    logs = [record(f"line {n}", n) for n in range(1, 50)]
    found = oracle.evidence("", logs, budget=100)
    assert "\n".join(found.lines()) == found.text(), "same cut, counted not split"


def test_evidence_of_nothing_is_empty():
    assert oracle.evidence("", []).text() == "", "an empty log sends nothing"


def test_evidence_keeps_old_matching_lines_past_the_budget():
    logs = [record(f"line {n}", n) for n in range(1, 50)] + [record("api work", 500)]
    found = oracle.evidence("api", logs, budget=100)
    assert [r.text for r in found.matching] == ["api work"], "the one match is sent"
    assert found.lines()[-1].endswith("api work"), "sent last, since it is the oldest"
    assert 3 <= len(found.lines()) <= 4, "the rest of the budget goes to the newest lines"
    assert len(found.text()) <= 100, "all within the budget"


def test_evidence_matches_the_way_the_list_does():
    logs = [record(". fix api", 1), record("api v1", 2), record("docs", 3)]
    found = oracle.evidence(". ap", logs)
    assert [r.text for r in found.matching] == [". fix api"], (
        "a sigil narrows the kind and words prefix-match, as `l` does"
    )
    assert [r.text for r in found.records()] == [". fix api"], (
        "a sigil bounds what goes to the model, as it bounds the list"
    )
    whole = oracle.evidence("ap", logs)
    assert [r.text for r in whole.records()] == [". fix api", "api v1", "docs"], (
        "without one, the words single out and the rest follows, newest first"
    )


def test_evidence_without_words_matches_nothing_in_particular():
    found = oracle.evidence("", [record("a", 1), record("b", 2)])
    assert found.matching == [], "no words, nothing singled out"
    assert len(found.filling) == 2, "everything is filling"


def test_evidence_prefers_newest_matches_when_they_overflow():
    logs = [record(f"api {n}", n) for n in range(1, 50)]
    found = oracle.evidence("api", logs, budget=100)
    assert found.filling == [], "matches alone fill the budget"
    assert found.lines()[0].endswith("api 1"), "the newest match comes first"


def test_prompt_carries_question_date_and_log():
    messages = oracle.prompt("today summary", [record("reading docs", 10)], NOW)
    system, user = (m["content"] for m in messages)
    assert "2026-10-10" in system and "Saturday" in system, "the model should be told today's date"
    assert user.startswith("today summary"), "the question comes first"
    assert "2026-10-10 14:50  reading docs" in user, "the log follows the question"


@pytest.mark.parametrize(
    "server, has_model",
    [(SERVER, True), (oracle.Llama("http://h", "", ""), False)],
)
def test_payload(server, has_model):
    payload = oracle.payload(server, [{"role": "user", "content": "q"}])
    assert ("model" in payload) is has_model, "model is named only when configured"
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}, (
        "the template is asked not to think so the answer is not spent inside <think>"
    )
    assert payload["messages"] == [{"role": "user", "content": "q"}], "messages pass through"


def test_remember_writes_question_then_answer(tmp_path):
    path = oracle.remember(tmp_path / "answers", "today summary", "You read docs.\nTwice.")
    assert path.name == "today-summary.md", "the file is named after the question"
    assert path.read_text() == "today summary\n\nYou read docs.\nTwice.\n", (
        "question on the first line, a blank line, then the answer"
    )


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


@pytest.mark.parametrize("backend", [SERVER, oracle.Apple(DATA)])
def test_each_backend_is_a_backend(backend):
    assert isinstance(backend, oracle.Backend), f"{backend} should answer the Backend protocol"


def test_evidence_within_a_window_fills_from_that_window_only():
    logs = [record("today api", 1), record("today docs", 2), record("old api", 60 * 24 * 3)]
    found = oracle.evidence("api today", logs, now=NOW)
    assert [r.text for r in found.matching] == ["today api"], "words match within the window"
    assert [r.text for r in found.filling] == ["today docs"], "the fill stays in the window"
