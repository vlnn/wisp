from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from itertools import count
from pathlib import Path

EXTENSION = ".md"
SLUG_LIMIT = 60
FALLBACK_SLUG = "note"

Stamps = Callable[[Path], tuple[datetime, datetime]]


class Kind(Enum):
    LOG = ("", "Log", "")
    TASK = (".", "Task", "TODO")
    DONE = ("*", "Done", "DONE")
    NOTE = ("!", "Note", "NOTE")
    QUESTION = ("?", "Question", "QUESTION")
    DECISION = ("=", "Decision", "DECIDED")
    CHECKLIST = ("#", "Checklist", "CHECKLIST")

    @property
    def sigil(self) -> str:
        return self.value[0]

    @property
    def offer(self) -> str:
        return self.value[1]

    @property
    def spoken(self) -> str:
        return self.value[2]

    @property
    def icon(self) -> str:
        return f"icons/{self.name.lower()}.png"


SIGILS = {kind.sigil: kind for kind in Kind if kind.sigil}
TIGHT = {Kind.QUESTION, Kind.NOTE, Kind.DECISION}
SETTLED = {Kind.DONE, Kind.DECISION}
FLIPPED = {Kind.TASK: Kind.DONE, Kind.DONE: Kind.TASK, Kind.DECISION: Kind.QUESTION}
RESOLVED = " | "
BOX = re.compile(r"^(\s*[-*] \[)([ xX])(\] .*)$")
TICKED = {"x", "X"}
TAG = re.compile(r"(?<!\w)#[^\W\d_](?:[\w-]*\w)?")


class Blank(ValueError):
    pass


class NoSuchItem(ValueError):
    pass


@dataclass(frozen=True)
class Record:
    path: Path
    kind: Kind
    line: str
    created: datetime
    changed: datetime
    body: str = ""

    @classmethod
    def parsed(
        cls, path: Path, text: str, created: datetime, changed: datetime, body: str = ""
    ) -> Record:
        kind, line = parse(text)
        return cls(path, kind, line, created, changed, body)

    @property
    def text(self) -> str:
        return compose(self.kind, self.line)

    @property
    def tags(self) -> list[str]:
        return tags_in(self.line)


def parse(text: str) -> tuple[Kind, str]:
    kind = SIGILS.get(text[:1])
    if kind and (kind in TIGHT or len(text) == 1 or text[1].isspace()):
        return kind, text[1:].strip()
    return Kind.LOG, text


def compose(kind: Kind, line: str) -> str:
    return f"{kind.sigil} {line}" if kind.sigil else line


def normalise(text: str) -> str:
    kind, line = parse(text.strip())
    if not line:
        raise Blank(text)
    return compose(kind, lowered_tags(line))


def tags_in(line: str) -> list[str]:
    return TAG.findall(line)


def lowered_tags(text: str) -> str:
    return TAG.sub(lambda found: found[0].lower(), text)


def untagged(text: str) -> str:
    return " ".join(TAG.sub("", text).split())


def file_stamps(path: Path) -> tuple[datetime, datetime]:
    stat = path.stat()
    born = getattr(stat, "st_birthtime", stat.st_mtime)
    return datetime.fromtimestamp(born), datetime.fromtimestamp(stat.st_mtime)


def read_folder(folder: Path, stamps: Stamps = file_stamps) -> list[Record]:
    if not folder.is_dir():
        return []
    return sorted((read_record(path, stamps) for path in record_files(folder)), key=newest_first)


def record_files(folder: Path) -> Iterable[Path]:
    return (
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix == EXTENSION and not path.name.startswith(".")
    )


def read_record(path: Path, stamps: Stamps = file_stamps) -> Record:
    content = path.read_text(encoding="utf-8")
    return Record.parsed(path, first_line(content), *stamps(path), body(content))


def first_line(content: str) -> str:
    return next((line.strip() for line in content.splitlines() if line.strip()), "")


def body(content: str) -> str:
    return split_body(content)[1]


def split_body(content: str) -> tuple[str, str]:
    lines = content.splitlines(keepends=True)
    first = next((n for n, line in enumerate(lines) if line.strip()), len(lines))
    return "".join(lines[: first + 1]), "".join(lines[first + 1 :])


@dataclass(frozen=True)
class Item:
    number: int
    text: str
    ticked: bool


def items(record: Record) -> list[Item]:
    return [
        Item(number, found[3][2:], found[2] in TICKED)
        for number, found in boxes(record.body.splitlines())
    ]


def boxes(lines: list[str]) -> Iterator[tuple[int, re.Match[str]]]:
    for number, line in enumerate(lines, start=1):
        found = BOX.match(line)
        if found:
            yield number, found


def progress(record: Record) -> tuple[int, int]:
    steps = items(record)
    return sum(item.ticked for item in steps), len(steps)


def is_run(record: Record) -> bool:
    return record.kind is not Kind.CHECKLIST and bool(items(record))


RUN_KINDS = {Kind.TASK, Kind.DONE}


def runs(template: Record, logs: Iterable[Record]) -> list[Record]:
    found = [r for r in logs if r.kind in RUN_KINDS and r.line == template.line]
    return sorted(found, key=newest_first)


def open_run(template: Record, logs: Iterable[Record]) -> Record | None:
    return next((r for r in runs(template, logs) if r.kind is Kind.TASK), None)


def newest_first(record: Record):
    return (-record.created.timestamp(), record.path.name)


def keep(folder: Path, text: str) -> Path:
    line = normalise(text)
    folder.mkdir(parents=True, exist_ok=True)
    return create(folder, slug(text), line)


def rename(path: Path, text: str) -> Path:
    line = normalise(text)
    old = first_line(path.read_text(encoding="utf-8"))
    write_text(path, line)
    if slug(text) == slug(old):
        return path
    target = free_path(path.parent, slug(text))
    path.rename(target)
    return target


def start(folder: Path, template: Record) -> Path:
    text = compose(Kind.TASK, template.line) + "\n" + cleared(template.body)
    return create(folder, slug(template.line), text)


def cleared(body: str) -> str:
    return "".join(
        BOX.sub(r"\g<1> \g<3>", line) if BOX.match(line) else line
        for line in body.splitlines(keepends=True)
    )


def tick(path: Path, number: int) -> str:
    content = path.read_text(encoding="utf-8")
    first, rest = split_body(content)
    lines = rest.splitlines(keepends=True)
    found = BOX.match(lines[number - 1]) if 0 < number <= len(lines) else None
    if not found:
        raise NoSuchItem(number)
    flipped = found[1] + flip(found[2]) + found[3]
    lines[number - 1] = flipped + lines[number - 1][found.end() :]
    path.write_text(first + "".join(lines), encoding="utf-8")
    return flipped


def flip(mark: str) -> str:
    return " " if mark in TICKED else "x"


def add(path: Path, text: str) -> str:
    if not text.strip():
        raise Blank(text)
    content = path.read_text(encoding="utf-8")
    line = f"- [ ] {text.strip()}"
    path.write_text(ended(content) + line + "\n", encoding="utf-8")
    return line


def ended(content: str) -> str:
    return content if not content or content.endswith("\n") else content + "\n"


def mark(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    kind, line = parse(first_line(content))
    if kind not in FLIPPED:
        return first_line(content)
    return rewrite_first_line(path, content, compose(FLIPPED[kind], line))


def decide(path: Path, resolution: str) -> str:
    if not resolution.strip():
        raise Blank(resolution)
    content = path.read_text(encoding="utf-8")
    kind, line = parse(first_line(content))
    if kind not in (Kind.QUESTION, Kind.DECISION):
        return first_line(content)
    settled = compose(Kind.DECISION, line + RESOLVED + resolution.strip())
    return rewrite_first_line(path, content, settled)


def rewrite_first_line(path: Path, content: str, text: str) -> str:
    path.write_text(replace_first_line(content, text), encoding="utf-8")
    return text


def replace_first_line(content: str, text: str) -> str:
    lines = content.splitlines(keepends=True)
    first = next((n for n, line in enumerate(lines) if line.strip()), None)
    if first is None:
        return text + "\n"
    lines[first] = text + "\n"
    return "".join(lines)


def write_text(path: Path, text: str) -> None:
    path.write_text(text.strip() + "\n", encoding="utf-8")


def slug(text: str) -> str:
    joined = "-".join(re.findall(r"\w+", untagged(text).casefold()))
    return joined[:SLUG_LIMIT].strip("-") or FALLBACK_SLUG


def create(folder: Path, name: str, text: str) -> Path:
    for path in candidates(folder, name):
        try:
            with path.open("x", encoding="utf-8") as new:
                new.write(text.strip() + "\n")
        except FileExistsError:
            continue
        return path
    raise AssertionError("candidates never run out")


def free_path(folder: Path, name: str) -> Path:
    return next(path for path in candidates(folder, name) if not path.exists())


def candidates(folder: Path, name: str) -> Iterator[Path]:
    return (folder / f"{name}{suffix}{EXTENSION}" for suffix in suffixes())


def suffixes() -> Iterator[str]:
    yield ""
    for n in count(2):
        yield f"-{n}"
