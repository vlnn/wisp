from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import TypedDict

from wisp.oracle import Evidence
from wisp.records import RESOLVED, Kind, Record, normalise, parse
from wisp.search import matches, query, search


class Icon(TypedDict):
    path: str


class Mod(TypedDict, total=False):
    arg: str
    subtitle: str
    valid: bool
    variables: dict[str, str]


class Row(TypedDict, total=False):
    title: str
    subtitle: str
    arg: str
    valid: bool
    icon: Icon
    variables: dict[str, str]
    mods: dict[str, Mod]
    text: dict[str, str]
    quicklookurl: str


SETTLE = {
    Kind.TASK: "Finish",
    Kind.DONE: "Reopen",
    Kind.QUESTION: "Decide",
    Kind.DECISION: "Reopen",
}
SETTLED = {Kind.DONE: "done", Kind.DECISION: "decided"}


def when(created: datetime, now: datetime) -> str:
    days_ago = (now.date() - created.date()).days
    clock = f"{created:%H:%M}"
    if days_ago == 0:
        return f"{clock} today"
    if days_ago == 1:
        return f"yesterday {clock}"
    if days_ago > 1 and created.year == now.year:
        return f"{created:%a} {created.day} {created:%b} {clock}"
    return f"{created.day} {created:%b} {created.year} {clock}"


def rows(text: str, records: Iterable[Record], now: datetime) -> list[Row]:
    offered = [keep_row(text)] if query(text).words else []
    return offered + [record_row(record, now) for record in search(text, records, now.date())]


def keep_row(text: str) -> Row:
    kind, line = parse(text.strip())
    return {
        "title": f'{kind.offer} "{line}"',
        "subtitle": "↩ keeps it",
        "arg": normalise(text),
        "icon": icon(kind),
        "variables": {"action": "keep"},
        "mods": {mod: {"valid": False, "subtitle": ""} for mod in ("shift", "alt", "cmd")},
    }


def record_row(record: Record, now: datetime) -> Row:
    path = str(record.path)
    return {
        "title": record.text,
        "subtitle": record_when(record, now),
        "arg": "",
        "icon": icon(record.kind),
        "quicklookurl": path,
        "variables": {"action": "menu", "path": path},
        "text": {"copy": record.text, "largetype": record.text},
        "mods": {
            "shift": shift_mod(record),
            "alt": {"arg": path, "subtitle": "Move to Trash", "variables": {"action": "trash"}},
            "cmd": {
                "arg": record.text,
                "subtitle": "Rename",
                "variables": {"action": "rename", "path": path},
            },
        },
    }


def icon(kind: Kind) -> Icon:
    return {"path": kind.icon}


def record_when(record: Record, now: datetime) -> str:
    written = when(record.created, now)
    if record.kind in SETTLED:
        return f"{SETTLED[record.kind]} {when(record.changed, now)} · {written}"
    return written


def shift_mod(record: Record) -> Mod:
    if record.kind in SETTLE:
        arg, variables = settling(record)
        return {"arg": arg, "subtitle": SETTLE[record.kind], "variables": variables}
    return {"arg": record.text, "subtitle": "Copy to clipboard", "variables": {"action": "copy"}}


def settling(record: Record) -> tuple[str, dict[str, str]]:
    path = str(record.path)
    if record.kind is Kind.QUESTION:
        return "", {"action": "menu", "path": path}
    return path, {"action": "mark"}


def menu_rows(record: Record, typed: str) -> list[Row]:
    if record.kind is Kind.QUESTION:
        return [decide_row(record, typed), *always_rows(record)]
    return [row for row in menu(record) if matches(typed, row["title"])]


def menu(record: Record) -> list[Row]:
    return [*settle_rows(record), *always_rows(record)]


def settle_rows(record: Record) -> list[Row]:
    if record.kind not in SETTLE:
        return []
    arg, variables = settling(record)
    return [menu_row(SETTLE[record.kind], record.text, arg, variables)]


def always_rows(record: Record) -> list[Row]:
    path, text = str(record.path), record.text
    actions = [
        ("Open", path, {"action": "open"}),
        ("Rename", text, {"action": "rename", "path": path}),
        ("Copy", text, {"action": "copy"}),
        ("Trash", path, {"action": "trash"}),
    ]
    return [menu_row(title, text, arg, variables) for title, arg, variables in actions]


def menu_row(title: str, subtitle: str, arg: str, variables: dict[str, str]) -> Row:
    return {"title": title, "subtitle": subtitle, "arg": arg, "variables": variables}


def decide_row(record: Record, resolution: str) -> Row:
    stripped = resolution.strip()
    variables = {"action": "decide", "path": str(record.path)}
    if not stripped:
        return {
            "title": f'Type the resolution for "{record.line}"',
            "valid": False,
            "icon": icon(Kind.QUESTION),
            "variables": variables,
        }
    return {
        "title": f'Decide "{record.line}{RESOLVED}{stripped}"',
        "subtitle": "↩ settles the question",
        "arg": stripped,
        "icon": icon(Kind.DECISION),
        "variables": variables,
    }


def rename_row(text: str) -> Row:
    stripped = text.strip()
    if not stripped:
        return {"title": "Type the new text", "valid": False}
    return {"title": f'Rename to "{stripped}"', "subtitle": "↩ renames", "arg": stripped}


NO_SERVER = "Set Model server or turn on Apple Intelligence in the workflow configuration"


def unserved_row() -> Row:
    return {"title": NO_SERVER, "subtitle": "to ask questions about the log", "valid": False}


def question_rows(
    question: str, records: Iterable[Record], now: datetime, found: Evidence
) -> list[Row]:
    offered = [ask_row(question, len(found.lines()), len(found.matching))] if question else []
    return offered + [record_row(record, now) for record in search(question, records, now.date())]


def ask_row(question: str, lines: int, matching: int = 0) -> Row:
    singled = f", {matching} matching" if 0 < matching < lines else ""
    return {
        "title": f'Ask "{question}"',
        "subtitle": f"↩ asks the model about {lines} lines{singled}",
        "arg": question,
        "icon": icon(Kind.QUESTION),
        "variables": {"action": "ask"},
        "mods": {mod: {"valid": False, "subtitle": ""} for mod in ("shift", "alt", "cmd")},
    }
