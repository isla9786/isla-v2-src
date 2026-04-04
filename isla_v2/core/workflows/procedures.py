from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from isla_v2.core.common.paths import PROCEDURE_RUNS_DIR, ensure_dirs
from isla_v2.core.tools.ops_status import get_status

VENV_PYTHON = "/home/ai/ai-agents/venv2026/bin/python"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_health_snapshot() -> str:
    ensure_dirs()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = PROCEDURE_RUNS_DIR / f"health-snapshot-{stamp}.json"
    payload = {
        "created_at": utc_now(),
        "v2_status": get_status("v2_bot"),
        "main_stack": get_status("main_stack"),
        "watchdog": get_status("watchdog"),
        "gateway": get_status("gateway"),
        "webui": get_status("webui"),
        "qdrant": get_status("qdrant"),
        "ollama": get_status("ollama"),
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return f"HEALTH_SNAPSHOT_OK: {out_path}"


@dataclass(frozen=True)
class ProcedureSpec:
    name: str
    description: str
    timeout_seconds: int
    command: tuple[str, ...] = ()
    handler: Callable[[], str] | None = None


PROCEDURES: dict[str, ProcedureSpec] = {
    "preflight": ProcedureSpec(
        name="preflight",
        description="Run the ISLA_V2 preflight gate.",
        timeout_seconds=180,
        command=("/home/ai/bin/isla-v2-preflight",),
    ),
    "stack_health": ProcedureSpec(
        name="stack_health",
        description="Run the main ISLA stack health check.",
        timeout_seconds=90,
        command=("/home/ai/bin/isla-check",),
    ),
    "watchdog_view": ProcedureSpec(
        name="watchdog_view",
        description="Render the watchdog status snapshot.",
        timeout_seconds=90,
        command=(VENV_PYTHON, "-m", "isla_v2.apps.watchdog.watchdog", "--show"),
    ),
    "health_snapshot": ProcedureSpec(
        name="health_snapshot",
        description="Write a bounded JSON health snapshot artifact.",
        timeout_seconds=120,
        handler=build_health_snapshot,
    ),
}


ALIASES = {
    "stack health": "stack_health",
    "watchdog view": "watchdog_view",
    "health snapshot": "health_snapshot",
}


def resolve_procedure_name(name: str) -> str:
    normalized = " ".join((name or "").strip().lower().split())
    if normalized in PROCEDURES:
        return normalized
    return ALIASES.get(normalized, normalized.replace(" ", "_"))


def get_procedure(name: str) -> ProcedureSpec | None:
    return PROCEDURES.get(resolve_procedure_name(name))


def list_procedures() -> list[ProcedureSpec]:
    return [PROCEDURES[name] for name in sorted(PROCEDURES.keys())]
