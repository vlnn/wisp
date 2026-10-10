import pytest

from wisp import view


@pytest.fixture
def job(tmp_path):
    return view.Job(tmp_path / "jobs" / "abc")


def test_job_starts_empty(job):
    assert job.partial() == "" and job.done() is None and job.error() is None, (
        "a fresh job has no text, no result and no error"
    )


def test_job_records_progress(job):
    job.progress("You ")
    job.progress("You read")
    assert job.partial() == "You read", "the latest text wins"


def test_job_finishes_with_the_answer_path(job, tmp_path):
    job.progress("You read docs.")
    job.finish(tmp_path / "answers" / "q.md")
    assert job.done() == tmp_path / "answers" / "q.md", "done names the saved answer"
    assert job.partial() == "You read docs.", "the text stays readable after finishing"


def test_job_fails_with_a_message(job):
    job.fail("Model not reachable at http://h")
    assert job.error() == "Model not reachable at http://h", "the error is kept for the view"


def test_job_ids_are_unique():
    assert view.job_id() != view.job_id(), "two jobs started together must not collide"


def test_starting_view_asks_to_rerun(job):
    shown = view.starting("today summary", job, lines=5)
    assert shown["rerun"] == view.RERUN, "Alfred should poll"
    assert shown["variables"] == {"job": str(job.folder)}, "the job travels in a variable"
    assert "today summary" in shown["response"] and "5 lines" in shown["response"], (
        "the view says what is being asked"
    )


def test_running_view_shows_the_text_so_far(job):
    job.progress("<think>hm</think>You rea")
    shown = view.showing("today summary", job)
    assert shown["response"] == "You rea" and shown["rerun"] == view.RERUN, (
        "partial text, thinking hidden, keep polling"
    )
    assert shown["behaviour"] == {"response": "replace", "scroll": "end"}, "replace and follow"


def test_finished_view_stops_polling_and_offers_keys(job, tmp_path):
    path = tmp_path / "answers" / "today-summary.md"
    job.progress("You read docs.")
    job.finish(path)
    shown = view.showing("today summary", job)
    assert "rerun" not in shown, "no more polling"
    assert shown["response"] == "You read docs.", "the answer, nothing else, so ↩ copies just it"
    assert shown["variables"] == {"job": "", "answer": str(path)}, "⌥↩ can open the saved file"
    assert shown["footer"] == '"today summary" · ↩ copy · ⌥↩ open the saved answer', (
        "the question moves to the footer"
    )


def test_failed_view_shows_the_error(job):
    job.fail("Model not reachable at http://h")
    shown = view.showing("today summary", job)
    assert "rerun" not in shown and shown["response"] == "**Model not reachable at http://h**", (
        "an error ends the view with the message"
    )
    assert shown["variables"] == {"job": ""}, "the job variable is cleared"
