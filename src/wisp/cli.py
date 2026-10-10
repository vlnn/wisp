from __future__ import annotations

import json
import os
import sys
import urllib.error
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Callable

from wisp import macos, oracle, present, records

DEFAULT_FOLDER = "~/log"
QUESTION = "?"
DRY_RUN = "--dry-run"
USAGE = "usage: wisp filter|keep|rename-filter|rename|trash|ask ..."


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
        rows = present.question_rows(
            question, ctx.answers(), ctx.now, len(ctx.logs()), ctx.server() is not None
        )
        return emit(rows)
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
    question = " ".join(arg for arg in args if arg != DRY_RUN).strip()
    if not question:
        return 1
    server = ctx.server()
    if server is None:
        return fail(present.NO_SERVER)
    logs = ctx.logs()
    if dry_run:
        return say(
            "\n\n".join(m["content"] for m in reversed(oracle.prompt(question, logs, ctx.now)))
        )
    macos.notify(f"Asking about {len(logs)} lines…")
    try:
        answer = oracle.ask(question, logs, ctx.now, server, oracle.post)
    except urllib.error.HTTPError as error:
        return fail(f"Model answered {error.code} at {server.url}")
    except (urllib.error.URLError, TimeoutError, OSError):
        return fail(f"Model not reachable at {server.url}")
    except (KeyError, IndexError, TypeError, ValueError):
        return fail("Model gave no answer")
    path = oracle.remember(oracle.answers_folder(ctx.env), question, answer)
    macos.notify(answer)
    return say(str(path))


COMMANDS: dict[str, Callable[[list[str], Context], int]] = {
    "filter": filter_command,
    "keep": keep_command,
    "rename-filter": rename_filter_command,
    "rename": rename_command,
    "trash": trash_command,
    "ask": ask_command,
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
