from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from isla_v2.core.common.paths import PROCEDURE_HISTORY_FILE, PROCEDURE_LOCKS_DIR, PROCEDURE_RUNS_DIR, ensure_dirs
from isla_v2.core.workflows.procedures import get_procedure, list_procedures

ENV_FILE = Path("/home/ai/ai-agents/isla_v2/secrets/isla_v2_bot.env")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def procedure_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(parse_env_file(ENV_FILE))
    env.setdefault("PYTHONPATH", "/home/ai/ai-agents")
    return env


def lock_path(name: str) -> Path:
    slug = name.replace("/", "-").replace(" ", "_")
    return PROCEDURE_LOCKS_DIR / f"{slug}.lock"


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire_lock(name: str) -> tuple[bool, str]:
    ensure_dirs()
    target = lock_path(name)
    if target.exists():
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        existing_pid = int(payload.get("pid", 0) or 0)
        if existing_pid and pid_alive(existing_pid):
            return False, f"PROCEDURE_ALREADY_RUNNING: {name}"
        target.unlink(missing_ok=True)

    target.write_text(
        json.dumps({"name": name, "pid": os.getpid(), "started_at": utc_now()}, indent=2) + "\n",
        encoding="utf-8",
    )
    return True, "LOCK_OK"


def release_lock(name: str) -> None:
    lock_path(name).unlink(missing_ok=True)


def append_history(entry: dict) -> None:
    ensure_dirs()
    PROCEDURE_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with PROCEDURE_HISTORY_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def list_procedures_text() -> str:
    rows = []
    for spec in list_procedures():
        rows.append(f"- {spec.name}: {spec.description} (timeout {spec.timeout_seconds}s)")
    return "ISLA procedures\n\n" + "\n".join(rows)


def procedure_history_text(limit: int = 8) -> str:
    ensure_dirs()
    if not PROCEDURE_HISTORY_FILE.exists():
        return "ISLA procedure history\n\nNo procedure runs yet."

    lines = PROCEDURE_HISTORY_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        return "ISLA procedure history\n\nNo procedure runs yet."

    rendered = []
    for raw in lines[-limit:]:
        try:
            item = json.loads(raw)
        except Exception:
            rendered.append(raw)
            continue
        rendered.append(
            f"- {item.get('finished_at', item.get('started_at', 'unknown'))}: "
            f"{item.get('name', 'unknown')} -> {item.get('status', 'unknown')} "
            f"[run_id={item.get('run_id', 'n/a')}]"
        )
    return "ISLA procedure history\n\n" + "\n".join(rendered)


def run_procedure(name: str) -> str:
    spec = get_procedure(name)
    if spec is None:
        return f"PROCEDURE_UNKNOWN: {name}"

    locked, message = acquire_lock(spec.name)
    if not locked:
        return message

    started_at = utc_now()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{spec.name}"
    run_log = PROCEDURE_RUNS_DIR / f"{run_id}.log"

    status = "OK"
    output = ""

    try:
        if spec.handler is not None:
            output = spec.handler()
        else:
            proc = subprocess.run(
                list(spec.command),
                capture_output=True,
                text=True,
                timeout=spec.timeout_seconds,
                env=procedure_env(),
                cwd="/home/ai/ai-agents",
            )
            status = "OK" if proc.returncode == 0 else f"FAIL({proc.returncode})"
            output = "\n".join(x for x in [proc.stdout, proc.stderr] if x.strip()).strip() or "NO_OUTPUT"
    except subprocess.TimeoutExpired as exc:
        status = "TIMEOUT"
        output = (
            (exc.stdout or "") + ("\n" if exc.stdout and exc.stderr else "") + (exc.stderr or "")
        ).strip() or "NO_OUTPUT"
    except Exception as exc:
        status = "FAIL"
        output = f"PROCEDURE_EXCEPTION: {exc}"
    finally:
        release_lock(spec.name)

    run_log.write_text(output + "\n", encoding="utf-8")
    finished_at = utc_now()
    append_history(
        {
            "run_id": run_id,
            "name": spec.name,
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at,
            "log_path": str(run_log),
        }
    )

    return (
        "ISLA procedure run\n\n"
        f"name: {spec.name}\n"
        f"status: {status}\n"
        f"run_id: {run_id}\n"
        f"log: {run_log}\n\n"
        + "\n".join(output.splitlines()[-40:])
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ISLA v2 procedure runner")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list")
    p_list.set_defaults(func=lambda _args: print(list_procedures_text()))

    p_history = sub.add_parser("history")
    p_history.add_argument("--limit", type=int, default=8)
    p_history.set_defaults(func=lambda args: print(procedure_history_text(args.limit)))

    p_run = sub.add_parser("run")
    p_run.add_argument("name")
    p_run.set_defaults(func=lambda args: print(run_procedure(args.name)))

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
