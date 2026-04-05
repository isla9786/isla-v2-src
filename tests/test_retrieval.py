from isla_v2.core.memory import retrieval
from isla_v2.core.router import responder
from isla_v2.core.router.types import RouteDecision


def test_grounding_disabled_returns_empty(monkeypatch):
    monkeypatch.delenv("ISLA_V2_ENABLE_CONTEXT_GROUNDING", raising=False)
    assert retrieval.build_grounding_context("bridge canary") == []


def test_grounding_enabled_is_bounded(monkeypatch):
    monkeypatch.setenv("ISLA_V2_ENABLE_CONTEXT_GROUNDING", "1")
    monkeypatch.setenv("ISLA_V2_GROUNDING_MAX_CHARS", "80")
    monkeypatch.setattr(
        retrieval,
        "search_facts",
        lambda prompt, limit=4: [
            {"namespace": "system", "key": "bridge_canary", "value": "green", "state": "active"}
        ],
    )
    monkeypatch.setattr(
        retrieval,
        "search_notes",
        lambda prompt, limit=4: [
            {"namespace": "project", "body": "Observed a short gateway timeout", "kind": "note"}
        ],
    )

    blocks = retrieval.build_grounding_context("bridge")
    assert blocks
    assert blocks[0].startswith("Authoritative facts:")
    assert sum(len(block) for block in blocks) <= 80


def test_grounding_degrades_safely_on_backend_failure(monkeypatch):
    monkeypatch.setenv("ISLA_V2_ENABLE_CONTEXT_GROUNDING", "1")

    def blow_up(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(retrieval, "search_facts", blow_up)
    monkeypatch.setattr(retrieval, "search_notes", blow_up)

    assert retrieval.build_grounding_context("bridge") == []


def test_responder_passes_context_blocks_to_broad_chat(monkeypatch):
    monkeypatch.setattr(responder, "maybe_run_action", lambda prompt, user_id=None: None)
    monkeypatch.setattr(
        responder,
        "route_prompt",
        lambda prompt: RouteDecision(route="broad_chat", reason="test"),
    )
    monkeypatch.setattr(responder, "get_broad_chat_answer", lambda prompt: None)
    monkeypatch.setattr(responder, "build_grounding_context", lambda prompt: ["Authoritative facts:\n- system.bridge_canary = green"])

    seen = {}

    def fake_broad_chat(prompt, context_blocks=None):
        seen["prompt"] = prompt
        seen["context_blocks"] = context_blocks
        return "CHAT_OK"

    monkeypatch.setattr(responder, "broad_chat", fake_broad_chat)

    assert responder.respond("tell me about the bridge", user_id=5) == "CHAT_OK"
    assert seen["prompt"] == "tell me about the bridge"
    assert seen["context_blocks"] == ["Authoritative facts:\n- system.bridge_canary = green"]
