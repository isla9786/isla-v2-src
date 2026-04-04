import argparse
import subprocess
from typing import Callable

from isla_v2.core.common.paths import BASE_DIR, ISLA_V2_DIR

VENV_PYTHON = BASE_DIR / "venv2026" / "bin" / "python"
ENV_FILE = ISLA_V2_DIR / "secrets" / "isla_v2_bot.env"


def run_command(cmd: list[str]) -> str:
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    out = "\n".join(x for x in [proc.stdout, proc.stderr] if x.strip()).strip()
    return out if out else "NO_OUTPUT"


def run_shell(script: str) -> str:
    return run_command(["/usr/bin/bash", "-lc", script])


def tail_lines(text: str, n: int = 40) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-n:]) if lines else text


def status_main_stack() -> str:
    return run_command(["/home/ai/bin/isla-check"])


def status_sidecar() -> str:
    return run_command(["/home/ai/bin/isla-crew-check"])


def status_v2() -> str:
    return run_command(["/home/ai/bin/isla-v2-status"])


def logs_v2() -> str:
    return tail_lines(run_command(["/home/ai/bin/isla-v2-logs"]), 40)


def status_gateway() -> str:
    return run_command(["systemctl", "--user", "status", "openclaw-gateway.service", "--no-pager"])


def logs_gateway() -> str:
    return tail_lines(
        run_command(["journalctl", "--user", "-u", "openclaw-gateway.service", "-n", "40", "--no-pager"]),
        40,
    )


def status_watchdog() -> str:
    view_script = (
        f'cd "{BASE_DIR}" && '
        f'if [[ -f "{ENV_FILE}" ]]; then set -a; source "{ENV_FILE}"; set +a; fi; '
        f'"{VENV_PYTHON}" -m isla_v2.apps.watchdog.watchdog --show'
    )
    timer_status = run_command(["/home/ai/bin/isla-v2-watchdog-status"])
    view = run_shell(view_script)
    return "ISLA ops watchdog status\n\n" + timer_status + "\n\n" + view


def logs_watchdog() -> str:
    return tail_lines(run_command(["/home/ai/bin/isla-v2-watchdog-logs"]), 40)


def status_ollama() -> str:
    active_state = run_command(["systemctl", "is-active", "ollama.service"]).strip()
    api_check = run_shell(
        "curl -fsS http://127.0.0.1:11434/api/tags >/dev/null && echo OLLAMA_API_OK || echo OLLAMA_API_DOWN"
    ).strip()
    return (
        "ISLA ops ollama status\n\n"
        f"ollama active: {active_state}\n"
        f"{api_check}\n\n"
        f"{status_main_stack()}"
    )


def logs_ollama() -> str:
    return "ISLA ops ollama logs\n\n" + tail_lines(
        run_command(["journalctl", "-u", "ollama.service", "-n", "40", "--no-pager"]),
        40,
    )


def status_webui() -> str:
    container = run_command(
        ["docker", "ps", "--filter", "name=open-webui", "--format", "{{.Names}}\t{{.Status}}"]
    ).strip()
    version = run_shell("curl -fsS http://127.0.0.1:3000/api/version || echo OPEN_WEBUI_API_DOWN").strip()
    return (
        "ISLA ops webui status\n\n"
        f"container: {container or 'OPEN_WEBUI_CONTAINER_DOWN'}\n"
        f"api: {version}"
    )


def status_qdrant() -> str:
    container = run_command(
        ["docker", "ps", "--filter", "name=qdrant", "--format", "{{.Names}}\t{{.Status}}"]
    ).strip()
    collections = run_shell("curl -fsS http://127.0.0.1:6333/collections || echo QDRANT_API_DOWN").strip()
    return (
        "ISLA ops qdrant status\n\n"
        f"container: {container or 'QDRANT_CONTAINER_DOWN'}\n"
        f"collections: {collections}"
    )


def status_golden() -> str:
    return run_command(["/home/ai/bin/isla-v2-promote", "--show"])


STATUS_HANDLERS: dict[str, Callable[[], str]] = {
    "crew_sidecar": status_sidecar,
    "main_stack": status_main_stack,
    "v2_bot": status_v2,
    "gateway": status_gateway,
    "watchdog": status_watchdog,
    "ollama": status_ollama,
    "webui": status_webui,
    "qdrant": status_qdrant,
    "golden": status_golden,
}

LOG_HANDLERS: dict[str, Callable[[], str]] = {
    "crew_sidecar": lambda: tail_lines(run_command(["/home/ai/bin/isla-crew-logs"]), 40),
    "v2_bot": logs_v2,
    "gateway": logs_gateway,
    "watchdog": logs_watchdog,
    "ollama": logs_ollama,
}


def get_status(target: str) -> str:
    handler = STATUS_HANDLERS.get(target)
    if handler is None:
        return f"UNKNOWN_TARGET: {target}"
    return handler()


def get_logs(target: str) -> str:
    handler = LOG_HANDLERS.get(target)
    if handler is None:
        return f"UNKNOWN_LOG_TARGET: {target}"
    return handler()


def main() -> None:
    parser = argparse.ArgumentParser(description="ISLA v2 ops status")
    parser.add_argument("mode", choices=("status", "logs"))
    parser.add_argument("target")
    args = parser.parse_args()

    if args.mode == "status":
        print(get_status(args.target))
    else:
        print(get_logs(args.target))


if __name__ == "__main__":
    main()
