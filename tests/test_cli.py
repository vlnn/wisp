import json
import urllib.error
from datetime import timedelta
from pathlib import Path

import pytest

from conftest import NOW, names
from wisp import apple, cli, oracle, present, view


@pytest.fixture
def env(folder, tmp_path):
    return {"log_folder": str(folder), "alfred_workflow_data": str(tmp_path / "data")}


@pytest.fixture
def served(env):
    env["oracle_url"] = "http://127.0.0.1:8080"
    return env


@pytest.fixture
def answered(env, stamps):
    def remember(question, answer, minutes_ago):
        path = oracle.remember(Path(env["alfred_workflow_data"]) / "answers", question, answer)
        stamps[path.name] = NOW - timedelta(minutes=minutes_ago)
        return path

    return remember


@pytest.fixture
def notify(mocker):
    return mocker.patch("wisp.cli.macos.notify")


def model_says(mocker, text):
    def answer(server, messages, on_text, data):
        if on_text:
            on_text(text[:3])
            on_text(text)
        return oracle.visible(text)

    return mocker.patch("wisp.cli.oracle.answer", side_effect=answer)


def model_fails(mocker, error):
    return mocker.patch("wisp.cli.oracle.answer", side_effect=error)


@pytest.fixture
def run(env, created, changed, capsys):
    def go(*argv):
        code = cli.run(list(argv), env, now=NOW, created=created, changed=changed)
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


@pytest.mark.parametrize("text", ["   ", ".", ". ", "!  "])
def test_keep_ignores_blank_text(run, folder, text):
    code, _out = run("keep", text)
    assert code == 1, f"{text!r} is not a log line"
    assert not folder.exists(), "nothing should be written"


def test_keep_writes_a_task(run, folder):
    code, out = run("keep", ".", "fix", "the", "build")
    assert code == 0 and out.strip() == ". fix the build", "keep should echo the normalised line"
    assert (folder / "fix-the-build.md").read_text() == ". fix the build\n", (
        "the file should hold the task line"
    )


def test_filter_by_sigil_lists_that_kind(run, logged):
    logged(". fix the build", 5)
    logged("* test api manually", 3)
    logged("api v1", 1)
    _, out = run("filter", ".")
    assert titles(out) == [". fix the build"], "a bare sigil lists open tasks and offers nothing"
    _, out = run("filter", ". api")
    assert titles(out) == ['Task "api"'], "a sigil with words offers a task of that kind"


def test_mark_flips_a_task_and_echoes_the_new_line(run, logged):
    path = logged(". fix the build", 5)
    code, out = run("mark", str(path))
    assert code == 0 and out.strip() == "* fix the build", "mark should echo the flipped line"
    assert path.read_text() == "* fix the build\n", "the file should now be done"
    code, out = run("mark", str(path))
    assert out.strip() == ". fix the build", "a second mark reopens it"


def test_done_row_reads_the_time_it_was_marked(run, logged, touched):
    path = logged("* fix the build", 120)
    touched[path.name] = NOW
    _, out = run("filter", "*")
    assert rows(out)[0]["subtitle"] == "done 15:00 today · 13:00 today", (
        "the view should read the done time from the injected changed callable"
    )


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
    trash = mocker.patch("wisp.cli.macos.trash")
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


def test_question_without_a_server_says_what_to_set(run, sample):
    _, out = run("filter", "? today summary")
    (row,) = rows(out)
    assert row["title"] == present.NO_SERVER, "without a server the only row says how to get one"
    assert row["valid"] is False, "and it cannot be actioned"


def test_question_offers_to_ask_then_lists_past_answers(run, served, sample, answered):
    answered("today summary", "Docs, mostly.", 60)
    answered("what about api", "Made v1.", 30)
    _, out = run("filter", "? today summary")
    assert titles(out) == ['Ask "today summary"', "today summary"], (
        "the Ask row first, then earlier answers whose question matches"
    )
    ask = rows(out)[0]
    assert ask["subtitle"] == "↩ asks the model about 5 lines"
    assert ask["arg"] == "today summary" and ask["variables"] == {"action": "ask"}, (
        "↩ should ask with the bare question"
    )


def test_bare_question_mark_lists_every_answer_newest_first(run, served, answered):
    answered("today summary", "Docs, mostly.", 60)
    answered("what about api", "Made v1.", 30)
    _, out = run("filter", "?")
    assert titles(out) == ["what about api", "today summary"], (
        "all answers, newest first, no Ask row"
    )


def test_answer_row_shape(run, served, answered):
    path = str(answered("today summary", "Docs, mostly.\nAnd a meeting.", 10))
    _, out = run("filter", "?")
    (row,) = rows(out)
    assert row["subtitle"] == "14:50 today · Docs, mostly.", (
        "when it was answered and how it starts"
    )
    assert row["arg"] == path and row["type"] == "file", "↩ opens the answer file"
    assert row["variables"] == {"action": "open"}, "↩ is the open action"
    assert row["text"]["copy"] == "Docs, mostly.\nAnd a meeting.", "⌘C gives the whole answer"
    assert row["mods"]["shift"]["arg"] == "Docs, mostly.\nAnd a meeting.", "⇧↩ copies the answer"
    assert row["mods"]["alt"]["variables"] == {"action": "trash"}, "⌥↩ trashes the answer"
    assert row["mods"]["cmd"]["valid"] is False, "answers are not renamed"


def test_ask_prints_the_answer_and_keeps_nothing(run, served, sample, mocker, notify, env):
    model_says(mocker, "<think>x</think>\nYou read docs.")
    code, out = run("ask", "today summary")
    assert code == 0 and out == "You read docs.\n", "ask prints the answer"
    assert not (Path(env["alfred_workflow_data"]) / "answers").exists(), "nothing is saved"
    assert [c.args[0] for c in notify.call_args_list] == [
        "Asking about 5 lines…",
        "You read docs.",
    ], "one notification when asking, one with the answer"


def test_ask_keep_saves_the_answer(run, served, sample, mocker, notify):
    model_says(mocker, "You read docs.")
    code, out = run("ask", "--keep", "today summary")
    path = Path(out.strip())
    assert code == 0 and path.name == "today-summary.md", "ask --keep prints the answer file"
    assert path.read_text() == "today summary\n\nYou read docs.\n", (
        "the file holds question and answer"
    )


def test_keep_answer_saves_what_the_view_shows(run, env):
    code, out = run("keep-answer", "today summary", "You read docs.")
    path = Path(out.strip())
    assert code == 0 and path.name == "today-summary.md", "keep-answer prints the answer file"
    assert path.read_text() == "today summary\n\nYou read docs.\n", (
        "the file holds question and answer"
    )
    assert path.parent == Path(env["alfred_workflow_data"]) / "answers", "next to the others"


def test_keep_answer_needs_both(run):
    assert run("keep-answer", "today summary")[0] == 1, "no answer, nothing to keep"


def test_ask_dry_run_prints_the_prompt_and_asks_nothing(run, served, sample, mocker, notify):
    post = model_says(mocker, "unused")
    code, out = run("ask", "--dry-run", "today summary")
    assert code == 0 and out.startswith("today summary\n") and "making API v1" in out, (
        "dry run prints what the model would be sent"
    )
    post.assert_not_called()
    notify.assert_not_called()


def test_ask_without_a_server(run, sample, notify):
    code, _ = run("ask", "today summary")
    assert code == 1, "no server, no answer"
    notify.assert_called_once_with(present.NO_SERVER)


def test_ask_when_the_server_is_down(run, served, sample, mocker, notify):
    model_fails(mocker, urllib.error.URLError("refused"))
    code, _ = run("ask", "today summary")
    assert code == 1, "an unreachable server fails the command"
    notify.assert_called_with("Model not reachable at http://127.0.0.1:8080")


def test_ask_when_the_server_refuses(run, served, sample, mocker, notify):
    error = urllib.error.HTTPError("http://127.0.0.1:8080", 401, "nope", {}, None)
    model_fails(mocker, error)
    code, _ = run("ask", "today summary")
    assert code == 1, "a refused request fails the command"
    notify.assert_called_with("Model answered 401 at http://127.0.0.1:8080")


def test_ask_when_the_answer_is_malformed(run, served, sample, mocker, notify):
    model_fails(mocker, KeyError("choices"))
    code, _ = run("ask", "today summary")
    assert code == 1, "a bad answer fails the command"
    notify.assert_called_with("Model gave no answer")


def test_ask_with_blank_question(run, served, sample, notify):
    code, _ = run("ask", " ")
    assert code == 1, "nothing to ask"


def test_question_row_counts_only_the_lines_that_fit(run, env, sample):
    env["oracle_apple"] = "1"
    _, out = run("filter", "? today summary")
    assert rows(out)[0]["subtitle"] == "↩ asks the model about 5 lines", "five short lines fit"


def test_ask_with_a_job_reports_progress_instead_of_notifying(
    run, served, sample, mocker, notify, tmp_path, env
):
    model_says(mocker, "You read docs.")
    job = tmp_path / "jobs" / "j1"
    code, out = run("ask", "--job", str(job), "today summary")
    assert code == 0 and out == "You read docs.\n", "ask with a job succeeds"
    done = view.Job(job)
    assert done.partial() == "You read docs." and done.done() is True, (
        "the job carries the text and knows it is finished"
    )
    assert not (Path(env["alfred_workflow_data"]) / "answers").exists(), "nothing is saved"
    notify.assert_not_called()


def test_ask_with_a_job_records_the_failure(run, served, sample, mocker, notify, tmp_path):
    model_fails(mocker, urllib.error.URLError("refused"))
    job = tmp_path / "jobs" / "j1"
    code, _ = run("ask", "--job", str(job), "today summary")
    assert code == 1 and view.Job(job).error() == "Model not reachable at http://127.0.0.1:8080", (
        "the failure goes to the job, not to a notification"
    )
    notify.assert_not_called()


def test_ask_apple_errors_are_messages(run, env, sample, mocker, notify):
    env["oracle_apple"] = "1"
    model_fails(mocker, apple.AppleError("Apple Intelligence is not enabled"))
    code, _ = run("ask", "today summary")
    assert code == 1, "an Apple failure fails the command"
    notify.assert_called_with("Apple Intelligence is not enabled")


def test_view_starts_a_job_in_the_background(run, served, sample, mocker):
    popen = mocker.patch("wisp.cli.subprocess.Popen")
    _, out = run("view", "today summary")
    shown = json.loads(out)
    job = shown["variables"]["job"]
    assert shown["rerun"] == view.RERUN and job, "the view polls a job it just started"
    argv = popen.call_args.args[0]
    assert argv[1:] == ["-m", "wisp", "ask", "--job", job, "today summary"], (
        "the job is wisp ask with the job folder"
    )
    assert popen.call_args.kwargs["start_new_session"] is True, "and it outlives the view script"


def test_view_polls_a_running_job(run, served, sample, mocker, tmp_path):
    popen = mocker.patch("wisp.cli.subprocess.Popen")
    job = view.Job(tmp_path / "jobs" / "j1")
    job.progress("You rea")
    served["job"] = str(job.folder)
    _, out = run("view", "today summary")
    shown = json.loads(out)
    assert shown["response"] == "You rea" and shown["rerun"] == view.RERUN, "shows the text so far"
    popen.assert_not_called()


def test_view_without_a_server(run, sample):
    _, out = run("view", "today summary")
    assert json.loads(out)["response"] == f"**{present.NO_SERVER}**", "the view says what to set"


def test_menu_lists_the_actions_for_one_record(run, logged):
    path = logged(". fix the build", 5)
    _, out = run("menu", str(path), "")
    assert titles(out) == ["Finish", "Open", "Rename", "Copy", "Trash"], (
        "the menu should be built from the record at that path"
    )
    _, out = run("menu", str(path), "fi")
    assert titles(out) == ["Finish"], "the typed query narrows the menu"
