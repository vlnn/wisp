from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Callable

from wisp import present, records

DEFAULT_FOLDER = "~/log"
USAGE = "usage: wisp filter|keep|rename-filter|rename|trash ..."


def log_folder(env: Mapping[str, str]) -> Path:
    return Path(os.path.expanduser(env.get("log_folder") or DEFAULT_FOLDER))


def emit(items: list) -> int:
    print(json.dumps({"items": items}, ensure_ascii=False))
    return 0


def say(text: str) -> int:
    print(text)
    return 0


def filter_command(args: list[str], folder: Path, now: datetime, created) -> int:
    query = args[0] if args else ""
    return emit(present.rows(query, records.read_folder(folder, created), now))


def keep_command(args: list[str], folder: Path, now: datetime, created) -> int:
    text = " ".join(args).strip()
    if not text:
        return 1
    records.keep(folder, text)
    return say(text)


def rename_filter_command(args: list[str], folder: Path, now: datetime, created) -> int:
    return emit([present.rename_row(args[0] if args else "")])


def rename_command(args: list[str], folder: Path, now: datetime, created) -> int:
    path, text = Path(args[0]), " ".join(args[1:]).strip()
    if not text:
        return 1
    records.rename(path, text)
    return say(text)


def trash_command(args: list[str], folder: Path, now: datetime, created) -> int:
    path = Path(args[0])
    text = records.first_line(path.read_text(encoding="utf-8"))
    records.trash(path)
    return say(text)


COMMANDS: dict[str, Callable[..., int]] = {
    "filter": filter_command,
    "keep": keep_command,
    "rename-filter": rename_filter_command,
    "rename": rename_command,
    "trash": trash_command,
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
    command = COMMANDS[argv[0]]
    return command(argv[1:], log_folder(env), now or datetime.now(), created or records.birth_time)


def main() -> None:
    sys.exit(run(sys.argv[1:], os.environ))
