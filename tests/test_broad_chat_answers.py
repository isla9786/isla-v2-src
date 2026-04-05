from isla_v2.core.policies import capability_answers
from isla_v2.core.router import responder
from isla_v2.core.router.types import RouteDecision


def test_model_question_returns_grounded_runtime_info(monkeypatch):
    monkeypatch.setattr(
        capability_answers,
        "describe_broad_model",
        lambda: {
            "model": "isla-default:latest",
            "parent_model": "qwen2.5:latest",
            "family": "qwen2",
            "parameter_size": "7.6B",
            "quantization_level": "Q4_K_M",
            "capabilities": ["completion", "tools"],
        },
    )
    monkeypatch.setattr(
        capability_answers,
        "list_local_models",
        lambda limit=6: ["isla-default:latest", "gemma4:e4b", "isla-code:latest"],
    )

    answer = capability_answers.get_broad_chat_answer("What models are you using right now?")

    assert answer is not None
    assert "`isla-default:latest`" in answer
    assert "`qwen2.5:latest`" in answer
    assert "`gemma4:e4b`" in answer
    assert "deterministic or local-system paths" in answer


def test_capability_question_returns_real_isla_capabilities(monkeypatch):
    monkeypatch.setattr(
        capability_answers,
        "describe_broad_model",
        lambda: {
            "model": "gemma4:e4b",
            "parent_model": "",
            "family": "gemma4",
            "parameter_size": "8.0B",
            "quantization_level": "Q4_K_M",
            "capabilities": ["completion"],
        },
    )

    answer = capability_answers.get_broad_chat_answer("What can you do?")

    assert answer is not None
    assert "trusted exact facts" in answer
    assert "deterministic `/ops`" in answer
    assert "allowlisted procedures" in answer
    assert "`gemma4:e4b`" in answer
    assert "should not invent current prices" in answer


def test_realtime_price_question_stays_truthful():
    answer = capability_answers.get_broad_chat_answer("What is the gold price right now?")

    assert answer is not None
    assert "cannot verify live external prices" in answer
    assert "should not guess the gold price right now" in answer


def test_exact_fact_route_still_wins_over_broad_chat(monkeypatch):
    monkeypatch.setattr(responder, "maybe_run_action", lambda prompt, user_id=None: None)
    monkeypatch.setattr(
        responder,
        "route_prompt",
        lambda prompt: RouteDecision(
            route="fact_lookup",
            reason="test",
            namespace="system",
            key="bridge_canary",
        ),
    )
    monkeypatch.setattr(responder, "get_fact", lambda namespace, key: "green")
    monkeypatch.setattr(responder, "get_broad_chat_answer", lambda prompt: "UNEXPECTED_BROAD_ANSWER")

    assert responder.respond("bridge_canary", user_id=5) == "green"


def test_action_confirmation_still_wins_over_broad_chat(monkeypatch):
    monkeypatch.setattr(
        responder,
        "maybe_run_action",
        lambda prompt, user_id=None: 'Confirmation required. Send exactly: "confirm restart gateway"',
    )
    monkeypatch.setattr(responder, "get_broad_chat_answer", lambda prompt: "UNEXPECTED_BROAD_ANSWER")

    assert responder.respond("restart gateway", user_id=9) == 'Confirmation required. Send exactly: "confirm restart gateway"'


def test_guided_broad_chat_answer_skips_ollama_call(monkeypatch):
    monkeypatch.setattr(responder, "maybe_run_action", lambda prompt, user_id=None: None)
    monkeypatch.setattr(
        responder,
        "route_prompt",
        lambda prompt: RouteDecision(route="broad_chat", reason="test"),
    )
    monkeypatch.setattr(
        responder,
        "get_broad_chat_answer",
        lambda prompt: "For broad chat, ISLA_V2 is currently configured to use `isla-default:latest`.",
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("broad_chat should not be called when a guided answer is available")

    monkeypatch.setattr(responder, "broad_chat", fail_if_called)

    result = responder.respond("what model are you using", user_id=5)
    assert "`isla-default:latest`" in result
