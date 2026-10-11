import plistlib
import re
from datetime import timedelta
from pathlib import Path

import pytest

from conftest import NOW
from wisp import cli, present, records

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "workflow"
ALFRED_VARIABLES = {"alfred_workflow_data", "alfred_workflow_cache", "job"}
EQUALS = 0


@pytest.fixture(scope="module")
def plist():
    with (WORKFLOW / "info.plist").open("rb") as f:
        return plistlib.load(f)


@pytest.fixture(scope="module")
def objects(plist):
    return {o["uid"]: o for o in plist["objects"]}


def scripts(plist):
    return [o["config"]["script"] for o in plist["objects"] if "script" in o.get("config", {})]


def wisp_commands(script):
    return re.findall(r"-m wisp ([a-z-]+)", script)


def case_labels(script):
    return re.findall(r"^\s*([a-z]+)\)", script, re.MULTILINE)


def match_strings(plist):
    return {
        condition["matchstring"]
        for o in plist["objects"]
        if o["type"].endswith("conditional")
        for condition in o["config"]["conditions"]
    }


def actions_in(row):
    found = {row.get("variables", {}).get("action")}
    found |= {mod.get("variables", {}).get("action") for mod in row.get("mods", {}).values()}
    return found - {None}


def emitted_actions():
    rows = [present.keep_row("x"), present.ask_row("x", 1)]
    for kind in records.Kind:
        record = records.Record(Path("/log/x.md"), kind, "x", NOW, NOW)
        rows.append(present.record_row(record, NOW + timedelta(minutes=1)))
        rows.extend(present.menu(record))
        rows.append(present.decide_row(record, "y"))
    return set().union(*map(actions_in, rows))


def test_every_script_runs_a_known_command(plist):
    for script in scripts(plist):
        for command in wisp_commands(script):
            assert command in cli.COMMANDS, f"the plist runs `wisp {command}`, which does not exist"


def test_every_emitted_action_has_a_branch(plist):
    branches = match_strings(plist).union(*(case_labels(s) for s in scripts(plist)))
    for action in emitted_actions():
        assert action in branches, f"present emits action {action!r} but the plist never routes it"


def test_every_branch_is_an_emitted_action(plist):
    for action in match_strings(plist):
        assert action in emitted_actions(), f"the plist routes {action!r} but nothing emits it"


def test_conditionals_match_exactly(plist):
    for o in plist["objects"]:
        if o["type"].endswith("conditional"):
            for condition in o["config"]["conditions"]:
                assert condition["matchmode"] == EQUALS, (
                    f"{condition['matchstring']} should use 'is equal to', not mode "
                    f"{condition['matchmode']}"
                )
                assert condition["inputstring"] == "{var:action}", "conditions read `action`"


def test_every_connection_points_at_an_object(plist, objects):
    for source, connections in plist["connections"].items():
        assert source in objects, f"connections start at unknown object {source}"
        for connection in connections:
            assert connection["destinationuid"] in objects, (
                f"{source} connects to unknown object {connection['destinationuid']}"
            )


def test_every_trigger_and_filter_leads_somewhere(plist, objects):
    for uid, o in objects.items():
        if o["type"].endswith(("hotkey", "scriptfilter", "conditional", "userinterface.text")):
            assert plist["connections"].get(uid), f"{o['type']} {uid} is wired to nothing"


def test_keyword_filters_each_have_a_hotkey(plist, objects):
    hotkey_targets = {
        c["destinationuid"]
        for uid, cs in plist["connections"].items()
        if objects[uid]["type"].endswith("hotkey")
        for c in cs
    }
    keyworded = {uid for uid, o in objects.items() if o.get("config", {}).get("keyword")}
    assert hotkey_targets == keyworded, "each keyword filter (`l`, `ask`) gets one hotkey object"


def test_text_view_runs_the_shipped_script(objects):
    (text,) = [o for o in objects.values() if o["type"].endswith("userinterface.text")]
    assert (WORKFLOW / text["config"]["inputfile"]).exists(), "the view script is in the bundle"


def test_configured_variables_are_the_ones_the_package_reads(plist):
    source = "".join(p.read_text() for p in (ROOT / "src" / "wisp").glob("*.py"))
    read = set(re.findall(r'env\.get\("([a-z_]+)"', source)) - ALFRED_VARIABLES
    configured = {c["variable"] for c in plist["userconfigurationconfig"]}
    assert configured == read, "the configuration panel should offer exactly the settings read"


def test_icons_in_the_bundle_match_present():
    assert {f"icons/{p.name}" for p in (WORKFLOW / "icons").glob("*.png")} == set(
        present.ICONS.values()
    ), "every icon present names ships, and nothing else"
