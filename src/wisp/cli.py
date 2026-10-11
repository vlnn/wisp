from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from wisp import apple, macos, oracle, present, records, view

DEFAULT_FOLDER = "~/log"
DRY_RUN = "--dry-run"
JOB = "--job"
KEEP = "--keep"
END_OF_FLAGS = "--"


class Usage(Exception):
    pass


@dataclass(frozen=True)
class AskArgs:
    question: str
    dry_run: bool = False
    keep: bool = False
    job: str | None = None

    @classmethod
    def parse(cls, argv: list[str]) -> AskArgs:
        flags: dict = {}
        words: list[str] = []
        rest = list(argv)
        while rest:
            arg = rest.pop(0)
            if arg == END_OF_FLAGS:
                words.extend(rest)
                break
            if arg == DRY_RUN:
                flags["dry_run"] = True
            elif arg == KEEP:
                flags["keep"] = True
            elif arg == JOB:
                if not rest:
                    raise Usage(f"{JOB} needs a folder")
                flags["job"] = rest.pop(0)
            else:
                words.append(arg)
        return cls(" ".join(words).strip(), **flags)


class Context:
    def __init__(
        self,
        env: Mapping[str, str],
        now: datetime,
        created: records.Clock,
        changed: records.Clock,
    ):
        self.env = env
        self.now = now
        self.created = created
        self.changed = changed
        self.folder = log_folder(env)

    def logs(self) -> list[records.Record]:
        return records.read_folder(self.folder, self.created, self.changed)

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
    return emit(present.rows((args[0] if args else "").strip(), ctx.logs(), ctx.now))


def ask_filter_command(args: list[str], ctx: Context) -> int:
    question = (args[0] if args else "").strip()
    server = ctx.server()
    logs = ctx.logs()
    lines = len(oracle.evidence(logs, oracle.budget_for(server)).splitlines()) if server else 0
    return emit(present.question_rows(question, logs, ctx.now, lines, bool(server)))


def keep_command(args: list[str], ctx: Context) -> int:
    text = records.normalise(" ".join(args))
    records.keep(ctx.folder, text)
    return say(text)


def rename_filter_command(args: list[str], ctx: Context) -> int:
    return emit([present.rename_row(args[0] if args else "")])


def rename_command(args: list[str], ctx: Context) -> int:
    path, text = Path(args[0]), " ".join(args[1:]).strip()
    records.rename(path, text)
    return say(text)


def trash_command(args: list[str], ctx: Context) -> int:
    path = Path(args[0])
    text = records.first_line(path.read_text(encoding="utf-8"))
    macos.trash(path)
    return say(text)


def menu_command(args: list[str], ctx: Context) -> int:
    record = records.read_record(Path(args[0]), ctx.created, ctx.changed)
    return emit(present.menu_rows(record, args[1] if len(args) > 1 else ""))


def decide_filter_command(args: list[str], ctx: Context) -> int:
    record = records.read_record(Path(args[0]), ctx.created, ctx.changed)
    return emit([present.decide_row(record, args[1] if len(args) > 1 else "")])


def decide_command(args: list[str], ctx: Context) -> int:
    path, resolution = Path(args[0]), " ".join(args[1:]).strip()
    records.decide(path, resolution)
    return say(records.first_line(path.read_text(encoding="utf-8")))


def mark_command(args: list[str], ctx: Context) -> int:
    path = records.mark(Path(args[0]))
    return say(records.first_line(path.read_text(encoding="utf-8")))


def ask_command(args: list[str], ctx: Context) -> int:
    asked = AskArgs.parse(args)
    dry_run, keep, question = asked.dry_run, asked.keep, asked.question
    job = view.Job(asked.job) if asked.job else None
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
    if job:
        job.progress(answer)
        job.finish()
    else:
        macos.notify(answer)
    if keep:
        return say(str(keep_answer(ctx, question, answer)))
    return say(answer)


def keep_answer(ctx: Context, question: str, answer: str) -> Path:
    return oracle.remember(oracle.answers_folder(ctx.env), question, answer)


def keep_answer_command(args: list[str], ctx: Context) -> int:
    if len(args) < 2 or not args[0].strip() or not args[1].strip():
        return 1
    return say(str(keep_answer(ctx, args[0], args[1])))


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
    "mark": mark_command,
    "decide-filter": decide_filter_command,
    "decide": decide_command,
    "menu": menu_command,
    "ask-filter": ask_filter_command,
    "ask": ask_command,
    "view": view_command,
    "keep-answer": keep_answer_command,
}

USAGE = "usage: wisp " + "|".join(COMMANDS) + " ..."


def run(
    argv: list[str],
    env: Mapping[str, str],
    now: datetime | None = None,
    created: records.Clock | None = None,
    changed: records.Clock | None = None,
) -> int:
    if not argv or argv[0] not in COMMANDS:
        print(USAGE, file=sys.stderr)
        return 2
    ctx = Context(
        env, now or datetime.now(), created or records.birth_time, changed or records.modified_time
    )
    try:
        return COMMANDS[argv[0]](argv[1:], ctx)
    except records.Blank:
        return 1
    except FileNotFoundError as error:
        return fail(f"No such record: {error.filename}")
    except Usage as error:
        print(f"{USAGE}\n{error}", file=sys.stderr)
        return 2


def main() -> None:
    sys.exit(run(sys.argv[1:], os.environ))
