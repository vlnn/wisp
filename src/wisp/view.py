from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from wisp import apple, oracle
from wisp.oracle import visible

RERUN = 0.2
GIVE_UP = max(oracle.TIMEOUT, apple.TIMEOUT) + 30
PARTIAL, DONE, ERROR, STARTED, THREAD = "partial.md", "done", "error", "started", "thread.json"
Turn = tuple[str, str]
NO_ANSWER = f"The model gave no answer in {GIVE_UP} seconds"


class Job:
    def __init__(self, folder: Path | str):
        self.folder = Path(folder)

    def partial(self) -> str:
        return self.read(PARTIAL)

    def done(self) -> bool:
        return (self.folder / DONE).exists()

    def error(self) -> str | None:
        return self.read(ERROR) or None

    def start(self, now: datetime) -> None:
        self.write(STARTED, now.isoformat())

    def started(self) -> datetime | None:
        stamp = self.read(STARTED)
        return datetime.fromisoformat(stamp) if stamp else None

    def stale(self, now: datetime) -> bool:
        started = self.started()
        return started is None or (now - started).total_seconds() > GIVE_UP

    def begin(self, lines: int) -> None:
        pass

    def progress(self, text: str) -> None:
        self.write(PARTIAL, text)

    def finish(self, answer: str) -> None:
        self.write(PARTIAL, answer)
        self.write(DONE, "")

    def fail(self, message: str) -> None:
        self.write(ERROR, message)

    def turns(self) -> list[Turn]:
        kept = self.read(THREAD)
        return [(q, a) for q, a in json.loads(kept)] if kept else []

    def remember(self, question: str, answer: str, after: Job | None = None) -> None:
        turns = (after.turns() if after else []) + [(question, answer)]
        self.write(THREAD, json.dumps(turns, ensure_ascii=False))

    def read(self, name: str) -> str:
        try:
            return (self.folder / name).read_text(encoding="utf-8")
        except OSError:
            return ""

    def write(self, name: str, text: str) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        scratch = self.folder / f".{name}.{os.getpid()}"
        scratch.write_text(text, encoding="utf-8")
        scratch.replace(self.folder / name)


def job_id() -> str:
    return f"{datetime.now():%Y%m%d-%H%M%S-%f}-{os.getpid()}"


def starting(question: str, job: Job, lines: int) -> dict:
    return {
        "rerun": RERUN,
        "variables": {"job": str(job.folder)},
        "response": f'_Asking about {lines} lines: "{question}"…_',
        "behaviour": {"scroll": "end"},
    }


def showing(question: str, job: Job, now: datetime) -> dict:
    error = job.error()
    if error:
        return failed(error)
    text = visible(job.partial())
    if job.done():
        return {
            "response": text,
            "footer": f'"{question}" · ↩ copy · ⌥↩ keep as a file and open it · ⌘↩ follow up',
            "variables": {"job": "", "question": question, "thread": str(job.folder)},
            "behaviour": {"response": "replace", "scroll": "end"},
        }
    if job.stale(now):
        return failed(NO_ANSWER)
    return {
        "rerun": RERUN,
        "variables": {"job": str(job.folder)},
        "response": text,
        "behaviour": {"response": "replace", "scroll": "end"},
    }


def failed(message: str) -> dict:
    return {"response": f"**{message}**", "variables": {"job": ""}}
