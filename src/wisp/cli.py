from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Callable

from wisp import apple, macos, oracle, present, records, view

DEFAULT_FOLDER = "~/log"
QUESTION = "?"
DRY_RUN = "--dry-run"
JOB = "--job"
USAGE = "usage: wisp filter|keep|rename-filter|rename|trash|ask|view ..."


class Context:
    def __init__(self, env: Mapping[str, str], now: datetime, created: records.Created):
        self.env = env
        self.now = now
        self.created = created
        self.folder = log_folder(env)

    def logs(self) -> list[records.Record]:
        return records.read_folder(self.folder, self.created)

    def answers(self) -> list[oracle.Answer]:
        return oracle.read_answers(oracle.answers_folder(self.env), self.created)

    def server(self) -> oracle.Server | None:
        return oracle.server(self.env)

    def data(self) -> Path:
        return oracle.answers_folder(self.env).parent

    def jobs(self) -> Path:
        cache = self.env.get("alfred_workflow_cache")
        return Path(cache) / "jobs" if cache else self.data() / "jobs"

    def lines_sent(self, server: oracle.Server) -> int:
        return len(oracle.evidence(self.logs(), oracle.budget_for(server)).splitlines())


def log_folder(env: Mapping[str, str]) -> Path:
    return Path(os.path.expanduser(env.get("log_folder") or DEFAULT_FOLDER))


def emit(items: list) -> int:
    print(json.dumps({"items": items}, ensure_ascii=False))
    return 0


def say(text: str) -> int:
    print(text)
    return 0


def fail(text: str) -> int:
    macos.notify(text)
    print(text, file=sys.stderr)
    return 1


def filter_command(args: list[str], ctx: Context) -> int:
    query = (args[0] if args else "").strip()
    if query.startswith(QUESTION):
        question = query[len(QUESTION) :].strip()
        server = ctx.server()
        lines = ctx.lines_sent(server) if server else 0
        return emit(present.question_rows(question, ctx.answers(), ctx.now, lines, bool(server)))
    return emit(present.rows(query, ctx.logs(), ctx.now))


def keep_command(args: list[str], ctx: Context) -> int:
    text = " ".join(args).strip()
    if not text:
        return 1
    records.keep(ctx.folder, text)
    return say(text)


def rename_filter_command(args: list[str], ctx: Context) -> int:
    return emit([present.rename_row(args[0] if args else "")])


def rename_command(args: list[str], ctx: Context) -> int:
    path, text = Path(args[0]), " ".join(args[1:]).strip()
    if not text:
        return 1
    records.rename(path, text)
    return say(text)


def trash_command(args: list[str], ctx: Context) -> int:
    path = Path(args[0])
    text = records.first_line(path.read_text(encoding="utf-8"))
    macos.trash(path)
    return say(text)


def ask_command(args: list[str], ctx: Context) -> int:
    dry_run = DRY_RUN in args
    job = view.Job(args[args.index(JOB) + 1]) if JOB in args else None
    question = " ".join(words_after_flags(args)).strip()
    if not question:
        return 1
    server = ctx.server()
    if server is None:
        return report(present.NO_SERVER, job)
    logs = ctx.logs()
    messages = oracle.prompt(question, logs, ctx.now, oracle.budget_for(server))
    if dry_run:
        return say("\n\n".join(m["content"] for m in reversed(messages)))
    if job is None:
        macos.notify(f"Asking about {len(logs)} lines…")
    try:
        answer = oracle.answer(server, messages, job.progress if job else None, str(ctx.data()))
    except urllib.error.HTTPError as error:
        return report(f"Model answered {error.code} at {server.url}", job)
    except (urllib.error.URLError, TimeoutError, OSError):
        return report(f"Model not reachable at {server.url}", job)
    except apple.AppleError as error:
        return report(str(error), job)
    except (KeyError, IndexError, TypeError, ValueError):
        return report("Model gave no answer", job)
    path = oracle.remember(oracle.answers_folder(ctx.env), question, answer)
    if job:
        job.progress(answer)
        job.finish(path)
    else:
        macos.notify(answer)
    return say(str(path))


def words_after_flags(args: list[str]) -> list[str]:
    words = []
    skip = False
    for arg in args:
        if skip or arg == DRY_RUN:
            skip = False
            continue
        if arg == JOB:
            skip = True
            continue
        words.append(arg)
    return words


def report(message: str, job: view.Job | None) -> int:
    if job:
        job.fail(message)
        print(message, file=sys.stderr)
        return 1
    return fail(message)


def view_command(args: list[str], ctx: Context) -> int:
    question = (args[0] if args else "").strip()
    server = ctx.server()
    if server is None:
        return emit_view(view.failed(present.NO_SERVER))
    running = ctx.env.get("job")
    if running:
        return emit_view(view.showing(question, view.Job(running)))
    job = view.Job(ctx.jobs() / view.job_id())
    job.folder.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [sys.executable, "-m", "wisp", "ask", JOB, str(job.folder), question],
        env=dict(ctx.env),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return emit_view(view.starting(question, job, ctx.lines_sent(server)))


def emit_view(shown: dict) -> int:
    print(json.dumps(shown, ensure_ascii=False))
    return 0


COMMANDS: dict[str, Callable[[list[str], Context], int]] = {
    "filter": filter_command,
    "keep": keep_command,
    "rename-filter": rename_filter_command,
    "rename": rename_command,
    "trash": trash_command,
    "ask": ask_command,
    "view": view_command,
}


def run(
    argv: list[str],
    env: Mapping[str, str],
    now: datetime | None = None,
    created: records.Created | None = None,
) -> int:
    if not argv or argv[0] not in COMMANDS:
        print(USAGE, file=sys.stderr)
        return 2
    ctx = Context(env, now or datetime.now(), created or records.birth_time)
    return COMMANDS[argv[0]](argv[1:], ctx)


def main() -> None:
    sys.exit(run(sys.argv[1:], os.environ))
