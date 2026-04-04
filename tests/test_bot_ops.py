import asyncio
import importlib
import sys
from types import SimpleNamespace


BOT_MODULE = "isla_v2.apps.telegram_sidecar.bot"


class FakeMessage:
    def __init__(self, text: str):
        self.text = text
        self.text_replies: list[str] = []
        self.html_replies: list[str] = []

    async def reply_text(self, text: str):
        self.text_replies.append(text)

    async def reply_html(self, text: str):
        self.html_replies.append(text)


class FakeUpdate:
    def __init__(self, text: str, user_id: int = 42):
        self.message = FakeMessage(text)
        self.effective_user = SimpleNamespace(id=user_id, username="tester")


def load_bot(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:TEST")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")
    sys.modules.pop(BOT_MODULE, None)
    return importlib.import_module(BOT_MODULE)


def test_ops_cmd_uses_shared_action_response(monkeypatch):
    bot = load_bot(monkeypatch)
    monkeypatch.setattr(bot, "allowed", lambda update: True)
    monkeypatch.setattr(bot, "maybe_run_action", lambda text, user_id=None: "ISLA ops ollama logs\n\nline1")

    update = FakeUpdate("/ops ollama logs")
    context = SimpleNamespace(args=["ollama", "logs"])

    asyncio.run(bot.ops_cmd(update, context))

    assert update.message.html_replies
    assert "ISLA ops ollama logs" in update.message.html_replies[-1]


def test_ops_cmd_returns_deterministic_unknown_help(monkeypatch):
    bot = load_bot(monkeypatch)
    monkeypatch.setattr(bot, "allowed", lambda update: True)
    monkeypatch.setattr(bot, "maybe_run_action", lambda text, user_id=None: None)
    monkeypatch.setattr(bot, "unknown_ops_text", lambda text: f"UNKNOWN_OPS_COMMAND: {text}")

    update = FakeUpdate("/ops not real")
    context = SimpleNamespace(args=["not", "real"])

    asyncio.run(bot.ops_cmd(update, context))

    assert update.message.html_replies
    assert "UNKNOWN_OPS_COMMAND: not real" in update.message.html_replies[-1]


def test_ops_cmd_without_args_returns_help_when_context_args_is_none(monkeypatch):
    bot = load_bot(monkeypatch)
    monkeypatch.setattr(bot, "allowed", lambda update: True)

    update = FakeUpdate("/ops")
    context = SimpleNamespace(args=None)

    asyncio.run(bot.ops_cmd(update, context))

    assert update.message.text_replies
    assert update.message.text_replies[-1].startswith("Ops help")


def test_text_handler_routes_slash_ops_without_context_args(monkeypatch):
    bot = load_bot(monkeypatch)
    monkeypatch.setattr(bot, "allowed", lambda update: True)
    monkeypatch.setattr(bot, "maybe_run_action", lambda text, user_id=None: f"SEEN:{text}")

    update = FakeUpdate("/ops pending confirms")
    context = SimpleNamespace()

    asyncio.run(bot.text_handler(update, context))

    assert update.message.text_replies == ["SEEN:pending confirms"]


def test_text_handler_routes_ops_prefix_to_ops_cmd(monkeypatch):
    bot = load_bot(monkeypatch)

    async def fake_ops_cmd(update, context):
        await update.message.reply_text("ops-called")

    monkeypatch.setattr(bot, "ops_cmd", fake_ops_cmd)

    update = FakeUpdate("/ops v2 status")
    context = SimpleNamespace(args=None)

    asyncio.run(bot.text_handler(update, context))

    assert update.message.text_replies == ["ops-called"]


def test_help_ops_comes_from_catalog(monkeypatch):
    bot = load_bot(monkeypatch)
    body = bot.help_ops()
    assert body.startswith("Ops help")
    assert "/ops ollama logs" in body
    assert "/ops rollback report" in body


def test_help_facts_lists_note_and_search_commands(monkeypatch):
    bot = load_bot(monkeypatch)
    body = bot.help_facts()
    assert "/factsearch <query>" in body
    assert "/facthistory <namespace> <key>" in body
    assert "/noteadd <namespace> <text>" in body
    assert "/notesearch <query>" in body


def test_help_main_advertises_status_alert(monkeypatch):
    bot = load_bot(monkeypatch)
    body = bot.help_main()
    assert "/status [short|full|alert]" in body


def test_factsearch_cmd_renders_results(monkeypatch):
    bot = load_bot(monkeypatch)
    monkeypatch.setattr(bot, "allowed", lambda update: True)
    monkeypatch.setattr(
        bot,
        "search_facts",
        lambda query: [
            {
                "namespace": "system",
                "key": "bridge_canary",
                "value": "ok",
                "source": "test",
                "state": "active",
                "expires_at": None,
            }
        ],
    )

    update = FakeUpdate("/factsearch bridge")
    context = SimpleNamespace(args=["bridge"])

    asyncio.run(bot.factsearch_cmd(update, context))

    assert update.message.html_replies
    assert "system.bridge_canary = ok" in update.message.html_replies[-1]
