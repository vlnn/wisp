from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from wisp.oracle import Answer
from wisp.records import Kind, Record, first_line, normalise, parse
from wisp.search import matches, query, search

OFFERS = {
    Kind.LOG: "Log",
    Kind.TASK: "Task",
    Kind.DONE: "Done",
    Kind.NOTE: "Note",
    Kind.QUESTION: "Question",
    Kind.DECISION: "Decision",
}
FLIPS = {
    Kind.TASK: "Mark done",
    Kind.DONE: "Reopen",
    Kind.QUESTION: "Decide",
    Kind.DECISION: "Reopen",
}
FINISHES = {
    Kind.TASK: "Finish",
    Kind.DONE: "Reopen",
    Kind.QUESTION: "Decide",
    Kind.DECISION: "Reopen",
}
SETTLED = {Kind.DONE: "done", Kind.DECISION: "decided"}
ICONS = {
    Kind.LOG: "icons/log.png",
    Kind.TASK: "icons/task.png",
    Kind.DONE: "icons/done.png",
    Kind.NOTE: "icons/note.png",
    Kind.QUESTION: "icons/question.png",
    Kind.DECISION: "icons/decision.png",
}


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


def rows(text: str, records: Iterable[Record], now: datetime) -> list[dict]:
    offered = [keep_row(text)] if query(text).words else []
    return offered + [record_row(record, now) for record in search(text, records)]


def keep_row(text: str) -> dict:
    kind, line = parse(text.strip())
    return {
        "title": f'{OFFERS[kind]} "{line}"',
        "subtitle": "↩ keeps it",
        "arg": normalise(text),
        "icon": icon(kind),
        "variables": {"action": "keep"},
        "mods": {mod: {"valid": False, "subtitle": ""} for mod in ("shift", "alt", "cmd")},
    }


def record_row(record: Record, now: datetime) -> dict:
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


def icon(kind: Kind) -> dict:
    return {"path": ICONS[kind]}


def record_when(record: Record, now: datetime) -> str:
    written = when(record.created, now)
    if record.kind in SETTLED:
        return f"{SETTLED[record.kind]} {when(record.changed, now)} · {written}"
    return written


def shift_mod(record: Record) -> dict:
    if record.kind in FLIPS:
        return {
            "arg": str(record.path),
            "subtitle": FLIPS[record.kind],
            "variables": {"action": "mark"},
        }
    return {"arg": record.text, "subtitle": "Copy to clipboard"}


def menu_rows(record: Record, typed: str) -> list[dict]:
    return [row for row in menu(record) if matches(typed, row["title"])]


def menu(record: Record) -> list[dict]:
    path, text = str(record.path), record.text
    flip = [(FINISHES[record.kind], path, {"action": "mark"})] if record.kind in FINISHES else []
    actions = [
        *flip,
        ("Open", path, {"action": "open"}),
        ("Rename", text, {"action": "rename", "path": path}),
        ("Copy", text, {"action": "copy"}),
        ("Trash", path, {"action": "trash"}),
    ]
    return [menu_row(title, text, arg, variables) for title, arg, variables in actions]


def menu_row(title: str, subtitle: str, arg: str, variables: dict) -> dict:
    return {"title": title, "subtitle": subtitle, "arg": arg, "variables": variables}


def rename_row(text: str) -> dict:
    stripped = text.strip()
    if not stripped:
        return {"title": "Type the new text", "valid": False}
    return {"title": f'Rename to "{stripped}"', "subtitle": "↩ renames", "arg": stripped}


NO_SERVER = "Set Model server or turn on Apple Intelligence in the workflow configuration"


def question_rows(
    question: str, answers: Iterable[Answer], now: datetime, lines: int, served: bool
) -> list[dict]:
    if not served:
        return [{"title": NO_SERVER, "subtitle": "to ask questions about the log", "valid": False}]
    asked = [a for a in answers if matches(question, a.question)]
    offered = [ask_row(question, lines)] if question else []
    return offered + [answer_row(answer, now) for answer in asked]


def ask_row(question: str, lines: int) -> dict:
    return {
        "title": f'Ask "{question}"',
        "subtitle": f"↩ asks the model about {lines} lines",
        "arg": question,
        "variables": {"action": "ask"},
        "mods": {mod: {"valid": False, "subtitle": ""} for mod in ("shift", "alt", "cmd")},
    }


def answer_row(answer: Answer, now: datetime) -> dict:
    path = str(answer.path)
    return {
        "title": answer.question,
        "subtitle": f"{when(answer.created, now)} · {first_line(answer.answer)}",
        "arg": path,
        "type": "file",
        "quicklookurl": path,
        "variables": {"action": "open"},
        "text": {"copy": answer.answer, "largetype": answer.answer},
        "mods": {
            "shift": {"arg": answer.answer, "subtitle": "Copy the answer"},
            "alt": {"arg": path, "subtitle": "Move to Trash", "variables": {"action": "trash"}},
            "cmd": {"valid": False, "subtitle": ""},
        },
    }
