from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from wisp.records import Record
from wisp.search import search


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
