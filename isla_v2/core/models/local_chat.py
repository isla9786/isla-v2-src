import argparse
import os
import time

import ollama

DEFAULT_MODEL = os.getenv("ISLA_V2_BROAD_MODEL", "isla-default:latest")
VALIDATED_MODELS: set[str] = set()
VALIDATION_PROMPT = "Reply with exactly: OK"

SYSTEM_PROMPT = """You are ISLA v2, a private local AI operating assistant built for this environment.

Real environment:
- Runs on WSL Ubuntu
- Uses Python-based local AI agents
- Uses Telegram bots for remote interaction
- Uses Ollama local LLMs
- Uses an exact fact store for trusted recall
- Uses separate operator notes for lower-trust memory
- Uses systemd user services for persistence
- Includes health checks, logs, confirmed restart flows, rollback helpers, and allowlisted procedures
- The legacy crew sidecar is retired in the current v2 baseline

How to answer:
- Be concise, practical, and operator-minded.
- Speak as a local AI system assistant, not as a generic chatbot.
- Prefer concrete examples from this setup: Telegram control, local services, health checks, fact recall, notes, ops workflows, writing support, troubleshooting.
- If asked what you can do, explain capabilities in terms of this actual setup.
- Do not invent tools or features that are not present.
- Do not mention hidden internals.
- For technical questions, give clear next steps.
- Optimize for usefulness, reliability, and controllability over hype.
"""


def ensure_model_available(model: str) -> str:
    resolved_model = model.strip()
    if not resolved_model:
        raise RuntimeError("OLLAMA_MODEL_INVALID: configured broad model is empty")

    if resolved_model in VALIDATED_MODELS:
        return resolved_model

    try:
        ollama.show(resolved_model)
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
    return resolved_model


def chat(prompt: str, model: str = DEFAULT_MODEL, context_blocks: list[str] | None = None) -> str:
    resolved_model = ensure_model_available(model)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
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
        options={"temperature": 0.15},
    )
    return resp["message"]["content"].strip()


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
