from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from wisp.oracle import visible

RERUN = 0.2
PARTIAL, DONE, ERROR = "partial.md", "done", "error"


class Job:
    def __init__(self, folder: Path | str):
        self.folder = Path(folder)

    def partial(self) -> str:
        return self.read(PARTIAL)

    def done(self) -> Path | None:
        path = self.read(DONE)
        return Path(path) if path else None

    def error(self) -> str | None:
        return self.read(ERROR) or None

    def progress(self, text: str) -> None:
        self.write(PARTIAL, text)

    def finish(self, path: Path) -> None:
        self.write(DONE, str(path))

    def fail(self, message: str) -> None:
        self.write(ERROR, message)

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


def showing(question: str, job: Job) -> dict:
    error = job.error()
    if error:
        return {"response": f"**{error}**", "variables": {"job": ""}}
    text = visible(job.partial())
    done = job.done()
    if done:
        return {
            "response": text,
            "footer": f'"{question}" · ↩ copy · ⌥↩ open the saved answer',
            "variables": {"job": "", "answer": str(done)},
            "behaviour": {"response": "replace", "scroll": "end"},
        }
    return {
        "rerun": RERUN,
        "variables": {"job": str(job.folder)},
        "response": text,
        "behaviour": {"response": "replace", "scroll": "end"},
    }


def failed(message: str) -> dict:
    return {"response": f"**{message}**", "variables": {"job": ""}}
