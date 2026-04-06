import importlib
import sys
import pytest


MODULE_NAME = "isla_v2.core.models.local_chat"


def load_local_chat(monkeypatch, broad_model: str | None = None):
    if broad_model is None:
        monkeypatch.delenv("ISLA_V2_BROAD_MODEL", raising=False)
    else:
        monkeypatch.setenv("ISLA_V2_BROAD_MODEL", broad_model)
    sys.modules.pop(MODULE_NAME, None)
    return importlib.import_module(MODULE_NAME)


def test_default_broad_model_stays_on_existing_default(monkeypatch):
    local_chat = load_local_chat(monkeypatch)
    assert local_chat.DEFAULT_MODEL == "isla-default:latest"


def test_default_broad_model_can_be_overridden_by_env(monkeypatch):
    local_chat = load_local_chat(monkeypatch, "gemma4:e4b")
    assert local_chat.DEFAULT_MODEL == "gemma4:e4b"


def test_chat_uses_requested_model_without_changing_default(monkeypatch):
    local_chat = load_local_chat(monkeypatch)
    events = []

    def fake_chat(**kwargs):
        events.append(("chat", kwargs))
        return {"message": {"content": "MODEL_OK"}}

    def fake_show(model):
        events.append(("show", model))
        return {"model_info": {"name": model}}

    monkeypatch.setattr(local_chat.ollama, "show", fake_show)
    monkeypatch.setattr(local_chat.ollama, "chat", fake_chat)

    result = local_chat.chat("hello", model="gemma4:e4b")

    assert result == "MODEL_OK"
    assert events[0] == ("show", "gemma4:e4b")
    assert events[1][0] == "chat"
    assert events[1][1]["model"] == "gemma4:e4b"
    assert events[1][1]["think"] is False
    assert events[1][1]["messages"][0]["role"] == "system"
    assert events[1][1]["messages"][-1]["content"] == "hello"


def test_chat_raises_clear_error_when_model_is_missing(monkeypatch):
    local_chat = load_local_chat(monkeypatch)
    chat_called = False

    def fake_show(model):
        raise local_chat.ollama.ResponseError(f"model '{model}' not found", status_code=404)

    def fake_chat(**kwargs):
        nonlocal chat_called
        chat_called = True
        return {"message": {"content": "UNEXPECTED"}}

    monkeypatch.setattr(local_chat.ollama, "show", fake_show)
    monkeypatch.setattr(local_chat.ollama, "chat", fake_chat)

    with pytest.raises(RuntimeError, match=r"OLLAMA_MODEL_NOT_FOUND: gemma4:e4b"):
        local_chat.chat("hello", model="gemma4:e4b")

    assert not chat_called


def test_chat_raises_clear_error_when_model_returns_empty_content(monkeypatch):
    local_chat = load_local_chat(monkeypatch)

    def fake_show(model):
        return {"model_info": {"name": model}}

    def fake_chat(**kwargs):
        return {"message": {"content": "   \n\t  "}}

    monkeypatch.setattr(local_chat.ollama, "show", fake_show)
    monkeypatch.setattr(local_chat.ollama, "chat", fake_chat)

    with pytest.raises(RuntimeError, match=r"OLLAMA_EMPTY_CONTENT: gemma4:e4b"):
        local_chat.chat("hello", model="gemma4:e4b")


def test_model_validation_is_cached_for_repeated_calls(monkeypatch):
    local_chat = load_local_chat(monkeypatch, "gemma4:e4b")
    show_calls = []

    def fake_show(model):
        show_calls.append(model)
        return {"model_info": {"name": model}}

    def fake_chat(**kwargs):
        return {"message": {"content": "MODEL_OK"}}

    monkeypatch.setattr(local_chat.ollama, "show", fake_show)
    monkeypatch.setattr(local_chat.ollama, "chat", fake_chat)

    assert local_chat.chat("hello") == "MODEL_OK"
    assert local_chat.chat("again") == "MODEL_OK"
    assert show_calls == ["gemma4:e4b"]


def test_validate_broad_chat_records_success_with_timing(monkeypatch):
    local_chat = load_local_chat(monkeypatch, "gemma4:e4b")
    times = iter([10.0, 10.25])

    def fake_show(model):
        return {"model_info": {"name": model}}

    def fake_chat(**kwargs):
        return {"message": {"content": "OK"}}

    monkeypatch.setattr(local_chat.ollama, "show", fake_show)
    monkeypatch.setattr(local_chat.ollama, "chat", fake_chat)
    monkeypatch.setattr(local_chat.time, "perf_counter", lambda: next(times))

    result = local_chat.validate_broad_chat()

    assert result == {
        "model": "gemma4:e4b",
        "status": "OK",
        "elapsed_ms": 250,
        "response": "OK",
    }
    assert "status: OK" in local_chat.format_validation_report(result)
    assert "elapsed_ms: 250" in local_chat.format_validation_report(result)


def test_validate_broad_chat_records_failure_with_timing(monkeypatch):
    local_chat = load_local_chat(monkeypatch, "missing-gemma4-check:latest")
    times = iter([20.0, 20.05])
    chat_called = False

    def fake_show(model):
        raise local_chat.ollama.ResponseError(f"model '{model}' not found", status_code=404)

    def fake_chat(**kwargs):
        nonlocal chat_called
        chat_called = True
        return {"message": {"content": "UNEXPECTED"}}

    monkeypatch.setattr(local_chat.ollama, "show", fake_show)
    monkeypatch.setattr(local_chat.ollama, "chat", fake_chat)
    monkeypatch.setattr(local_chat.time, "perf_counter", lambda: next(times))

    result = local_chat.validate_broad_chat()

    assert result["model"] == "missing-gemma4-check:latest"
    assert result["status"] == "FAIL"
    assert result["elapsed_ms"] == 50
    assert "OLLAMA_MODEL_NOT_FOUND: missing-gemma4-check:latest" in str(result["error"])
    assert "error: OLLAMA_MODEL_NOT_FOUND: missing-gemma4-check:latest" in local_chat.format_validation_report(result)
    assert not chat_called
