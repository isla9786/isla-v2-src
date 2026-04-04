from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_DIR = Path("/home/ai/ai-agents")
ENV_FILE = BASE_DIR / "isla_v2" / "secrets" / "isla_v2_bot.env"
STATE_DIR = BASE_DIR / "isla_v2" / "data" / "watchdog"
STATE_FILE = STATE_DIR / "state.json"

AUTO_RECOVERY_ENABLED = True


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data

    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def get_bot_config() -> tuple[str, list[str]]:
    file_env = parse_env_file(ENV_FILE)

    token = os.getenv("TELEGRAM_BOT_TOKEN") or file_env.get("TELEGRAM_BOT_TOKEN", "")
    allowed = os.getenv("TELEGRAM_ALLOWED_USER_IDS") or file_env.get("TELEGRAM_ALLOWED_USER_IDS", "")

    ids = [x.strip() for x in allowed.split(",") if x.strip()]
    if not token:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
    if not ids:
        raise RuntimeError("Missing TELEGRAM_ALLOWED_USER_IDS")

    return token, ids


def run_text(cmd: list[str], timeout: int = 30) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = "\n".join(x for x in [proc.stdout, proc.stderr] if x.strip()).strip()
        return out if out else "NO_OUTPUT"
    except Exception as e:
        return f"COMMAND_ERROR: {' '.join(cmd)} :: {e}"


def load_state() -> dict:
    ensure_dirs()
    if not STATE_FILE.exists():
        return {
            "last_status": "unknown",
            "last_fingerprint": "",
            "last_sent_at": "",
            "last_ok_at": "",
        }
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {
            "last_status": "unknown",
            "last_fingerprint": "",
            "last_sent_at": "",
            "last_ok_at": "",
        }


def save_state(state: dict) -> None:
    ensure_dirs()
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def send_telegram_message(text: str) -> None:
    token, user_ids = get_bot_config()
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    ok_count = 0
    failures: list[str] = []

    for chat_id in user_ids:
        payload = urlencode(
            {
                "chat_id": chat_id,
                "text": text,
            }
        ).encode()

        req = Request(
            url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        try:
            with urlopen(req, timeout=20) as resp:
                resp.read()
            ok_count += 1
        except HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = "<unreadable>"
            failures.append(f"TELEGRAM_SEND_FAIL chat_id={chat_id} http={e.code} body={body}")
        except Exception as e:
            failures.append(f"TELEGRAM_SEND_FAIL chat_id={chat_id} err={e}")

    print(f"TELEGRAM_OK_COUNT={ok_count}")
    for item in failures:
        print(item)

    if ok_count == 0:
        raise RuntimeError("Telegram send failed for all configured chat IDs")


def fingerprint_for_issues(issues: list[str]) -> str:
    if not issues:
        return "ok"
    joined = "\n".join(sorted(issues))
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def sidecar_is_retired() -> bool:
    status = run_text(["systemctl", "--user", "status", "isla-crew-bot.service", "--no-pager"])
    return "Unit isla-crew-bot.service could not be found." in status


def evaluate() -> dict:
    v2_status = run_text(["systemctl", "--user", "is-active", "isla-v2-bot.service"]).strip()
    v2_ok = v2_status == "active"

    sidecar_raw = run_text(["/home/ai/bin/isla-crew-check"])
    sidecar_retired = sidecar_is_retired()
    sidecar_active = sidecar_retired or "[OK]   service is active" in sidecar_raw
    sidecar_caps = sidecar_retired or "[OK]   no capability error" in sidecar_raw
    sidecar_poll = sidecar_retired or "[OK]   no Telegram polling conflict" in sidecar_raw

    main_raw = run_text(["/home/ai/bin/isla-check"])
    gateway_ok = "[OK]   OpenClaw Gateway is active" in main_raw
    ollama_ok = "[OK]   Ollama API reachable" in main_raw
    webui_ok = "[OK]   Open WebUI API reachable" in main_raw
    qdrant_ok = "[OK]   Qdrant API reachable" in main_raw

    issues: list[str] = []

    if not v2_ok:
        issues.append(f"- ISLA v2 bot not active ({v2_status})")
    if not sidecar_retired and not sidecar_active:
        issues.append("- crew sidecar not active")
    if not sidecar_retired and not sidecar_caps:
        issues.append("- crew sidecar capability issue detected")
    if not sidecar_retired and not sidecar_poll:
        issues.append("- crew sidecar polling conflict detected")
    if not gateway_ok:
        issues.append("- gateway not OK")
    if not ollama_ok:
        issues.append("- ollama API not OK")
    if not webui_ok:
        issues.append("- open-webui not OK")
    if not qdrant_ok:
        issues.append("- qdrant not OK")

    snapshot = {
        "v2": "OK" if v2_ok else f"FAIL ({v2_status})",
        "sidecar": "RETIRED" if sidecar_retired else ("OK" if sidecar_active else "FAIL"),
        "sidecar_caps": "RETIRED" if sidecar_retired else ("OK" if sidecar_caps else "FAIL"),
        "sidecar_poll": "RETIRED" if sidecar_retired else ("OK" if sidecar_poll else "FAIL"),
        "gateway": "OK" if gateway_ok else "FAIL",
        "ollama": "OK" if ollama_ok else "FAIL",
        "webui": "OK" if webui_ok else "FAIL",
        "qdrant": "OK" if qdrant_ok else "FAIL",
    }

    checks = {
        "v2_ok": v2_ok,
        "sidecar_retired": sidecar_retired,
        "sidecar_active": sidecar_active,
        "sidecar_caps": sidecar_caps,
        "sidecar_poll": sidecar_poll,
        "gateway_ok": gateway_ok,
        "ollama_ok": ollama_ok,
        "webui_ok": webui_ok,
        "qdrant_ok": qdrant_ok,
    }

    return {
        "issues": issues,
        "snapshot": snapshot,
        "checks": checks,
        "fingerprint": fingerprint_for_issues(issues),
        "main_raw": main_raw,
        "sidecar_raw": sidecar_raw,
    }


def attempt_auto_recovery(report: dict) -> tuple[list[str], dict]:
    checks = report["checks"]
    actions: list[str] = []

    if not AUTO_RECOVERY_ENABLED:
        return actions, report

    if not checks["v2_ok"]:
        run_text(["systemctl", "--user", "restart", "isla-v2-bot.service"])
        run_text(["/usr/bin/bash", "-lc", "sleep 2"])
        actions.append("- restarted isla-v2-bot.service")

    if (not checks["sidecar_retired"]) and (
        (not checks["sidecar_active"]) or (not checks["sidecar_caps"]) or (not checks["sidecar_poll"])
    ):
        run_text(["systemctl", "--user", "restart", "isla-crew-bot.service"])
        run_text(["/usr/bin/bash", "-lc", "sleep 2"])
        actions.append("- restarted isla-crew-bot.service")

    if not checks["gateway_ok"]:
        run_text(["systemctl", "--user", "restart", "openclaw-gateway.service"])
        run_text(["/usr/bin/bash", "-lc", "sleep 2"])
        actions.append("- restarted openclaw-gateway.service")

    if (not checks["qdrant_ok"]) or (not checks["webui_ok"]):
        docker_names = run_text(["docker", "ps", "--format", "{{.Names}}"])
        names = {x.strip() for x in docker_names.splitlines() if x.strip()}

        if not checks["qdrant_ok"]:
            if "qdrant" in names:
                run_text(["docker", "restart", "qdrant"])
                actions.append("- restarted qdrant container")
            else:
                run_text(["docker", "start", "qdrant"])
                actions.append("- started qdrant container")

        if not checks["webui_ok"]:
            if "open-webui" in names:
                run_text(["docker", "restart", "open-webui"])
                actions.append("- restarted open-webui container")
            else:
                run_text(["docker", "start", "open-webui"])
                actions.append("- started open-webui container")

        run_text(["/usr/bin/bash", "-lc", "sleep 3"])

    if not checks["ollama_ok"]:
        proc = subprocess.run(
            ["sudo", "/usr/local/bin/isla-rootctl", "restart", "ollama"],
            capture_output=True,
            text=True,
        )
        out = "\n".join(x for x in [proc.stdout, proc.stderr] if x.strip()).strip()
        actions.append(
            f"- attempted privileged ollama restart (rc={proc.returncode})"
            + (f": {out}" if out else "")
        )
        run_text(["/usr/bin/bash", "-lc", "sleep 2"])

    after = evaluate()
    return actions, after

def render_alert_text(report: dict, actions: list[str] | None = None) -> str:
    s = report["snapshot"]
    issues = report["issues"]

    msg = (
        "ISLA watchdog alert\n\n"
        "Detected issues:\n"
        + "\n".join(issues)
        + "\n\n"
    )

    if actions:
        msg += "Auto-recovery actions attempted:\n" + "\n".join(actions) + "\n\n"

    msg += (
        "Snapshot:\n"
        f"- v2 bot: {s['v2']}\n"
        f"- crew sidecar: {s['sidecar']}\n"
        f"- sidecar capability: {s['sidecar_caps']}\n"
        f"- sidecar polling: {s['sidecar_poll']}\n"
        f"- gateway: {s['gateway']}\n"
        f"- ollama: {s['ollama']}\n"
        f"- webui: {s['webui']}\n"
        f"- qdrant: {s['qdrant']}\n\n"
        f"Time: {utc_now()}"
    )
    return msg


def render_recovery_text(report: dict) -> str:
    s = report["snapshot"]

    return (
        "ISLA watchdog recovery\n\n"
        "All monitored services look healthy again.\n\n"
        "Snapshot:\n"
        f"- v2 bot: {s['v2']}\n"
        f"- crew sidecar: {s['sidecar']}\n"
        f"- sidecar capability: {s['sidecar_caps']}\n"
        f"- sidecar polling: {s['sidecar_poll']}\n"
        f"- gateway: {s['gateway']}\n"
        f"- ollama: {s['ollama']}\n"
        f"- webui: {s['webui']}\n"
        f"- qdrant: {s['qdrant']}\n\n"
        f"Time: {utc_now()}"
    )


def render_auto_recovery_success_text(before: dict, after: dict, actions: list[str]) -> str:
    s = after["snapshot"]

    return (
        "ISLA watchdog auto-recovery\n\n"
        "Detected issues were cleared automatically.\n\n"
        "Actions taken:\n"
        + "\n".join(actions)
        + "\n\n"
        + "Snapshot:\n"
        f"- v2 bot: {s['v2']}\n"
        f"- crew sidecar: {s['sidecar']}\n"
        f"- sidecar capability: {s['sidecar_caps']}\n"
        f"- sidecar polling: {s['sidecar_poll']}\n"
        f"- gateway: {s['gateway']}\n"
        f"- ollama: {s['ollama']}\n"
        f"- webui: {s['webui']}\n"
        f"- qdrant: {s['qdrant']}\n\n"
        f"Time: {utc_now()}"
    )


def render_show_text(report: dict) -> str:
    s = report["snapshot"]
    issues = report["issues"]

    header = "ISLA watchdog status\n\n"
    if issues:
        body = "Detected issues:\n" + "\n".join(issues)
    else:
        body = "No active issues detected."

    tail = (
        "\n\nSnapshot:\n"
        f"- v2 bot: {s['v2']}\n"
        f"- crew sidecar: {s['sidecar']}\n"
        f"- sidecar capability: {s['sidecar_caps']}\n"
        f"- sidecar polling: {s['sidecar_poll']}\n"
        f"- gateway: {s['gateway']}\n"
        f"- ollama: {s['ollama']}\n"
        f"- webui: {s['webui']}\n"
        f"- qdrant: {s['qdrant']}\n"
        f"- auto-recovery: {'ENABLED' if AUTO_RECOVERY_ENABLED else 'DISABLED'}\n"
    )
    return header + body + tail


def process_once(force_alert: bool = False, show_only: bool = False) -> int:
    report = evaluate()

    if show_only:
        print(render_show_text(report))
        return 0

    state = load_state()
    now = utc_now()

    if force_alert:
        msg = render_alert_text(
            report if report["issues"] else {
                **report,
                "issues": ["- manual watchdog test alert"],
                "fingerprint": "manual-test",
            }
        )
        send_telegram_message(msg)
        state["last_sent_at"] = now
        save_state(state)
        print("WATCHDOG_FORCE_ALERT_SENT")
        return 0

    issues = report["issues"]
    fp = report["fingerprint"]

    if issues:
        is_new_issue = (
            state.get("last_status") != "alert"
            or state.get("last_fingerprint") != fp
        )

        if is_new_issue and AUTO_RECOVERY_ENABLED:
            actions, after = attempt_auto_recovery(report)

            if actions:
                if after["issues"]:
                    send_telegram_message(render_alert_text(after, actions=actions))
                    state["last_status"] = "alert"
                    state["last_fingerprint"] = after["fingerprint"]
                    state["last_sent_at"] = now
                    save_state(state)
                    print("WATCHDOG_ALERT_SENT_AFTER_RECOVERY")
                    return 0

                send_telegram_message(render_auto_recovery_success_text(report, after, actions))
                state["last_status"] = "ok"
                state["last_fingerprint"] = "ok"
                state["last_sent_at"] = now
                state["last_ok_at"] = now
                save_state(state)
                print("WATCHDOG_AUTO_RECOVERY_SUCCESS_SENT")
                return 0

        if is_new_issue:
            send_telegram_message(render_alert_text(report))
            state["last_sent_at"] = now

        state["last_status"] = "alert"
        state["last_fingerprint"] = fp
        save_state(state)
        print("WATCHDOG_ALERT" if is_new_issue else "WATCHDOG_NO_CHANGE")
        return 0

    was_alerting = state.get("last_status") == "alert"
    state["last_status"] = "ok"
    state["last_fingerprint"] = "ok"
    state["last_ok_at"] = now
    save_state(state)

    if was_alerting:
        send_telegram_message(render_recovery_text(report))
        state["last_sent_at"] = now
        save_state(state)
        print("WATCHDOG_RECOVERY_SENT")
    else:
        print("WATCHDOG_OK")

    return 0


def clear_state() -> int:
    if STATE_FILE.exists():
        STATE_FILE.unlink()
        print(f"STATE_CLEARED: {STATE_FILE}")
    else:
        print("STATE_ALREADY_CLEAR")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="ISLA v2 watchdog")
    parser.add_argument("--once", action="store_true", help="Run one check now (compat mode)")
    parser.add_argument("--show", action="store_true", help="Print current watchdog view without sending alerts")
    parser.add_argument("--force-alert", action="store_true", help="Send a manual test alert now")
    parser.add_argument("--clear-state", action="store_true", help="Clear stored watchdog state")
    args = parser.parse_args()

    if args.clear_state:
        raise SystemExit(clear_state())
    if args.show:
        raise SystemExit(process_once(show_only=True))
    if args.force_alert:
        raise SystemExit(process_once(force_alert=True))
    if args.once:
        raise SystemExit(process_once())
    raise SystemExit(process_once())


if __name__ == "__main__":
    main()
