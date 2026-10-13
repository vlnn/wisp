import json
from pathlib import Path

import pytest

from conftest import LINES, NOW, names
from wisp import apple, cli, oracle, present, view


@pytest.fixture
def env(folder, tmp_path):
    return {"log_folder": str(folder), "alfred_workflow_data": str(tmp_path / "data")}


@pytest.fixture
def served(env):
    env["oracle_url"] = "http://127.0.0.1:8080"
    return env


@pytest.fixture
def notify(mocker):
    return mocker.patch("wisp.cli.macos.notify")


def model_says(mocker, text):
    def respond(self, messages, on_text):
        if on_text:
            on_text(text[:3])
            on_text(text)
        return oracle.visible(text)

    return mocker.patch("wisp.oracle.Llama.respond", respond)


def model_fails(mocker, error):
    return mocker.patch("wisp.oracle.Llama.respond", side_effect=error)


@pytest.fixture
def run(env, clock, capsys):
    def go(*argv):
        code = cli.run(list(argv), env, now=NOW, stamps=clock)
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
    assert row["arg"] == "", "↩ should open the menu with nothing typed"
    assert row["variables"] == {"action": "menu", "path": path}, "↩ should be the menu action"
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


def test_filter_treats_a_question_mark_as_a_kind(run, logged):
    logged("? ship friday", 5)
    _, out = run("filter", "?")
    assert titles(out) == ["? ship friday"], "? is a sigil in the list, not the ask mode"


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


def test_menu_on_a_question_offers_the_resolution(run, logged):
    path = logged("? why is the sky green", 5)
    _, out = run("menu", str(path), "it is blue")
    assert titles(out)[0] == 'Decide "why is the sky green | it is blue"', "the first row decides"


@pytest.mark.parametrize(
    "action, before, after, printed",
    [
        ("keep", None, "reading docs\n", "reading docs"),
        ("mark", ". fix the build", "* fix the build\n", "* fix the build"),
    ],
)
def test_act_runs_the_action_on_the_argument(run, folder, logged, action, before, after, printed):
    arg = str(logged(before, 5)) if before else "reading docs"
    code, out = run("act", action, arg)
    assert code == 0 and out.strip() == printed, f"act {action} behaves as `wisp {action}`"
    (file,) = folder.iterdir()
    assert file.read_text() == after, "the file reflects the action"


def test_act_copy_puts_the_text_on_the_clipboard(run, mocker):
    copy = mocker.patch("wisp.cli.macos.copy")
    code, out = run("act", "copy", "meeting with L")
    assert code == 0 and out.strip() == "meeting with L", "copy echoes what it copied"
    copy.assert_called_once_with("meeting with L")


def test_act_open_opens_the_file(run, mocker):
    opened = mocker.patch("wisp.cli.macos.open")
    code, out = run("act", "open", "/log/x.md")
    assert code == 0 and out.strip() == "/log/x.md", "open echoes the path"
    opened.assert_called_once_with(Path("/log/x.md"))


def test_act_trash_moves_the_file(run, logged, mocker):
    trash = mocker.patch("wisp.cli.macos.trash")
    path = logged("reading docs", 5)
    code, out = run("act", "trash", str(path))
    assert code == 0 and out.strip() == "reading docs", "trash echoes the text"
    trash.assert_called_once_with(path)


def test_act_refuses_an_unknown_action(run, capsys):
    code, _ = run("act", "explode", "x")
    assert code == 2, "an action the plist could not have emitted is a usage error"


def test_decide_writes_the_resolution_and_echoes_the_line(run, logged):
    path = logged("? why is the sky green", 5)
    code, out = run("decide", str(path), "it", "is", "blue")
    assert code == 0 and out.strip() == "= why is the sky green | it is blue", "decide echoes"
    assert path.read_text() == "= why is the sky green | it is blue\n", "the file is settled"


def test_decide_with_a_blank_resolution_changes_nothing(run, logged):
    path = logged("? why is the sky green", 5)
    code, _ = run("decide", str(path), "  ")
    assert code == 1, "a blank resolution is refused"
    assert path.read_text() == "? why is the sky green\n", "the question stays open"


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


@pytest.mark.parametrize("text", ["   ", ".", ". ", "!  "])
def test_rename_refuses_a_bare_sigil(run, sample, text):
    path = sample[3]
    code, _ = run("rename", str(path), text)
    assert code == 1, f"{text!r} is not a log line"
    assert path.read_text() == "reading docs\n", "the record is untouched"


def test_trash_sends_the_file_to_the_trash(run, sample, mocker):
    trash = mocker.patch("wisp.cli.macos.trash")
    path = sample[0]
    code, out = run("trash", str(path))
    assert code == 0 and out.strip() == "making API v1", "trash should echo the text"
    trash.assert_called_once_with(path)


@pytest.mark.parametrize(
    "argv",
    [["mark"], ["decide", "it is blue"], ["rename", "new text"], ["trash"], ["menu", ""]],
)
def test_a_missing_record_is_reported_not_raised(run, notify, argv):
    verb, rest = argv[0], argv[1:]
    code, _ = run(verb, "/nowhere/nope.md", *rest)
    assert code == 1, f"{verb} of a missing file should fail cleanly"
    notify.assert_called_once_with("No such record: /nowhere/nope.md")


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
    _, out = run("ask-filter", "today summary")
    (row,) = rows(out)
    assert row["title"] == present.NO_SERVER, "without a server the only row says how to get one"
    assert row["valid"] is False, "and it cannot be actioned"


def test_question_offers_to_ask_then_lists_the_log(run, served, sample):
    _, out = run("ask-filter", "api")
    assert titles(out) == ['Ask "api"', "testing api manually", "making API v1"], (
        "the Ask row first, then the log lines the words match, as `l api` lists them"
    )
    ask = rows(out)[0]
    assert ask["subtitle"] == "↩ asks the model about 2 lines matching api", (
        "the Ask row says how many lines go and what they match"
    )
    assert ask["arg"] == "api" and ask["variables"] == {"action": "ask"}, (
        "↩ should ask with the bare question"
    )


def test_bare_ask_lists_the_whole_log_newest_first(run, served, sample):
    _, out = run("ask-filter", "")
    assert titles(out) == list(reversed(LINES)), "the whole log as `l` shows it, no Ask row"


def test_ask_rows_are_the_log_rows(run, served, logged):
    logged(". document api", 5)
    logged("api v1", 1)
    _, out = run("ask-filter", "api")
    assert rows(out)[1:] == rows(run("filter", "api")[1])[1:], (
        "under the Ask row, `ask api` and `l api` give the same rows"
    )


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
    stream = mocker.patch("wisp.oracle.stream")
    code, out = run("ask", "--dry-run", "today summary")
    assert code == 0 and out.startswith("today summary\n") and "making API v1" in out, (
        "dry run prints what the model would be sent"
    )
    stream.assert_not_called()
    notify.assert_not_called()


def test_ask_without_a_server(run, sample, notify):
    code, _ = run("ask", "today summary")
    assert code == 1, "no server, no answer"
    notify.assert_called_once_with(present.NO_SERVER)


def test_ask_failures_become_messages(run, served, sample, mocker, notify):
    model_fails(mocker, oracle.ModelError("Model not reachable at http://h"))
    code, _ = run("ask", "today summary")
    assert code == 1, "a model failure fails the command"
    notify.assert_called_with("Model not reachable at http://h")


def test_ask_with_blank_question(run, served, sample, notify):
    code, _ = run("ask", " ")
    assert code == 1, "nothing to ask"


def test_ask_with_a_bare_job_flag_fails_cleanly(env, clock, capsys):
    code = cli.run(["ask", "today summary", "--job"], env, NOW, clock)
    assert code == 2, "a flag without its value is a usage error, not a traceback"
    assert "--job" in capsys.readouterr().err, "and the message names the flag"


@pytest.mark.parametrize(
    "argv, expected",
    [
        (["today"], cli.AskArgs(question="today")),
        (["--dry-run", "today", "summary"], cli.AskArgs(question="today summary", dry_run=True)),
        (["today", "--keep"], cli.AskArgs(question="today", keep=True)),
        (["--job", "/j", "x"], cli.AskArgs(question="x", job="/j")),
        (["--", "--keep", "it"], cli.AskArgs(question="--keep it")),
        (["--thread", "/t", "more"], cli.AskArgs(question="more", thread="/t")),
    ],
)
def test_ask_args(argv, expected):
    assert cli.AskArgs.parse(argv) == expected, f"{argv} should parse as {expected}"


def test_question_row_counts_only_the_lines_that_fit(run, env, sample):
    env["oracle_apple"] = "1"
    _, out = run("ask-filter", "today summary")
    assert rows(out)[0]["subtitle"] == "↩ asks the model about 5 lines", (
        "five short lines fit, and words matching none of them count nothing"
    )


def test_ask_sends_old_matching_lines_the_budget_would_cut(run, served, logged, mocker):
    small = oracle.Llama("http://127.0.0.1:8080", budget=60)
    mocker.patch("wisp.oracle.backend", return_value=small)
    logged("api work", 60 * 24 * 30)
    for n in range(1, 10):
        logged(f"line {n}", n)
    _, out = run("ask", "--dry-run", "api")
    assert "api work" in out, "the old match is sent"
    assert out.count("\n") < 12, "but the budget still holds"


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
    model_fails(mocker, oracle.ModelError("Model not reachable at http://h"))
    job = tmp_path / "jobs" / "j1"
    code, _ = run("ask", "--job", str(job), "today summary")
    assert code == 1 and view.Job(job).error() == "Model not reachable at http://h", (
        "the failure goes to the job, not to a notification"
    )
    notify.assert_not_called()


def test_ask_apple_errors_are_messages(run, env, sample, mocker, notify):
    env["oracle_apple"] = "1"
    mocker.patch("wisp.oracle.apple.respond", side_effect=apple.AppleError("not enabled"))
    code, _ = run("ask", "today summary")
    assert code == 1, "an Apple failure fails the command"
    notify.assert_called_with("not enabled")


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
    assert view.Job(job).started() == NOW, "the job is stamped before the process starts"


def test_view_polls_a_running_job(run, served, sample, mocker, tmp_path):
    popen = mocker.patch("wisp.cli.subprocess.Popen")
    job = view.Job(tmp_path / "jobs" / "j1")
    job.start(NOW)
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


def test_menu_on_a_question_decides_with_what_is_typed(run, logged):
    path = logged("? why is the sky green", 5)
    _, out = run("menu", str(path), "it is blue")
    assert titles(out) == [
        'Decide "why is the sky green | it is blue"',
        "Open",
        "Rename",
        "Copy",
        "Trash",
    ], "the typed text is the answer, the other actions stay"


def test_check_reports_the_configuration(run, served, sample, mocker, env):
    mocker.patch("wisp.oracle.Llama.check", return_value="server up")
    code, out = run("check")
    assert code == 0, "check always succeeds; it reports"
    assert out.splitlines() == [
        f"log folder   {env['log_folder']} (5 records)",
        f"data folder  {env['alfred_workflow_data']}",
        f"jobs folder  {env['alfred_workflow_data']}/jobs",
        "model        server up",
    ], "one line per setting, the model line from the backend"


def test_check_without_a_folder_or_a_model(run, env):
    _, out = run("check")
    assert out.splitlines()[0] == f"log folder   {env['log_folder']} (missing, made on first log)"
    assert out.splitlines()[-1] == f"model        {present.NO_SERVER}", "no backend, the same hint"


@pytest.mark.parametrize("method", ["begin", "progress", "finish", "fail"])
def test_notify_and_job_answer_the_same_calls(method, tmp_path):
    assert callable(getattr(cli.Notify(), method)) and callable(
        getattr(view.Job(tmp_path), method)
    ), "ask talks to one sink, whichever it was given"


def test_notify_tells_the_person_at_each_step(notify):
    sink = cli.Notify()
    sink.begin(5)
    sink.progress("You")
    sink.finish("You read docs.")
    sink.fail("Model not reachable")
    assert [c.args[0] for c in notify.call_args_list] == [
        "Asking about 5 lines…",
        "You read docs.",
        "Model not reachable",
    ], "begin, finish and fail notify; progress is silent"


def test_job_finish_keeps_the_final_text(tmp_path):
    job = view.Job(tmp_path)
    job.progress("You rea")
    job.finish("You read docs.")
    assert job.partial() == "You read docs." and job.done(), "finish writes the answer and done"


def test_filter_by_a_day_lists_that_day_and_still_offers_the_text(run, logged):
    logged("standup", 60 * 24 + 10)
    logged("review", 10)
    _, out = run("filter", "yesterday")
    assert titles(out) == ['Log "yesterday"', "standup"], (
        "the list narrows to yesterday while the offer keeps what was typed"
    )


def test_ask_about_a_day_sends_that_day_only(run, served, logged):
    logged("standup", 60 * 24 + 10)
    logged("review", 10)
    _, out = run("ask", "--dry-run", "what did I do yesterday")
    assert "standup" in out and "review" not in out, (
        "a day in the question limits the log to that day, whatever the other words"
    )


def test_ask_row_counts_within_the_window(run, served, logged):
    logged("standup", 60 * 24 + 10)
    logged("api review", 60 * 24 + 5)
    logged("review", 10)
    _, out = run("ask-filter", "api yesterday")
    assert rows(out)[0]["subtitle"] == "↩ asks the model about 1 line matching api", (
        "the window bounds the lines, the words pick within it"
    )


@pytest.fixture
def answered(tmp_path):
    first = view.Job(tmp_path / "jobs" / "j1")
    first.start(NOW)
    first.finish("Two.")
    first.remember("how many api lines", "Two.")
    return first


def test_ask_with_a_thread_continues_the_conversation(run, served, sample, mocker, answered):
    model_says(mocker, "Both today.")
    second = answered.folder.parent / "j2"
    code, out = run("ask", "--job", str(second), "--thread", str(answered.folder), "when")
    assert code == 0 and out == "Both today.\n", "the follow-up is answered"
    assert view.Job(second).turns() == [
        ("how many api lines", "Two."),
        ("when", "Both today."),
    ], "the new job carries every turn so far"
    assert answered.turns() == [("how many api lines", "Two.")], "the earlier job is untouched"


def test_ask_with_a_thread_sends_the_earlier_turns(run, served, sample, mocker, answered):
    seen = {}

    def respond(self, messages, on_text):
        seen["messages"] = messages
        return "ok"

    mocker.patch("wisp.oracle.Llama.respond", respond)
    run("ask", "--thread", str(answered.folder), "when")
    roles = [m["role"] for m in seen["messages"]]
    assert roles == ["system", "user", "assistant", "user"], "the thread precedes the question"
    assert seen["messages"][1]["content"].startswith("how many api lines"), (
        "the log goes with the first question"
    )
    assert seen["messages"][2]["content"] == "Two." and seen["messages"][3]["content"] == "when", (
        "then the earlier answer and the new question"
    )


def test_view_with_a_thread_starts_a_follow_up_job(run, served, sample, mocker, answered):
    popen = mocker.patch("wisp.cli.subprocess.Popen")
    served["thread"] = str(answered.folder)
    _, out = run("view", "when")
    argv = popen.call_args.args[0]
    job = json.loads(out)["variables"]["job"]
    assert argv[1:] == [
        "-m",
        "wisp",
        "ask",
        "--job",
        job,
        "--thread",
        str(answered.folder),
        "when",
    ], "the background ask gets the thread"


def test_ask_more_offers_a_follow_up_on_the_thread(run, served, sample, answered):
    served["thread"] = str(answered.folder)
    _, out = run("ask-more", "when")
    (row,) = rows(out)
    assert row["title"] == 'Ask "when"' and row["variables"] == {
        "action": "ask",
        "thread": str(answered.folder),
    }, "the row asks with the thread carried along"
    assert row["subtitle"] == 'follows up on "how many api lines" · 2 lines', (
        "the row says what it follows up on and what the model has"
    )


def test_ask_more_with_nothing_typed_waits(run, served, answered):
    served["thread"] = str(answered.folder)
    _, out = run("ask-more", "")
    (row,) = rows(out)
    assert row["valid"] is False and row["title"] == 'Type a follow-up to "how many api lines"', (
        "nothing to ask yet"
    )


TEMPLATE = "# release\n- [ ] bump\n- [ ] tag\n"


@pytest.fixture
def template(folder, stamps):
    folder.mkdir()
    path = folder / "release.md"
    path.write_text(TEMPLATE)
    stamps[path.name] = NOW
    return path


def test_start_writes_a_run_and_prints_its_path(run, folder, template, stamps):
    code, out = run("start", str(template))
    assert code == 0 and out.strip() == str(folder / "release-2.md"), "start prints the run"
    assert (folder / "release-2.md").read_text() == ". release\n- [ ] bump\n- [ ] tag\n", (
        "the run is a task with the boxes cleared"
    )


def test_start_continues_an_open_run_unless_fresh(run, folder, template, stamps, env):
    _, first = run("start", str(template))
    stamps["release-2.md"] = NOW
    _, again = run("start", str(template))
    assert again == first, "a second start hands back the open run"
    env["fresh"] = "1"
    _, fresh = run("start", str(template))
    assert fresh.strip() == str(folder / "release-3.md"), "fresh starts another run anyway"


def test_start_with_text_creates_the_template(run, folder):
    code, out = run("start", "# packing")
    assert code == 0 and out.strip() == str(folder / "packing.md"), "start prints the template"
    assert (folder / "packing.md").read_text() == "# packing\n", "a new template has no steps"
    assert names(folder) == ["packing.md"], "no run is started for an empty new template"


def test_tick_reads_the_path_variable_and_prints_the_line(run, template, env):
    env["path"] = str(template)
    code, out = run("tick", "2")
    assert code == 0 and out.strip() == "- [x] tag", "tick prints the flipped line"
    assert template.read_text() == "# release\n- [ ] bump\n- [x] tag\n", "the file is ticked"


def test_tick_of_a_non_step_fails_quietly(run, template, env):
    env["path"] = str(template)
    code, _ = run("tick", "9")
    assert code == 1, "a bad item number is a bad argument, like blank text"


def test_add_appends_a_step_and_prints_it(run, template, env):
    env["path"] = str(template)
    code, out = run("add", "publish", "notes")
    assert code == 0 and out.strip() == "- [ ] publish notes", "add prints the new line"
    assert template.read_text().endswith("- [ ] publish notes\n"), "the step is appended"


def test_items_lists_the_steps(run, template):
    _, out = run("items", str(template), "")
    assert titles(out) == ["☐ bump", "☐ tag"], "items emits one row per step"


def test_items_narrows_and_offers_to_add(run, template):
    _, out = run("items", str(template), "ta")
    assert titles(out) == ["☐ tag"], "typed text narrows the steps"
    _, out = run("items", str(template), "ship")
    assert titles(out) == ['Add "ship"'], "unmatched text is offered as a new step"


@pytest.mark.parametrize("action", ["start", "tick", "add"])
def test_act_dispatches_the_checklist_actions(run, template, env, action):
    env["path"] = str(template)
    argument = {"start": str(template), "tick": "1", "add": "ship"}[action]
    code, out = run("act", action, argument)
    assert code == 0 and out.strip(), f"act {action} behaves as `wisp {action}`"


def test_menu_on_a_template_offers_start_then_steps(run, template):
    _, out = run("menu", str(template), "")
    assert titles(out)[:2] == ["Start", "Steps"], "a template's menu starts or edits it"


def test_menu_on_a_template_with_an_open_run_continues(run, folder, template, stamps):
    run("start", str(template))
    stamps["release-2.md"] = NOW
    _, out = run("menu", str(template), "")
    assert titles(out)[0] == "Continue", "with a run open, the menu continues it"


def test_filter_lists_checklists_with_their_steps(run, template):
    _, out = run("filter", "#")
    assert rows(out) == [
        {
            **rows(out)[0],
            "title": "# release",
            "subtitle": "2 steps · 15:00 today",
            "icon": {"path": "icons/checklist.png"},
        }
    ], "l # lists templates with their step count"


def test_items_and_tick_trim_the_path_alfred_hands_over(run, template, env):
    _, out = run("items", f"{template}\n", "")
    assert titles(out) == ["☐ bump", "☐ tag"], "a Run Script's output ends in a newline"
    env["path"] = f"{template}\n"
    code, out = run("tick", "1")
    assert code == 0 and out.strip() == "- [x] bump", "tick reads the path trimmed"
