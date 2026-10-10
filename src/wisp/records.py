from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from itertools import count
from pathlib import Path
from typing import Callable

EXTENSION = ".md"
SLUG_LIMIT = 60
FALLBACK_SLUG = "note"

Created = Callable[[Path], datetime]


@dataclass(frozen=True)
class Record:
    path: Path
    text: str
    created: datetime


def birth_time(path: Path) -> datetime:
    stat = path.stat()
    return datetime.fromtimestamp(getattr(stat, "st_birthtime", stat.st_mtime))


def read_folder(folder: Path, created: Created = birth_time) -> list[Record]:
    if not folder.is_dir():
        return []
    return sorted((read_record(path, created) for path in record_files(folder)), key=newest_first)


def record_files(folder: Path) -> Iterable[Path]:
    return (
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix == EXTENSION and not path.name.startswith(".")
    )


def read_record(path: Path, created: Created) -> Record:
    return Record(path, first_line(path.read_text(encoding="utf-8")), created(path))


def first_line(content: str) -> str:
    return next((line.strip() for line in content.splitlines() if line.strip()), "")


def body(content: str) -> str:
    lines = content.splitlines()
    first = next((n for n, line in enumerate(lines) if line.strip()), len(lines))
    return "\n".join(lines[first + 1 :]).strip()


def newest_first(record: Record):
    return (-record.created.timestamp(), record.path.name)


def keep(folder: Path, text: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = free_path(folder, slug(text))
    write_text(path, text)
    return path


def rename(path: Path, text: str) -> Path:
    old = first_line(path.read_text(encoding="utf-8"))
    write_text(path, text)
    if slug(text) == slug(old):
        return path
    target = free_path(path.parent, slug(text))
    path.rename(target)
    return target


def write_text(path: Path, text: str) -> None:
    path.write_text(text.strip() + "\n", encoding="utf-8")


def slug(text: str) -> str:
    joined = "-".join(re.findall(r"\w+", text.casefold()))
    return joined[:SLUG_LIMIT].strip("-") or FALLBACK_SLUG


def free_path(folder: Path, name: str) -> Path:
    candidates = (folder / f"{name}{suffix}{EXTENSION}" for suffix in suffixes())
    return next(path for path in candidates if not path.exists())


def suffixes() -> Iterator[str]:
    yield ""
    for n in count(2):
        yield f"-{n}"
