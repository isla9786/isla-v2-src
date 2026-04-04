from pathlib import Path

import pytest

from isla_v2.core.router import responder
from isla_v2.core.router.types import RouteDecision
from isla_v2.core.tools import ops_actions


@pytest.fixture(autouse=True)
def isolate_ops_state(monkeypatch, tmp_path: Path):
    ops_actions.PENDING_CONFIRMS.clear()
    monkeypatch.setattr(ops_actions, "OPS_AUDIT_LOG", tmp_path / "ops-audit.log")
    yield
    ops_actions.PENDING_CONFIRMS.clear()


def test_recover_main_uses_shared_confirmation_path(monkeypatch):
    monkeypatch.setattr(ops_actions, "ops_recover_main_text", lambda: "RECOVER_MAIN_OK")

    request = ops_actions.maybe_run_action("recover main", user_id=77)
    assert request == 'Confirmation required. Send exactly: "confirm recover main"'

    result = ops_actions.maybe_run_action("confirm recover main", user_id=77)
    assert result == "RECOVER_MAIN_OK"

    audit = ops_actions.OPS_AUDIT_LOG.read_text(encoding="utf-8")
    assert "action=confirm recover main" in audit
    assert "result=OK" in audit


def test_recover_all_confirmation_expires(monkeypatch):
    now = {"value": 1000.0}
    monkeypatch.setattr(ops_actions.time, "time", lambda: now["value"])

    request = ops_actions.maybe_run_action("recover all", user_id=5)
    assert request == 'Confirmation required. Send exactly: "confirm recover all"'

    now["value"] += ops_actions.CONFIRM_TTL_SECONDS + 1
    result = ops_actions.maybe_run_action("confirm recover all", user_id=5)
    assert result == ops_actions.confirmation_expired_text()

    audit = ops_actions.OPS_AUDIT_LOG.read_text(encoding="utf-8")
    assert "action=recover all" in audit
    assert "result=PENDING: confirm recover all" in audit
    assert "action=confirm recover all" in audit
    assert "result=EXPIRED_OR_MISSING" in audit


def test_confirm_restart_ollama_alias_reuses_force_restart_path(monkeypatch):
    monkeypatch.setattr(ops_actions, "ops_force_restart_ollama_text", lambda: "OLLAMA_FORCE_OK")

    request = ops_actions.maybe_run_action("force restart ollama", user_id=9)
    assert request == 'Confirmation required. Send exactly: "confirm force restart ollama"'

    result = ops_actions.maybe_run_action("confirm restart ollama", user_id=9)
    assert result == "OLLAMA_FORCE_OK"


def test_ollama_logs_returns_tailed_journal(monkeypatch):
    monkeypatch.setattr(ops_actions, "get_logs", lambda target: f"LOGS:{target}")

    result = ops_actions.maybe_run_action("ollama logs", user_id=1)
    assert result == "LOGS:ollama"


def test_plain_text_unknown_ops_is_deterministic(monkeypatch):
    monkeypatch.setattr(responder, "maybe_run_action", lambda prompt, user_id=None: None)
    monkeypatch.setattr(
        responder,
        "route_prompt",
        lambda prompt: RouteDecision(route="ops", reason="test"),
    )

    result = responder.respond("inspect mystery subsystem", user_id=3)
    assert result.startswith("UNKNOWN_OPS_COMMAND: inspect mystery subsystem")


def test_pending_confirms_tracks_canonical_confirm_text():
    ops_actions.maybe_run_action("restart gateway", user_id=88)
    pending = ops_actions.pending_confirms_text()
    assert "confirm restart gateway" in pending
