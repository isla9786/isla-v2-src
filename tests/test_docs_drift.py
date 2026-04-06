import importlib.util
import re
import shlex
from pathlib import Path

from isla_v2.core.policies.capability_answers import get_capability_answer
from isla_v2.core.router.deterministic_router import route_prompt
from isla_v2.core.tools.ops_catalog import is_known_ops_command, known_ops_names
from isla_v2.core.workflows.procedures import PROCEDURES, resolve_procedure_name


ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
MANUAL = DOCS_DIR / "ISLA_V2_OPERATOR_MANUAL.md"
CHEATSHEET = DOCS_DIR / "ISLA_V2_OPERATOR_CHEATSHEET.md"
BOT = ROOT / "isla_v2" / "apps" / "telegram_sidecar" / "bot.py"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def section(text: str, start_heading: str, end_heading: str | None = None) -> str:
    start = text.index(start_heading)
    body_start = text.index("\n", start) + 1
    if end_heading is None:
        return text[body_start:]
    end = text.index(end_heading, body_start)
    return text[body_start:end]


def markdown_table_first_column(text: str) -> list[str]:
    values: list[str] = []
    for line in text.splitlines():
        if not line.startswith("| `"):
            continue
        cell = line.split("|")[1].strip()
        values.append(cell.strip("`"))
    return values


def bot_slash_commands() -> set[str]:
    content = read(BOT)
    return set(re.findall(r'CommandHandler\("([^"]+)"', content))


def command_like_entries(text: str) -> list[str]:
    entries = re.findall(r"`([^`]+)`", text)
    result: list[str] = []
    for entry in entries:
        if entry.startswith("/home/ai/bin/"):
            result.append(entry)
            continue
        if entry.startswith("/"):
            first = entry[1:].split()[0]
            if "/" not in first:
                result.append(entry)
            continue
        if entry.startswith("python -m "):
            result.append(entry)
            continue
        if entry and entry[0].islower():
            result.append(entry)
    return result


def validate_slash_command(entry: str, slash_commands: set[str]) -> None:
    parts = entry[1:].split()
    root = parts[0]
    assert root in slash_commands, f"missing Telegram slash command root: {entry}"

    args = parts[1:]
    if root == "ops":
        assert args, f"/ops entry missing subcommand: {entry}"
        assert is_known_ops_command(" ".join(args)), f"unknown /ops command in docs: {entry}"
    elif root == "help":
        assert not args or args in (["facts"], ["ops"]), f"unexpected /help form in docs: {entry}"
    elif root == "status":
        assert not args or args in (["short"], ["full"], ["alert"]), f"unexpected /status form in docs: {entry}"
    elif root == "hotel":
        assert args in (["address"], ["phone"]), f"unexpected /hotel form in docs: {entry}"
    elif root == "system":
        assert args == ["canary"], f"unexpected /system form in docs: {entry}"


def validate_plain_text_entry(entry: str) -> None:
    if is_known_ops_command(entry):
        return
    if resolve_procedure_name(entry) in PROCEDURES:
        return
    if get_capability_answer(entry):
        return
    if route_prompt(entry).route in {"exact", "fact_lookup"}:
        return
    raise AssertionError(f"documented plain-text command not recognized by live implementation: {entry}")


def validate_cli_entry(entry: str) -> None:
    working_dir: Path | None = None
    command = entry

    if command.startswith("cd "):
        assert " && " in command, f"malformed cd-prefixed CLI entry in docs: {entry}"
        cd_part, command = command.split(" && ", 1)
        cd_parts = shlex.split(cd_part)
        assert len(cd_parts) == 2 and cd_parts[0] == "cd", f"malformed cd-prefixed CLI entry in docs: {entry}"
        working_dir = Path(cd_parts[1])
        assert working_dir.exists(), f"documented CLI working directory missing: {working_dir}"

    parts = shlex.split(command)
    assert parts, f"empty CLI entry in docs: {entry}"

    if parts[0].startswith("/home/ai/bin/"):
        path = Path(parts[0])
        assert path.exists(), f"documented CLI path missing: {path}"
        return

    if parts[0] == "python" and len(parts) >= 3 and parts[1] == "-m":
        module = parts[2]
        assert importlib.util.find_spec(module) is not None, f"documented Python module missing: {module}"
        return

    if parts[0].endswith("/python"):
        interpreter = Path(parts[0])
        assert interpreter.exists(), f"documented Python interpreter missing: {interpreter}"
        assert len(parts) >= 2, f"malformed Python script entry in docs: {entry}"
        if parts[1] == "-m":
            assert len(parts) >= 3, f"malformed Python module entry in docs: {entry}"
            module = parts[2]
            assert importlib.util.find_spec(module) is not None, f"documented Python module missing: {module}"
            return

        script = Path(parts[1])
        script_path = script if script.is_absolute() else (working_dir or ROOT) / script
        assert script_path.exists(), f"documented Python script missing: {script_path}"
        return

    raise AssertionError(f"unsupported CLI entry validator: {entry}")


def test_manual_canonical_ops_match_live_catalog():
    manual = read(MANUAL)
    ops_section = section(manual, "## /ops commands", "## Plain-text operator commands")
    documented = set(markdown_table_first_column(ops_section))
    live = set(known_ops_names())
    assert documented == live, (
        "manual canonical /ops inventory drifted from live catalog\n"
        f"documented_only={sorted(documented - live)}\n"
        f"live_only={sorted(live - documented)}"
    )


def test_manual_procedures_match_live_registry():
    manual = read(MANUAL)
    procedures_section = section(manual, "## Procedures", "## How to run procedures")
    documented = set(markdown_table_first_column(procedures_section))
    live = set(PROCEDURES.keys())
    assert documented == live, (
        "manual procedure inventory drifted from live registry\n"
        f"documented_only={sorted(documented - live)}\n"
        f"live_only={sorted(live - documented)}"
    )


def test_cheatsheet_command_surface_matches_live_implementation():
    cheat = read(CHEATSHEET)
    slash_commands = bot_slash_commands()

    telegram_section = section(cheat, "## Core Telegram Commands", "## Core Plain-Text Commands")
    plain_text_section = section(cheat, "## Core Plain-Text Commands", "## Core Local CLI Commands")
    cli_section = section(cheat, "## Core Local CLI Commands", "## Safest Restart Flow")
    restart_section = section(cheat, "## Safest Restart Flow", "## Rollback Safety Commands")
    rollback_section = section(cheat, "## Rollback Safety Commands", "## Facts and Notes")
    facts_section = section(cheat, "## Facts and Notes", "## Procedures")
    procedures_section = section(cheat, "## Procedures", "## Top Troubleshooting Cues")

    for entry in command_like_entries(telegram_section):
        validate_slash_command(entry, slash_commands)

    for entry in command_like_entries(plain_text_section):
        validate_plain_text_entry(entry)

    for entry in command_like_entries(cli_section):
        validate_cli_entry(entry)

    for entry in command_like_entries(restart_section):
        if entry.startswith("/home/ai/bin/") or entry.startswith("python -m "):
            validate_cli_entry(entry)
        elif entry.startswith("/"):
            validate_slash_command(entry, slash_commands)
        else:
            validate_plain_text_entry(entry)

    for entry in command_like_entries(rollback_section):
        if entry.startswith("/home/ai/bin/") or entry.startswith("python -m "):
            validate_cli_entry(entry)
        elif entry.startswith("/"):
            validate_slash_command(entry, slash_commands)
        else:
            validate_cli_entry(entry)

    for entry in command_like_entries(facts_section):
        if entry.startswith("/"):
            validate_slash_command(entry, slash_commands)

    procedure_names = {entry for entry in command_like_entries(procedures_section) if not entry.startswith("/")}
    documented_proc_names = {resolve_procedure_name(name) for name in procedure_names if name in PROCEDURES or resolve_procedure_name(name) in PROCEDURES}
    assert documented_proc_names == set(PROCEDURES.keys()), (
        "cheatsheet procedure list drifted from live registry\n"
        f"documented={sorted(documented_proc_names)}\n"
        f"live={sorted(PROCEDURES.keys())}"
    )

    for entry in command_like_entries(procedures_section):
        if entry.startswith("/"):
            validate_slash_command(entry, slash_commands)
