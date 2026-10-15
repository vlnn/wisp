from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import TypedDict

from wisp import suggest
from wisp.oracle import Evidence
from wisp.records import (
    RESOLVED,
    Item,
    Kind,
    Record,
    items,
    normalise,
    open_run,
    parse,
    progress,
    runs,
    untagged,
)
from wisp.search import Query, fold, is_tag, logged, matches, query, search, spoken


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
    autocomplete: str


SETTLE = {
    Kind.TASK: "Finish",
    Kind.DONE: "Reopen",
    Kind.QUESTION: "Decide",
    Kind.DECISION: "Reopen",
}
SETTLED = {Kind.DONE: "done", Kind.DECISION: "decided"}
NO_MODS: dict[str, Mod] = {mod: {"valid": False, "subtitle": ""} for mod in ("shift", "alt", "cmd")}


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
    logs = list(records)
    asked = query(text, now.date())
    offered = offer_rows(text, logs, now) if asked.words else tag_rows(text, asked, logs, now)
    return offered + [record_row(record, now, logs) for record in search(text, logs, now.date())]


def tag_rows(text: str, asked: Query, logs: Sequence[Record], now: datetime) -> list[Row]:
    if not asked.tags:
        return []
    vocab = suggest.vocabulary(logs)
    return [tag_row(key, vocab, text, now) for key in suggest.tags_starting(asked.tags[-1], vocab)]


def tag_row(key: str, vocab: suggest.Vocabulary, text: str, now: datetime) -> Row:
    tag = suggest.spelling(key, vocab.spellings)
    return {
        "title": tag,
        "subtitle": f"{counted(vocab.count(key))} · last {when(vocab.last[key], now)}",
        "valid": False,
        "autocomplete": f"{with_tag_finished(text, tag)} ",
    }


def counted(records: int) -> str:
    return "1 record" if records == 1 else f"{records} records"


def with_tag_finished(text: str, tag: str) -> str:
    tokens = text.split()
    last = max(n for n, token in enumerate(tokens) if is_tag(token))
    return " ".join([*tokens[:last], tag, *tokens[last + 1 :]])


def offer_rows(text: str, logs: Sequence[Record], now: datetime) -> list[Row]:
    first = offer_row(text, logs, now)
    if parse(logged(text))[0] is Kind.CHECKLIST:
        return [first]
    return [first, *suggestion_rows(text, logs)]


def suggestion_rows(text: str, logs: Sequence[Record]) -> list[Row]:
    found = suggest.suggestions(text, suggest.vocabulary(logs))
    return [suggestion_row(suggestion) for suggestion in found]


def suggestion_row(suggestion: suggest.Suggestion) -> Row:
    subtitle = f"↩ keeps it with {suggestion.adds} · {suggestion.why}"
    return {**keep_row(suggestion.text), "subtitle": subtitle}


def offer_row(text: str, logs: Sequence[Record], now: datetime) -> Row:
    kind, line = parse(logged(text))
    if kind is Kind.CHECKLIST:
        return checklist_offer(line, logs, now)
    return keep_row(text)


def keep_row(text: str) -> Row:
    kept = normalise(logged(text))
    kind, line = parse(kept)
    return {
        "title": f'{kind.offer} "{line}"',
        "subtitle": "↩ keeps it",
        "arg": kept,
        "icon": icon(kind),
        "variables": {"action": "keep"},
        "mods": NO_MODS,
    }


def checklist_offer(line: str, logs: Sequence[Record], now: datetime) -> Row:
    found = exact_template(line, logs)
    if found is None:
        return create_offer(line)
    run = open_run(found, logs)
    if run is None:
        return start_offer(found)
    return continue_offer(found, run, now)


def offer(title: str, subtitle: str, arg: str, variables: dict[str, str]) -> Row:
    return {
        "title": title,
        "subtitle": subtitle,
        "arg": arg,
        "icon": icon(Kind.CHECKLIST),
        "variables": variables,
        "mods": NO_MODS,
    }


def create_offer(line: str) -> Row:
    return offer(f'Checklist "{line}"', "↩ creates it", normalise(f"# {line}"), {"action": "start"})


def start_offer(template: Record) -> Row:
    path = str(template.path)
    row = offer(
        f'Start "{template.line}"', f"↩ starts a run · {steps(template)}", path, {"action": "start"}
    )
    return {**row, "mods": {**NO_MODS, "cmd": fresh_mod(template)}}


def continue_offer(template: Record, run: Record, now: datetime) -> Row:
    subtitle = f"{ratio(run)} since {when(run.created, now)}"
    row = offer(f'Continue "{template.line}"', subtitle, "", items_action(run))
    return {**row, "mods": {**NO_MODS, "cmd": fresh_mod(template)}}


def fresh_mod(template: Record) -> Mod:
    return {
        "arg": str(template.path),
        "subtitle": "Start a fresh run",
        "variables": {"action": "start", "fresh": "1"},
    }


def exact_template(line: str, logs: Iterable[Record]) -> Record | None:
    wanted = fold(untagged(line))
    return next(
        (r for r in logs if r.kind is Kind.CHECKLIST and fold(untagged(r.line)) == wanted), None
    )


def items_action(record: Record) -> dict[str, str]:
    return {"action": "items", "path": str(record.path)}


def record_row(record: Record, now: datetime, logs: Sequence[Record] = ()) -> Row:
    path = str(record.path)
    return {
        "title": record.text,
        "subtitle": subtitle(record, now, logs),
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


def subtitle(record: Record, now: datetime, logs: Sequence[Record]) -> str:
    shown = state(record, now, logs)
    return f"{shown} · {' '.join(record.tags)}" if record.tags else shown


def state(record: Record, now: datetime, logs: Sequence[Record]) -> str:
    if record.kind is Kind.CHECKLIST:
        return f"{steps(record)} · {template_state(record, logs, now)}"
    if not items(record):
        return record_when(record, now)
    if record.kind is Kind.DONE:
        return f"done {when(record.changed, now)} · {ratio(record)} · {when(record.created, now)}"
    return f"{ratio(record)} · started {when(record.created, now)}"


def record_when(record: Record, now: datetime) -> str:
    written = when(record.created, now)
    if record.kind in SETTLED:
        return f"{SETTLED[record.kind]} {when(record.changed, now)} · {written}"
    return written


def steps(record: Record) -> str:
    return f"{progress(record)[1]} steps"


def ratio(record: Record) -> str:
    ticked, total = progress(record)
    return f"{ticked}/{total}"


def template_state(template: Record, logs: Sequence[Record], now: datetime) -> str:
    run = open_run(template, logs)
    if run is not None:
        return f"run open since {when(run.created, now)}"
    done = runs(template, logs)
    if done:
        return f"last done {when(done[0].changed, now)}"
    return when(template.created, now)


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


def menu_rows(record: Record, typed: str, logs: Sequence[Record] = ()) -> list[Row]:
    if record.kind is Kind.QUESTION:
        return [decide_row(record, typed), *always_rows(record)]
    return [row for row in menu(record, logs) if matches(typed, row["title"])]


def menu(record: Record, logs: Sequence[Record] = ()) -> list[Row]:
    if record.kind is Kind.CHECKLIST:
        return [start_row(record, logs), steps_row(record), *always_rows(record)]
    if items(record):
        return [steps_row(record), *settle_rows(record), *always_rows(record)]
    return [*settle_rows(record), *always_rows(record)]


def start_row(template: Record, logs: Sequence[Record]) -> Row:
    run = open_run(template, logs)
    if run is None:
        return menu_row("Start", template.text, str(template.path), {"action": "start"})
    return menu_row("Continue", run.text, "", items_action(run))


def steps_row(record: Record) -> Row:
    return menu_row("Steps", record.text, "", items_action(record))


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


def item_rows(record: Record, typed: str) -> list[Row]:
    shown = [row for row in body_rows(record) if matches(typed, row["title"])]
    if typed.strip() and not any(row.get("valid", True) for row in shown):
        return [add_row(record, typed.strip())]
    if not shown:
        return [{"title": f'Type a step to add to "{record.line}"', "valid": False}]
    if typed.strip():
        return shown
    return [*lead_rows(record), *shown]


def lead_rows(record: Record) -> list[Row]:
    if complete(record):
        return [menu_row("Finish", record.text, str(record.path), {"action": "mark"})]
    if record.kind is Kind.CHECKLIST:
        return [fresh_run_row(record, f'Start "{record.line}"')]
    if record.kind is Kind.DONE:
        return [fresh_run_row(record, f'Run "{record.line}" again')]
    return []


def fresh_run_row(record: Record, title: str) -> Row:
    subtitle = "↩ starts a run with every box cleared"
    return menu_row(title, subtitle, str(record.path), {"action": "start"})


def body_rows(record: Record) -> list[Row]:
    boxed = {item.number: item for item in items(record)}
    lines = [(n, line.strip()) for n, line in enumerate(record.body.splitlines(), 1)]
    pending = [(n, text) for n, text in lines if text and not ticked(boxed.get(n))]
    done = [(n, text) for n, text in lines if ticked(boxed.get(n))]
    return [body_row(boxed.get(n), text, record) for n, text in pending + done]


def ticked(item: Item | None) -> bool:
    return item is not None and item.ticked


def body_row(item: Item | None, text: str, record: Record) -> Row:
    return item_row(item, record) if item else {"title": text, "valid": False}


def item_row(item: Item, record: Record) -> Row:
    return {
        "title": f"{'☑' if item.ticked else '☐'} {item.text}",
        "subtitle": "↩ unticks" if item.ticked else "↩ ticks",
        "arg": str(item.number),
        "variables": {"action": "tick", "path": str(record.path)},
    }


def add_row(record: Record, text: str) -> Row:
    return {
        "title": f'Add "{text}"',
        "subtitle": "↩ adds a step",
        "arg": text,
        "variables": {"action": "add", "path": str(record.path)},
    }


def complete(record: Record) -> bool:
    ticked, total = progress(record)
    return record.kind is Kind.TASK and total > 0 and ticked == total


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
    logs = list(records)
    offered = (
        [ask_row(question, len(found.lines()), found.terms, found.without)] if question else []
    )
    listed = search(question, logs, now.date(), spoken)
    return offered + [record_row(r, now, logs) for r in listed]


def followup_row(question: str, first: str, thread: str, lines: int) -> Row:
    if not question:
        return {"title": f'Type a follow-up to "{first}"', "valid": False}
    return {
        "title": f'Ask "{question}"',
        "subtitle": f'follows up on "{first}" · {lines} lines',
        "arg": question,
        "icon": icon(Kind.QUESTION),
        "variables": {"action": "ask", "thread": thread},
    }


def ask_row(
    question: str, lines: int, terms: Iterable[str] = (), without: Iterable[str] = ()
) -> Row:
    counted = f"{lines} line" if lines == 1 else f"{lines} lines"
    matched = f" matching {', '.join(terms)}" if terms else ""
    excluded = f", leaving out {', '.join(without)}" if without else ""
    return {
        "title": f'Ask "{question}"',
        "subtitle": f"↩ asks the model about {counted}{matched}{excluded}",
        "arg": question,
        "icon": icon(Kind.QUESTION),
        "variables": {"action": "ask"},
        "mods": NO_MODS,
    }
