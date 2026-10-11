from datetime import timedelta

import pytest

from conftest import NOW
from wisp import view


@pytest.fixture
def job(tmp_path):
    started = view.Job(tmp_path / "jobs" / "abc")
    started.start(NOW)
    return started


def test_job_starts_empty(job):
    assert job.partial() == "" and job.done() is False and job.error() is None, (
        "a fresh job has no text, no result and no error"
    )


def test_job_records_progress(job):
    job.progress("You ")
    job.progress("You read")
    assert job.partial() == "You read", "the latest text wins"


def test_job_finishes(job):
    job.finish("You read docs.")
    assert job.done() is True, "done says the answer is complete"
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
    shown = view.showing("today summary", job, NOW)
    assert shown["response"] == "You rea" and shown["rerun"] == view.RERUN, (
        "partial text, thinking hidden, keep polling"
    )
    assert shown["behaviour"] == {"response": "replace", "scroll": "end"}, "replace and follow"


def test_finished_view_stops_polling_and_offers_keys(job):
    job.finish("You read docs.")
    shown = view.showing("today summary", job, NOW)
    assert "rerun" not in shown, "no more polling"
    assert shown["response"] == "You read docs.", "the answer, nothing else, so ↩ copies just it"
    assert shown["variables"] == {"job": "", "question": "today summary"}, (
        "⌥↩ can save the answer under its question"
    )
    assert shown["footer"] == '"today summary" · ↩ copy · ⌥↩ keep as a file and open it', (
        "the question moves to the footer"
    )


def test_failed_view_shows_the_error(job):
    job.fail("Model not reachable at http://h")
    shown = view.showing("today summary", job, NOW)
    assert "rerun" not in shown and shown["response"] == "**Model not reachable at http://h**", (
        "an error ends the view with the message"
    )
    assert shown["variables"] == {"job": ""}, "the job variable is cleared"


def test_view_gives_up_on_a_dead_job(job):
    job.progress("You rea")
    late = NOW + timedelta(seconds=view.GIVE_UP + 1)
    shown = view.showing("today summary", job, late)
    assert "rerun" not in shown and shown["response"] == f"**{view.NO_ANSWER}**", (
        "a job past the deadline with no done or error is reported, not polled forever"
    )
    assert view.showing("today summary", job, NOW + timedelta(seconds=1))["rerun"] == view.RERUN, (
        "a young job is still polled"
    )


def test_view_gives_up_when_the_job_folder_is_gone(tmp_path):
    gone = view.Job(tmp_path / "jobs" / "cleared")
    shown = view.showing("today summary", gone, NOW)
    assert "rerun" not in shown and shown["response"] == f"**{view.NO_ANSWER}**", (
        "a job with no start stamp was cleared from under the view"
    )
