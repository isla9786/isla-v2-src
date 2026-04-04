import os
import re
import subprocess
import time
from pathlib import Path
from typing import Callable

from isla_v2.core.memory.fact_store import get_fact
from isla_v2.core.tools.ops_catalog import (
    canonicalize_ops_text,
    normalize_ops_text,
    ops_help_text,
    unknown_ops_text,
)
from isla_v2.core.tools.ops_status import get_logs, get_status
from isla_v2.core.workflows.runner import list_procedures_text, procedure_history_text, run_procedure

CONFIRM_TTL_SECONDS = 60
OPS_AUDIT_LOG = Path("/home/ai/ai-agents/isla_v2/data/ops-audit.log")
PENDING_CONFIRMS: dict[tuple[int, str], float] = {}

REQUEST_CONFIRM_MAP = {
    "restart sidecar": "confirm restart sidecar",
    "restart v2": "confirm restart v2",
    "recover main": "confirm recover main",
    "recover all": "confirm recover all",
    "restart gateway": "confirm restart gateway",
    "force restart ollama": "confirm force restart ollama",
    "rollback golden": "confirm rollback golden",
}
CONFIRM_ACTIONS = set(REQUEST_CONFIRM_MAP.values())


def _run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = "\n".join(x for x in [proc.stdout, proc.stderr] if x.strip()).strip()
    return out if out else "NO_OUTPUT"


def tail_lines(text: str, n: int = 40) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-n:]) if lines else text


def _schedule_restart(service_name: str, delay_seconds: int = 2) -> None:
    cmd = f"(sleep {delay_seconds}; systemctl --user restart {service_name}) >/dev/null 2>&1 &"
    subprocess.Popen(
        ["/usr/bin/bash", "-lc", cmd],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env={**os.environ, "HOME": os.environ.get("HOME", "/home/ai")},
    )


def sidecar_is_retired() -> bool:
    status = _run(["systemctl", "--user", "status", "isla-crew-bot.service", "--no-pager"])
    return "Unit isla-crew-bot.service could not be found." in status


def sidecar_retired_text() -> str:
    return (
        "Legacy crew sidecar is retired in the v2 baseline.\n\n"
        "No crew sidecar service is expected on this host."
    )


def register_pending_confirm(user_id: int, confirm_text: str) -> None:
    PENDING_CONFIRMS[(user_id, normalize_ops_text(confirm_text))] = time.time()


def consume_pending_confirm(user_id: int, confirm_text: str) -> bool:
    key = (user_id, normalize_ops_text(confirm_text))
    created = PENDING_CONFIRMS.pop(key, None)
    if created is None:
        return False
    return (time.time() - created) <= CONFIRM_TTL_SECONDS


def confirmation_expired_text() -> str:
    return "No pending confirmation or it expired. Run the action again and confirm within 60 seconds."


def prune_pending_confirms() -> None:
    now = time.time()
    expired = [
        key
        for key, created in list(PENDING_CONFIRMS.items())
        if (now - created) > CONFIRM_TTL_SECONDS
    ]
    for key in expired:
        PENDING_CONFIRMS.pop(key, None)


def pending_confirms_text() -> str:
    prune_pending_confirms()
    if not PENDING_CONFIRMS:
        return "ISLA pending confirms\n\nNo pending confirmations."

    now = time.time()
    rows = []
    for (user_id, confirm_text), created in sorted(PENDING_CONFIRMS.items(), key=lambda item: item[1]):
        remaining = max(0, int(CONFIRM_TTL_SECONDS - (now - created)))
        rows.append(f"- user {user_id}: {confirm_text} ({remaining}s left)")
    return "ISLA pending confirms\n\n" + "\n".join(rows)


def audit_ops_action(user_id: int, action: str, result: str) -> None:
    OPS_AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with OPS_AUDIT_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{ts}\tuser={user_id}\taction={action}\tresult={result}\n")


def audit_trail_text() -> str:
    if not OPS_AUDIT_LOG.exists():
        return "ISLA ops audit trail\n\nNo audit log yet."

    lines = OPS_AUDIT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = "\n".join(lines[-30:]) if lines else "No audit log yet."
    return "ISLA ops audit trail\n\n" + tail


def _restart_sidecar_text() -> str:
    _run(["systemctl", "--user", "restart", "isla-crew-bot.service"])
    status = _run(["/home/ai/bin/isla-crew-check"])
    return "ACTION_OK: restarted crew sidecar service\n\n" + status


def _restart_v2_text() -> str:
    _schedule_restart("isla-v2-bot.service", delay_seconds=2)
    return "ACTION_OK: scheduled restart ISLA v2 bot service in 2 seconds"


def _extract_pid(text: str) -> str:
    match = re.search(r"Main PID:\s+(\d+)", text)
    return match.group(1) if match else "unknown"


def _yes_no(ok: bool, good: str = "OK", bad: str = "ISSUE") -> str:
    return good if ok else bad


def _sidecar_state() -> tuple[str, bool, bool, str, bool, bool, str]:
    sidecar_raw = _run(["/home/ai/bin/isla-crew-check"])
    sidecar_retired = sidecar_is_retired()
    sidecar_active = sidecar_retired or "[OK]   service is active" in sidecar_raw
    pid_match = re.search(r"\[OK\]\s+bot pid:\s+(\d+)", sidecar_raw)
    sidecar_pid = "retired" if sidecar_retired else (pid_match.group(1) if pid_match else "unknown")
    sidecar_caps = sidecar_retired or "[OK]   no capability error" in sidecar_raw
    sidecar_poll = sidecar_retired or "[OK]   no Telegram polling conflict" in sidecar_raw
    sidecar_label = "RETIRED" if sidecar_retired else _yes_no(sidecar_active, "RUNNING", "DOWN")
    return sidecar_raw, sidecar_retired, sidecar_active, sidecar_pid, sidecar_caps, sidecar_poll, sidecar_label


def ops_alert_text() -> str:
    v2_raw = _run(["systemctl", "--user", "status", "isla-v2-bot.service", "--no-pager"])
    _, sidecar_retired, sidecar_active, sidecar_pid, sidecar_caps, sidecar_poll, sidecar_label = _sidecar_state()
    main_raw = _run(["/home/ai/bin/isla-check"])

    v2_running = "Active: active (running)" in v2_raw
    v2_pid = _extract_pid(v2_raw)

    gateway_ok = "[OK]   OpenClaw Gateway is active" in main_raw
    ollama_ok = "[OK]   Ollama API reachable" in main_raw
    webui_ok = "[OK]   Open WebUI API reachable" in main_raw
    qdrant_ok = "[OK]   Qdrant API reachable" in main_raw
    canary = get_fact("system", "bridge_canary") or "missing"

    issues = []

    if not v2_running:
        issues.append(f"- v2 bot DOWN (pid {v2_pid})")
    if not sidecar_retired and not sidecar_active:
        issues.append(f"- crew sidecar DOWN (pid {sidecar_pid})")
    if not sidecar_retired and not sidecar_caps:
        issues.append("- crew sidecar capability state not OK")
    if not sidecar_retired and not sidecar_poll:
        issues.append("- crew sidecar polling conflict detected")
    if not gateway_ok:
        issues.append("- gateway not OK")
    if not ollama_ok:
        issues.append("- ollama not OK")
    if not webui_ok:
        issues.append("- webui not OK")
    if not qdrant_ok:
        issues.append("- qdrant not OK")
    if canary == "missing":
        issues.append("- bridge canary missing")

    if not issues:
        return (
            "ISLA ops alert\n\n"
            "No active issues detected.\n"
            f"- v2 bot RUNNING (pid {v2_pid})\n"
            f"- crew sidecar {sidecar_label} (pid {sidecar_pid})\n"
            "- main stack healthy"
        )

    return "ISLA ops alert\n\n" + "\n".join(issues)


def ops_restart_gateway_text() -> str:
    _run(["systemctl", "--user", "restart", "openclaw-gateway.service"])
    _run(["/usr/bin/bash", "-lc", "sleep 2"])
    gateway_status = _run(["systemctl", "--user", "status", "openclaw-gateway.service", "--no-pager"])
    health = _run(["/home/ai/bin/isla-check"])
    return "ISLA ops restart gateway\n\n" + gateway_status + "\n\n" + health


def ops_recover_main_text() -> str:
    steps = []

    docker_names = _run(["docker", "ps", "--format", "{{.Names}}"])
    names = {x.strip() for x in docker_names.splitlines() if x.strip()}

    if "qdrant" in names:
        steps.append("- qdrant already running")
    else:
        _run(["docker", "start", "qdrant"])
        steps.append("- started qdrant")

    if "open-webui" in names:
        steps.append("- open-webui already running")
    else:
        _run(["docker", "start", "open-webui"])
        steps.append("- started open-webui")

    _run(["/usr/bin/bash", "-lc", "sleep 3"])
    health = _run(["/home/ai/bin/isla-check"])

    return "ISLA ops recover main\n\n" + "\n".join(steps) + "\n\n" + health


def ops_ollama_status_text() -> str:
    active_state = _run(["systemctl", "is-active", "ollama.service"]).strip()
    api_check = _run([
        "/usr/bin/bash",
        "-lc",
        "curl -fsS http://127.0.0.1:11434/api/tags >/dev/null && echo OLLAMA_API_OK || echo OLLAMA_API_DOWN",
    ]).strip()
    health = _run(["/home/ai/bin/isla-check"])
    return (
        "ISLA ops ollama status\n\n"
        f"ollama active: {active_state}\n"
        f"{api_check}\n\n"
        f"{health}"
    )


def ops_ollama_logs_text() -> str:
    logs = _run(["journalctl", "-u", "ollama.service", "-n", "40", "--no-pager"])
    return "ISLA ops ollama logs\n\n" + tail_lines(logs, 40)


def ops_restart_ollama_text() -> str:
    active_state = _run(["systemctl", "is-active", "ollama.service"]).strip()
    api_check = _run([
        "/usr/bin/bash",
        "-lc",
        "curl -fsS http://127.0.0.1:11434/api/tags >/dev/null && echo OLLAMA_API_OK || echo OLLAMA_API_DOWN",
    ]).strip()

    if active_state == "active" and api_check == "OLLAMA_API_OK":
        return (
            "ISLA ops restart ollama\n\n"
            "Ollama already healthy; no restart needed.\n"
            f"ollama active: {active_state}\n"
            f"{api_check}"
        )

    return (
        "ISLA ops restart ollama\n\n"
        "Ollama is not fully healthy.\n"
        f"ollama active: {active_state}\n"
        f"{api_check}\n\n"
        'Send exactly: "force restart ollama"'
    )


def ops_force_restart_ollama_text() -> str:
    attempts = []

    def run_rc(cmd: list[str]) -> tuple[int, str]:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        out = "\n".join(x for x in [proc.stdout, proc.stderr] if x.strip()).strip()
        return proc.returncode, out

    rc_restart, out_restart = run_rc(["sudo", "/usr/local/bin/isla-rootctl", "restart", "ollama"])
    attempts.append(
        "$ sudo /usr/local/bin/isla-rootctl restart ollama\n"
        f"rc={rc_restart}" + (f"\n{out_restart}" if out_restart else "")
    )

    _run(["/usr/bin/bash", "-lc", "sleep 2"])

    rc_active, out_active = run_rc(["sudo", "/usr/local/bin/isla-rootctl", "is-active", "ollama"])
    active_state = out_active.strip() if out_active.strip() else f"rc={rc_active}"

    api_check = _run([
        "/usr/bin/bash",
        "-lc",
        "curl -fsS http://127.0.0.1:11434/api/tags >/dev/null && echo OLLAMA_API_OK || echo OLLAMA_API_DOWN",
    ]).strip()
    health = _run(["/home/ai/bin/isla-check"])

    return (
        "ISLA ops force restart ollama\n\n"
        + "\n\n".join(attempts)
        + "\n\n"
        + f"ollama active: {active_state}\n"
        + api_check
        + "\n\n"
        + health
    )


def ops_recover_all_text() -> str:
    steps = []

    _run(["systemctl", "--user", "restart", "openclaw-gateway.service"])
    _run(["/usr/bin/bash", "-lc", "sleep 2"])
    gateway_state = _run(["systemctl", "--user", "is-active", "openclaw-gateway.service"]).strip()
    steps.append(f"- gateway state: {gateway_state}")

    docker_names = _run(["docker", "ps", "--format", "{{.Names}}"])
    names = {x.strip() for x in docker_names.splitlines() if x.strip()}

    if "qdrant" in names:
        steps.append("- qdrant already running")
    else:
        start_qdrant = _run(["docker", "start", "qdrant"]).strip()
        steps.append("- started qdrant" if "qdrant" in start_qdrant else f"- qdrant start result: {start_qdrant}")

    if "open-webui" in names:
        steps.append("- open-webui already running")
    else:
        start_webui = _run(["docker", "start", "open-webui"]).strip()
        steps.append("- started open-webui" if "open-webui" in start_webui else f"- open-webui start result: {start_webui}")

    _run(["/usr/bin/bash", "-lc", "sleep 3"])

    ollama_active = _run(["systemctl", "is-active", "ollama.service"]).strip()
    ollama_api = _run([
        "/usr/bin/bash",
        "-lc",
        "curl -fsS http://127.0.0.1:11434/api/tags >/dev/null && echo OLLAMA_API_OK || echo OLLAMA_API_DOWN",
    ]).strip()

    steps.append(f"- ollama active: {ollama_active}")
    steps.append(f"- ollama api: {ollama_api}")

    health = _run(["/home/ai/bin/isla-check"])
    return "ISLA ops recover all\n\n" + "\n".join(steps) + "\n\n" + health


def ops_rollback_golden_schedule_text() -> str:
    report_path = Path("/home/ai/ai-agents/isla_v2/data/rollback-last.txt")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = (
        "nohup /usr/bin/bash -lc "
        "\"source /home/ai/ai-agents/venv2026/bin/activate >/dev/null 2>&1 || true; "
        "/home/ai/bin/isla-v2-drill > /home/ai/ai-agents/isla_v2/data/rollback-last.txt 2>&1\" "
        ">/dev/null 2>&1 &"
    )
    subprocess.Popen(
        ["/usr/bin/bash", "-lc", cmd],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    return (
        "ISLA rollback golden scheduled.\n\n"
        "The bot may restart briefly during recovery.\n"
        "Use rollback report in about 10 seconds."
    )


def ops_rollback_report_text() -> str:
    report_path = Path("/home/ai/ai-agents/isla_v2/data/rollback-last.txt")
    if not report_path.exists():
        return "ISLA rollback report\n\nNo rollback report found yet."

    body = report_path.read_text(encoding="utf-8", errors="replace").strip() or "NO_OUTPUT"
    return "ISLA rollback report\n\n" + body


def read_only_actions() -> dict[str, Callable[[], str]]:
    return {
        "alert": ops_alert_text,
        "pending confirms": pending_confirms_text,
        "audit trail": audit_trail_text,
        "rollback report": ops_rollback_report_text,
        "sidecar logs": lambda: get_logs("crew_sidecar"),
        "sidecar status": lambda: get_status("crew_sidecar"),
        "main health": lambda: get_status("main_stack"),
        "v2 status": lambda: get_status("v2_bot"),
        "v2 logs": lambda: get_logs("v2_bot"),
        "gateway status": lambda: get_status("gateway"),
        "gateway logs": lambda: get_logs("gateway"),
        "watchdog status": lambda: get_status("watchdog"),
        "watchdog logs": lambda: get_logs("watchdog"),
        "webui status": lambda: get_status("webui"),
        "qdrant status": lambda: get_status("qdrant"),
        "golden status": lambda: get_status("golden"),
        "procedures": list_procedures_text,
        "procedure history": procedure_history_text,
        "ollama status": lambda: get_status("ollama"),
        "ollama logs": lambda: get_logs("ollama"),
        "restart ollama": ops_restart_ollama_text,
    }


def confirmed_actions() -> dict[str, Callable[[], str]]:
    return {
        "confirm restart sidecar": _restart_sidecar_text,
        "confirm restart v2": _restart_v2_text,
        "confirm recover main": ops_recover_main_text,
        "confirm recover all": ops_recover_all_text,
        "confirm restart gateway": ops_restart_gateway_text,
        "confirm force restart ollama": ops_force_restart_ollama_text,
        "confirm rollback golden": ops_rollback_golden_schedule_text,
    }


def _run_confirmed_action(user_id: int | None, action: str, func) -> str:
    try:
        result = func()
        if user_id is not None:
            audit_ops_action(user_id, action, "OK")
        return result
    except Exception as exc:
        if user_id is not None:
            audit_ops_action(user_id, action, f"FAIL: {exc}")
        raise


def maybe_run_action(prompt: str, user_id: int | None = None) -> str | None:
    normalized_prompt = normalize_ops_text(prompt)
    pl = canonicalize_ops_text(prompt)

    if pl == "procedure run <name>":
        name = normalized_prompt.removeprefix("procedure run ").strip()
        return run_procedure(name) if name else "PROCEDURE_UNKNOWN: missing procedure name"

    if pl in {"sidecar status", "sidecar logs", "restart sidecar", "confirm restart sidecar"} and sidecar_is_retired():
        return sidecar_retired_text()

    confirm_text = REQUEST_CONFIRM_MAP.get(pl)
    if confirm_text is not None:
        if user_id is not None:
            register_pending_confirm(user_id, confirm_text)
            audit_ops_action(user_id, pl, f"PENDING: {confirm_text}")
        return f'Confirmation required. Send exactly: "{confirm_text}"'

    if pl in CONFIRM_ACTIONS:
        if user_id is None or not consume_pending_confirm(user_id, pl):
            if user_id is not None:
                audit_ops_action(user_id, pl, "EXPIRED_OR_MISSING")
            return confirmation_expired_text()

    confirm_handler = confirmed_actions().get(pl)
    if confirm_handler is not None:
        return _run_confirmed_action(user_id, pl, confirm_handler)

    read_only_handler = read_only_actions().get(pl)
    if read_only_handler is not None:
        return read_only_handler()

    return None
