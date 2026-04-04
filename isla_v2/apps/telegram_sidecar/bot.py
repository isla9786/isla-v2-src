import asyncio
import html
import os
import re
import subprocess

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from isla_v2.core.memory.fact_store import (
    delete_fact,
    get_fact,
    get_fact_history,
    list_facts,
    search_facts,
    set_fact,
)
from isla_v2.core.memory.note_store import add_note, recent_notes, search_notes
from isla_v2.core.router.responder import respond
from isla_v2.core.tools.ops_actions import maybe_run_action
from isla_v2.core.tools.ops_catalog import ops_help_text, unknown_ops_text

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USER_IDS = {
    int(x.strip())
    for x in os.environ["TELEGRAM_ALLOWED_USER_IDS"].split(",")
    if x.strip()
}


def allowed(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id in ALLOWED_USER_IDS)


def help_main() -> str:
    return (
        "ISLA v2 is online.\n\n"
        "Main:\n"
        "/ask <prompt>\n"
        "/ops <command>\n"
        "/status [short|full|alert]\n"
        "/help\n"
        "/help facts\n"
        "/help ops\n\n"
        "Shortcuts:\n"
        "/hotel address\n"
        "/hotel phone\n"
        "/system canary\n\n"
        "Facts and notes:\n"
        "/factget <namespace> <key>\n"
        "/factlist <namespace>\n"
        "/factsearch <query>\n"
        "/facthistory <namespace> <key>\n"
        "/factset <namespace> <key> <value>\n"
        "/factdelete <namespace> <key>\n"
        "/noteadd <namespace> <text>\n"
        "/noterecent [namespace]\n"
        "/notesearch <query>"
    )


def help_facts() -> str:
    return (
        "Facts and notes help\n\n"
        "Usage:\n"
        "/factget <namespace> <key>\n"
        "/factlist <namespace>\n"
        "/factsearch <query>\n"
        "/facthistory <namespace> <key>\n"
        "/factset <namespace> <key> <value>\n"
        "/factdelete <namespace> <key>\n"
        "/noteadd <namespace> <text>\n"
        "/noterecent [namespace]\n"
        "/notesearch <query>\n\n"
        "Examples:\n"
        "/factget aquari_hotel address\n"
        "/factlist aquari_hotel\n"
        "/factsearch bridge\n"
        "/facthistory system bridge_canary\n"
        "/factset system test_key hello_from_telegram\n"
        "/factdelete system test_key\n"
        "/noteadd project observed a transient gateway timeout\n"
        "/noterecent project\n"
        "/notesearch gateway timeout\n\n"
        "Shortcuts:\n"
        "/hotel address\n"
        "/hotel phone\n"
        "/system canary"
    )


def help_ops() -> str:
    return ops_help_text()


def render_fact_row(row: dict) -> str:
    ttl_part = f" [expires_at={row['expires_at']}]" if row.get("expires_at") else ""
    return (
        f"{row['namespace']}.{row['key']} = {row['value']} "
        f"[source={row['source']}] [state={row['state']}]"
        f"{ttl_part}"
    )


def render_fact_history_row(row: dict) -> str:
    ttl_part = f" [expires_at={row['expires_at']}]" if row.get("expires_at") else ""
    return (
        f"{row['operation']} {row['namespace']}.{row['key']} = {row.get('value')} "
        f"[source={row['source']}] [updated_at={row['updated_at']}] [state={row['state']}]"
        f"{ttl_part}"
    )


def render_note_row(row: dict) -> str:
    return (
        f"#{row['id']} {row['namespace']}: {row['body']} "
        f"[kind={row['kind']}] [source={row['source']}] [created_at={row['created_at']}]"
    )

def clip(text: str, limit: int = 3200) -> str:
    text = text or "No output."
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n...[truncated]"


async def send_plain(update: Update, text: str) -> None:
    await update.message.reply_text(clip(text))


async def send_block(update: Update, text: str) -> None:
    body = html.escape(clip(text))
    await update.message.reply_html(f"<pre>{body}</pre>")


def run_text(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = "\n".join(x for x in [proc.stdout, proc.stderr] if x.strip()).strip()
    return out if out else "NO_OUTPUT"


def extract_pid(text: str) -> str:
    m = re.search(r"Main PID:\s+(\d+)", text)
    return m.group(1) if m else "unknown"


def yes_no(ok: bool, good: str = "OK", bad: str = "ISSUE") -> str:
    return good if ok else bad


def sidecar_is_retired() -> bool:
    sidecar_unit_status = run_text(["systemctl", "--user", "status", "isla-crew-bot.service", "--no-pager"])
    return "Unit isla-crew-bot.service could not be found." in sidecar_unit_status


def sidecar_state() -> tuple[str, bool, bool, str, bool, bool, str]:
    sidecar_raw = run_text(["/home/ai/bin/isla-crew-check"])
    sidecar_retired = sidecar_is_retired()
    sidecar_active = sidecar_retired or "[OK]   service is active" in sidecar_raw
    sidecar_pid_match = re.search(r"\[OK\]\s+bot pid:\s+(\d+)", sidecar_raw)
    sidecar_pid = "retired" if sidecar_retired else (sidecar_pid_match.group(1) if sidecar_pid_match else "unknown")
    sidecar_caps = sidecar_retired or "[OK]   no capability error" in sidecar_raw
    sidecar_poll = sidecar_retired or "[OK]   no Telegram polling conflict" in sidecar_raw
    sidecar_label = "RETIRED" if sidecar_retired else yes_no(sidecar_active, "RUNNING", "DOWN")
    return sidecar_raw, sidecar_retired, sidecar_active, sidecar_pid, sidecar_caps, sidecar_poll, sidecar_label


def dashboard_text() -> str:
    v2_raw = run_text(["systemctl", "--user", "status", "isla-v2-bot.service", "--no-pager"])
    _, _, sidecar_active, sidecar_pid, sidecar_caps, sidecar_poll, sidecar_label = sidecar_state()
    main_raw = run_text(["/home/ai/bin/isla-check"])

    v2_running = "Active: active (running)" in v2_raw
    v2_pid = extract_pid(v2_raw)

    gateway_ok = "[OK]   OpenClaw Gateway is active" in main_raw
    ollama_ok = "[OK]   Ollama API reachable" in main_raw
    webui_ok = "[OK]   Open WebUI API reachable" in main_raw
    qdrant_ok = "[OK]   Qdrant API reachable" in main_raw

    hotel_address = get_fact("aquari_hotel", "address") or "missing"
    hotel_phone = get_fact("aquari_hotel", "phone") or "missing"
    canary = get_fact("system", "bridge_canary") or "missing"

    return (
        "ISLA v2 dashboard\n\n"
        "Bots\n"
        f"- v2 bot: {yes_no(v2_running, 'RUNNING', 'DOWN')} (pid {v2_pid})\n"
        f"- crew sidecar: {sidecar_label} (pid {sidecar_pid})\n"
        f"- sidecar capability state: {yes_no(sidecar_caps)}\n"
        f"- sidecar polling state: {yes_no(sidecar_poll)}\n\n"
        "Main stack\n"
        f"- gateway: {yes_no(gateway_ok)}\n"
        f"- ollama: {yes_no(ollama_ok)}\n"
        f"- webui: {yes_no(webui_ok)}\n"
        f"- qdrant: {yes_no(qdrant_ok)}\n\n"
        "Trusted facts\n"
        f"- hotel address: {hotel_address}\n"
        f"- hotel phone: {hotel_phone}\n"
        f"- bridge canary: {canary}"
    )


def dashboard_text_mode(mode: str = "short") -> str:
    mode = (mode or "short").strip().lower()

    v2_raw = run_text(["systemctl", "--user", "status", "isla-v2-bot.service", "--no-pager"])
    _, sidecar_retired, sidecar_active, sidecar_pid, sidecar_caps, sidecar_poll, sidecar_label = sidecar_state()
    main_raw = run_text(["/home/ai/bin/isla-check"])

    v2_running = "Active: active (running)" in v2_raw
    v2_pid = extract_pid(v2_raw)

    gateway_ok = "[OK]   OpenClaw Gateway is active" in main_raw
    ollama_ok = "[OK]   Ollama API reachable" in main_raw
    webui_ok = "[OK]   Open WebUI API reachable" in main_raw
    qdrant_ok = "[OK]   Qdrant API reachable" in main_raw

    hotel_address = get_fact("aquari_hotel", "address") or "missing"
    hotel_phone = get_fact("aquari_hotel", "phone") or "missing"
    canary = get_fact("system", "bridge_canary") or "missing"

    if mode == "short":
        return (
            "ISLA v2 status (short)\n\n"
            f"- v2 bot: {yes_no(v2_running, 'RUNNING', 'DOWN')} (pid {v2_pid})\n"
            f"- crew sidecar: {sidecar_label} (pid {sidecar_pid})\n"
            f"- sidecar capability: {yes_no(sidecar_caps)}\n"
            f"- sidecar polling: {yes_no(sidecar_poll)}\n"
            f"- gateway: {yes_no(gateway_ok)}\n"
            f"- ollama: {yes_no(ollama_ok)}\n"
            f"- webui: {yes_no(webui_ok)}\n"
            f"- qdrant: {yes_no(qdrant_ok)}\n"
            f"- canary: {canary}"
        )

    if mode == "alert":
        issues = []

        if not v2_running:
            issues.append(f"- v2 bot DOWN (pid {v2_pid})")
        if not sidecar_retired and not sidecar_active:
            issues.append(f"- crew sidecar DOWN (pid {sidecar_pid})")
        if not sidecar_retired and not sidecar_caps:
            issues.append("- sidecar capability state not OK")
        if not sidecar_retired and not sidecar_poll:
            issues.append("- sidecar polling state not OK")
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
                "ISLA v2 status (alert)\n\n"
                "No active issues detected.\n"
                f"- v2 bot RUNNING (pid {v2_pid})\n"
                f"- crew sidecar {sidecar_label} (pid {sidecar_pid})\n"
                "- main stack healthy\n"
                f"- canary present: {canary}"
            )

        return "ISLA v2 status (alert)\n\n" + "\n".join(issues)

    return (
        "ISLA v2 dashboard (full)\n\n"
        "Bots\n"
        f"- v2 bot: {yes_no(v2_running, 'RUNNING', 'DOWN')} (pid {v2_pid})\n"
        f"- crew sidecar: {sidecar_label} (pid {sidecar_pid})\n"
        f"- sidecar capability state: {yes_no(sidecar_caps)}\n"
        f"- sidecar polling state: {yes_no(sidecar_poll)}\n\n"
        "Main stack\n"
        f"- gateway: {yes_no(gateway_ok)}\n"
        f"- ollama: {yes_no(ollama_ok)}\n"
        f"- webui: {yes_no(webui_ok)}\n"
        f"- qdrant: {yes_no(qdrant_ok)}\n\n"
        "Trusted facts\n"
        f"- hotel address: {hotel_address}\n"
        f"- hotel phone: {hotel_phone}\n"
        f"- bridge canary: {canary}"
    )


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await update.message.reply_text("Unauthorized.")
        return
    await update.message.reply_text(help_main())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await update.message.reply_text("Unauthorized.")
        return

    topic = " ".join(context.args).strip().lower()

    if not topic:
        await update.message.reply_text(help_main())
        return
    if topic == "facts":
        await update.message.reply_text(help_facts())
        return
    if topic == "ops":
        await update.message.reply_text(help_ops())
        return

    await update.message.reply_text("Usage: /help, /help facts, or /help ops")


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await update.message.reply_text("Unauthorized.")
        return

    mode = " ".join(context.args).strip().lower()
    if mode == "":
        mode = "short"

    if mode not in {"short", "full", "alert"}:
        await update.message.reply_text("Usage: /status, /status short, /status full, or /status alert")
        return

    try:
        text = await asyncio.to_thread(dashboard_text_mode, mode)
        await send_block(update, text)
    except Exception as e:
        await update.message.reply_text(f"status failed: {e}")


async def ask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await update.message.reply_text("Unauthorized.")
        return

    prompt = " ".join(context.args).strip()
    if not prompt:
        await update.message.reply_text("Usage: /ask <prompt>")
        return

    try:
        result = await asyncio.to_thread(respond, prompt, update.effective_user.id)

        low = prompt.lower()
        looks_ops = any(
            x in low for x in [
                "status", "logs", "health", "restart",
                "sidecar", "main stack", "isla v2 bot"
            ]
        )

        if looks_ops or "\n" in result:
            await send_block(update, result)
        else:
            await send_plain(update, result)
    except Exception as e:
        await update.message.reply_text(f"ISLA v2 failed: {e}")


async def ops_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await update.message.reply_text("Unauthorized.")
        return

    raw = (update.message.text or "").strip()
    args = getattr(context, "args", None)

    if isinstance(args, (list, tuple)):
        text = " ".join(args).strip()
    elif raw.startswith("/ops"):
        text = raw[len("/ops"):].strip()
    else:
        text = raw
    if not text:
        await update.message.reply_text(help_ops())
        return

    user_id = update.effective_user.id

    try:
        result = await asyncio.to_thread(maybe_run_action, text, user_id)
        if result is not None:
            if "\n" in result:
                await send_block(update, result)
            else:
                await send_plain(update, result)
            return
    except Exception as e:
        await update.message.reply_text(f"ops failed: {e}")
        return

    await send_block(update, unknown_ops_text(text))

async def factget_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await update.message.reply_text("Unauthorized.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Usage: /factget <namespace> <key>")
        return

    namespace, key = context.args
    try:
        value = await asyncio.to_thread(get_fact, namespace, key)
        if value is None:
            await update.message.reply_text("FACT_NOT_FOUND")
            return
        await send_plain(update, f"{namespace}.{key} = {value}")
    except Exception as e:
        await update.message.reply_text(f"factget failed: {e}")


async def factlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await update.message.reply_text("Unauthorized.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Usage: /factlist <namespace>")
        return

    namespace = context.args[0]
    try:
        rows = await asyncio.to_thread(list_facts, namespace)
        if not rows:
            await update.message.reply_text("NO_FACTS_FOUND")
            return

        lines = [render_fact_row(row) for row in rows]
        await send_block(update, "\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"factlist failed: {e}")


async def factsearch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await update.message.reply_text("Unauthorized.")
        return

    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text("Usage: /factsearch <query>")
        return

    try:
        rows = await asyncio.to_thread(search_facts, query)
        if not rows:
            await update.message.reply_text("NO_FACTS_FOUND")
            return
        await send_block(update, "\n".join(render_fact_row(row) for row in rows))
    except Exception as e:
        await update.message.reply_text(f"factsearch failed: {e}")


async def facthistory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await update.message.reply_text("Unauthorized.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Usage: /facthistory <namespace> <key>")
        return

    namespace, key = context.args
    try:
        rows = await asyncio.to_thread(get_fact_history, namespace, key)
        if not rows:
            await update.message.reply_text("NO_FACT_HISTORY")
            return
        await send_block(update, "\n".join(render_fact_history_row(row) for row in rows))
    except Exception as e:
        await update.message.reply_text(f"facthistory failed: {e}")


async def factset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await update.message.reply_text("Unauthorized.")
        return

    if len(context.args) < 3:
        await update.message.reply_text("Usage: /factset <namespace> <key> <value>")
        return

    namespace = context.args[0]
    key = context.args[1]
    value = " ".join(context.args[2:]).strip()

    try:
        await asyncio.to_thread(set_fact, namespace, key, value, "telegram_manual")
        await update.message.reply_text(f"SET_OK: {namespace}.{key}")
    except Exception as e:
        await update.message.reply_text(f"factset failed: {e}")


async def factdelete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await update.message.reply_text("Unauthorized.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Usage: /factdelete <namespace> <key>")
        return

    namespace, key = context.args
    try:
        ok = await asyncio.to_thread(delete_fact, namespace, key)
        if ok:
            await update.message.reply_text(f"DELETE_OK: {namespace}.{key}")
        else:
            await update.message.reply_text(f"DELETE_NOT_FOUND: {namespace}.{key}")
    except Exception as e:
        await update.message.reply_text(f"factdelete failed: {e}")


async def noteadd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await update.message.reply_text("Unauthorized.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /noteadd <namespace> <text>")
        return

    namespace = context.args[0]
    body = " ".join(context.args[1:]).strip()

    try:
        note_id = await asyncio.to_thread(add_note, namespace, body, "telegram_manual", "note")
        await update.message.reply_text(f"NOTE_OK: {namespace}#{note_id}")
    except Exception as e:
        await update.message.reply_text(f"noteadd failed: {e}")


async def noterecent_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await update.message.reply_text("Unauthorized.")
        return

    if len(context.args) > 1:
        await update.message.reply_text("Usage: /noterecent [namespace]")
        return

    namespace = context.args[0] if context.args else None

    try:
        rows = await asyncio.to_thread(recent_notes, namespace)
        if not rows:
            await update.message.reply_text("NO_NOTES_FOUND")
            return
        await send_block(update, "\n".join(render_note_row(row) for row in rows))
    except Exception as e:
        await update.message.reply_text(f"noterecent failed: {e}")


async def notesearch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await update.message.reply_text("Unauthorized.")
        return

    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text("Usage: /notesearch <query>")
        return

    try:
        rows = await asyncio.to_thread(search_notes, query)
        if not rows:
            await update.message.reply_text("NO_NOTES_FOUND")
            return
        await send_block(update, "\n".join(render_note_row(row) for row in rows))
    except Exception as e:
        await update.message.reply_text(f"notesearch failed: {e}")


async def hotel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await update.message.reply_text("Unauthorized.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Usage: /hotel address or /hotel phone")
        return

    item = context.args[0].strip().lower()
    key_map = {
        "address": "address",
        "phone": "phone",
    }

    key = key_map.get(item)
    if not key:
        await update.message.reply_text("Usage: /hotel address or /hotel phone")
        return

    value = await asyncio.to_thread(get_fact, "aquari_hotel", key)
    if value is None:
        await update.message.reply_text("FACT_NOT_FOUND")
        return

    await send_plain(update, value)


async def system_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await update.message.reply_text("Unauthorized.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Usage: /system canary")
        return

    item = context.args[0].strip().lower()
    if item != "canary":
        await update.message.reply_text("Usage: /system canary")
        return

    value = await asyncio.to_thread(get_fact, "system", "bridge_canary")
    if value is None:
        await update.message.reply_text("FACT_NOT_FOUND")
        return

    await send_plain(update, value)


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    raw0 = (update.message.text or "").strip()
    if raw0.startswith("/ops"):
        await ops_cmd(update, context)
        return

    if not allowed(update):
        await update.message.reply_text("Unauthorized.")
        return

    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Empty message.")
        return

    try:
        result = await asyncio.to_thread(respond, text, update.effective_user.id)
        if "\n" in result:
            await send_block(update, result)
        else:
            await send_plain(update, result)
    except Exception as e:
        await update.message.reply_text(f"ISLA v2 failed: {e}")


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("ask", ask_cmd))
    app.add_handler(CommandHandler("ops", ops_cmd))
    app.add_handler(CommandHandler("factget", factget_cmd))
    app.add_handler(CommandHandler("factlist", factlist_cmd))
    app.add_handler(CommandHandler("factsearch", factsearch_cmd))
    app.add_handler(CommandHandler("facthistory", facthistory_cmd))
    app.add_handler(CommandHandler("factset", factset_cmd))
    app.add_handler(CommandHandler("factdelete", factdelete_cmd))
    app.add_handler(CommandHandler("noteadd", noteadd_cmd))
    app.add_handler(CommandHandler("noterecent", noterecent_cmd))
    app.add_handler(CommandHandler("notesearch", notesearch_cmd))
    app.add_handler(CommandHandler("hotel", hotel_cmd))
    app.add_handler(CommandHandler("system", system_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
