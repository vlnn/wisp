from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from wisp.oracle import Answer
from wisp.records import Record, first_line
from wisp.search import matches, search


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


def rows(query: str, records: Iterable[Record], now: datetime) -> list[dict]:
    text = query.strip()
    offered = [keep_row(text)] if text else []
    return offered + [record_row(record, now) for record in search(text, records)]


def keep_row(text: str) -> dict:
    return {
        "title": f'Log "{text}"',
        "subtitle": "↩ keeps it",
        "arg": text,
        "variables": {"action": "keep"},
        "mods": {mod: {"valid": False, "subtitle": ""} for mod in ("shift", "alt", "cmd")},
    }


def record_row(record: Record, now: datetime) -> dict:
    path = str(record.path)
    return {
        "title": record.text,
        "subtitle": when(record.created, now),
        "arg": path,
        "type": "file",
        "quicklookurl": path,
        "variables": {"action": "open"},
        "text": {"copy": record.text, "largetype": record.text},
        "mods": {
            "shift": {"arg": record.text, "subtitle": "Copy to clipboard"},
            "alt": {"arg": path, "subtitle": "Move to Trash", "variables": {"action": "trash"}},
            "cmd": {
                "arg": record.text,
                "subtitle": "Rename",
                "variables": {"action": "rename", "path": path},
            },
        },
    }


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
