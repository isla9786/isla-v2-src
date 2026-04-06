import argparse
import os
import time

import ollama

DEFAULT_MODEL = os.getenv("ISLA_V2_BROAD_MODEL", "isla-default:latest")
VALIDATED_MODELS: set[str] = set()
MODEL_SHOW_CACHE: dict[str, object] = {}
VALIDATION_PROMPT = "Reply with exactly: OK"

SYSTEM_PROMPT = """You are ISLA v2, a private local AI operating assistant built for this environment.

Real environment:
- Runs on WSL Ubuntu
- Uses Python-based local AI agents
- Uses Telegram bots for remote interaction
- Uses Ollama local LLMs for broad chat
- Uses an exact fact store for trusted recall
- Uses separate operator notes for lower-trust memory
- Uses systemd user services for persistence
- Includes health checks, logs, confirmed restart flows, rollback helpers, and allowlisted procedures
- The legacy crew sidecar is retired in the current v2 baseline

How to answer:
- Be concise, practical, and operator-minded.
- Speak as a local AI system assistant, not as a generic chatbot.
- Prefer concrete examples from this setup: Telegram control, local services, health checks, fact recall, notes, ops workflows, writing support, troubleshooting.
- Keep a clear boundary between:
  - what you know from this local setup,
  - what you can check locally,
  - and what you cannot verify here.
- If asked what model is in use, only mention the configured or locally verified model details that were actually provided in context.
- If asked what you can do, explain capabilities in terms of this actual setup.
- For current prices, news, web facts, or anything time-sensitive outside the local system, do not guess or imply live internet access.
- If you cannot verify something from this environment, say so plainly and give the best local next step.
- Do not invent tools or features that are not present.
- Do not mention hidden internals.
- For technical questions, give clear next steps.
- Optimize for usefulness, reliability, and controllability over hype.
"""


def _parse_detail_value(response: object, key: str) -> str:
    details = getattr(response, "details", None)
    if details is not None:
        value = getattr(details, key, None)
        if value:
            return str(value)

    if isinstance(response, dict):
        details_dict = response.get("details")
        if isinstance(details_dict, dict):
            value = details_dict.get(key)
            if value:
                return str(value)

    return ""


def _parse_capabilities(response: object) -> list[str]:
    capabilities = getattr(response, "capabilities", None)
    if capabilities is None and isinstance(response, dict):
        capabilities = response.get("capabilities", [])
    return [str(item) for item in capabilities or []]


def _model_name_from_entry(entry: object) -> str:
    if isinstance(entry, dict):
        return str(entry.get("model") or entry.get("name") or "").strip()
    return str(getattr(entry, "model", None) or getattr(entry, "name", None) or "").strip()


def load_model_metadata(model: str) -> tuple[str, object]:
    resolved_model = model.strip()
    if not resolved_model:
        raise RuntimeError("OLLAMA_MODEL_INVALID: configured broad model is empty")

    cached = MODEL_SHOW_CACHE.get(resolved_model)
    if cached is not None:
        VALIDATED_MODELS.add(resolved_model)
        return resolved_model, cached

    try:
        response = ollama.show(resolved_model)
    except ollama.ResponseError as exc:
        message = str(exc).lower()
        if exc.status_code == 404 or "not found" in message:
            raise RuntimeError(
                f"OLLAMA_MODEL_NOT_FOUND: {resolved_model}. Pull it with: ollama pull {resolved_model}"
            ) from exc
        raise RuntimeError(f"OLLAMA_MODEL_CHECK_FAILED: {resolved_model}: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"OLLAMA_MODEL_CHECK_FAILED: {resolved_model}: {exc}") from exc

    VALIDATED_MODELS.add(resolved_model)
    MODEL_SHOW_CACHE[resolved_model] = response
    return resolved_model, response


def ensure_model_available(model: str) -> str:
    resolved_model, _ = load_model_metadata(model)
    return resolved_model


def describe_broad_model(model: str = DEFAULT_MODEL) -> dict[str, str | list[str]]:
    resolved_model, response = load_model_metadata(model)
    return {
        "model": resolved_model,
        "parent_model": _parse_detail_value(response, "parent_model"),
        "family": _parse_detail_value(response, "family"),
        "parameter_size": _parse_detail_value(response, "parameter_size"),
        "quantization_level": _parse_detail_value(response, "quantization_level"),
        "capabilities": _parse_capabilities(response),
    }


def list_local_models(limit: int = 8) -> list[str]:
    try:
        response = ollama.list()
    except Exception as exc:
        raise RuntimeError(f"OLLAMA_MODEL_LIST_FAILED: {exc}") from exc

    models = getattr(response, "models", None)
    if models is None and isinstance(response, dict):
        models = response.get("models", [])

    seen: list[str] = []
    for entry in models or []:
        name = _model_name_from_entry(entry)
        if name and name not in seen:
            seen.append(name)
        if len(seen) >= limit:
            break
    return seen


def _extract_chat_content(response: object, model: str) -> str:
    message = getattr(response, "message", None)
    if message is None and isinstance(response, dict):
        message = response.get("message")

    content = ""
    if isinstance(message, dict):
        content = str(message.get("content") or "")
    elif message is not None:
        content = str(getattr(message, "content", "") or "")

    stripped = content.strip()
    if stripped:
        return stripped

    raise RuntimeError(f"OLLAMA_EMPTY_CONTENT: {model} returned no usable message content")


def chat(prompt: str, model: str = DEFAULT_MODEL, context_blocks: list[str] | None = None) -> str:
    model_snapshot = describe_broad_model(model)
    resolved_model = str(model_snapshot["model"])
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    runtime_lines = [f"Configured broad-chat model: {resolved_model}."]
    if model_snapshot["parent_model"]:
        runtime_lines.append(f"Parent/base model: {model_snapshot['parent_model']}.")
    if model_snapshot["family"]:
        runtime_lines.append(f"Model family: {model_snapshot['family']}.")
    if model_snapshot["parameter_size"]:
        runtime_lines.append(f"Approximate parameter size: {model_snapshot['parameter_size']}.")
    if model_snapshot["capabilities"]:
        runtime_lines.append(
            "Ollama-reported model capabilities: "
            + ", ".join(str(item) for item in model_snapshot["capabilities"])
            + "."
        )
    messages.append({"role": "system", "content": "\n".join(runtime_lines)})
    if context_blocks:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Local context is available below.\n"
                    "- Authoritative facts are high trust.\n"
                    "- Operator notes are lower trust.\n"
                    "- Use context when it is relevant, but do not invent unsupported details.\n\n"
                    + "\n\n".join(context_blocks)
                ),
            }
        )
    messages.append({"role": "user", "content": prompt})

    resp = ollama.chat(
        model=resolved_model,
        messages=messages,
        think=False,
        options={"temperature": 0.15},
    )
    return _extract_chat_content(resp, resolved_model)


def validate_broad_chat(
    model: str = DEFAULT_MODEL,
    prompt: str = VALIDATION_PROMPT,
) -> dict[str, str | int]:
    reported_model = model.strip() or "(empty)"
    started = time.perf_counter()
    try:
        response = chat(prompt, model=model)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "model": reported_model,
            "status": "OK",
            "elapsed_ms": elapsed_ms,
            "response": response,
        }
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "model": reported_model,
            "status": "FAIL",
            "elapsed_ms": elapsed_ms,
            "error": str(exc),
        }


def format_validation_report(result: dict[str, str | int]) -> str:
    lines = [
        "ISLA broad chat validation",
        f"model: {result['model']}",
        f"status: {result['status']}",
        f"elapsed_ms: {result['elapsed_ms']}",
    ]
    if result["status"] == "OK":
        lines.append(f"response: {result['response']}")
    else:
        lines.append(f"error: {result['error']}")
    return "\n".join(lines)

def main() -> None:
    parser = argparse.ArgumentParser(description="ISLA v2 local broad chat")
    parser.add_argument("prompt", nargs="?")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate configured model presence and basic broad-chat response",
    )
    args = parser.parse_args()
    if args.validate:
        result = validate_broad_chat(model=args.model, prompt=args.prompt or VALIDATION_PROMPT)
        print(format_validation_report(result))
        if result["status"] != "OK":
            raise SystemExit(1)
        return

    if not args.prompt:
        parser.error("prompt is required unless --validate is used")
    print(chat(args.prompt, model=args.model))

if __name__ == "__main__":
    main()
