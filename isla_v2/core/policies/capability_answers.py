from typing import Optional

from isla_v2.core.models.local_chat import DEFAULT_MODEL, describe_broad_model, list_local_models


MODEL_QUESTION_MARKERS = (
    "what model are you using",
    "what models are you using",
    "which model are you using",
    "which models are you using",
    "what llm are you using",
    "which llm are you using",
    "what model powers",
    "what broad model",
    "available models",
    "installed models",
)

CAPABILITY_QUESTION_MARKERS = (
    "what can you do",
    "how can you help",
    "capabilities",
)

REALTIME_MARKERS = (
    "right now",
    "current ",
    "latest ",
    "live ",
    "today",
)

EXTERNAL_REALTIME_MARKERS = (
    "price",
    "gold",
    "silver",
    "stock",
    "btc",
    "bitcoin",
    "eth",
    "ethereum",
    "weather",
    "forecast",
    "temperature",
    "news",
    "headline",
    "exchange rate",
    "traffic",
)


def _normalize(prompt: str) -> str:
    return " ".join(prompt.lower().split())


def _matches_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _format_local_models(limit: int = 6) -> str:
    try:
        names = list_local_models(limit=limit)
    except RuntimeError as exc:
        return f"I could not list installed Ollama models from this process: {exc}."

    if not names:
        return "I could not see any installed Ollama models from this process."

    return "Installed Ollama models I can currently see: " + ", ".join(f"`{name}`" for name in names) + "."


def _describe_configured_model() -> str:
    try:
        snapshot = describe_broad_model()
    except RuntimeError as exc:
        return (
            f"For broad chat, ISLA_V2 is configured to use `{DEFAULT_MODEL}`. "
            f"I could not verify that model locally right now: {exc}."
        )

    lines = [f"For broad chat, ISLA_V2 is currently configured to use `{snapshot['model']}`."]
    if snapshot["parent_model"]:
        lines.append(f"Parent/base model: `{snapshot['parent_model']}`.")
    if snapshot["family"]:
        lines.append(f"Model family: `{snapshot['family']}`.")
    if snapshot["parameter_size"]:
        lines.append(f"Approximate size: `{snapshot['parameter_size']}`.")
    if snapshot["quantization_level"]:
        lines.append(f"Quantization: `{snapshot['quantization_level']}`.")
    capabilities = snapshot["capabilities"]
    if capabilities:
        lines.append(
            "Ollama reports model capabilities: "
            + ", ".join(f"`{item}`" for item in capabilities)
            + "."
        )
    lines.append(_format_local_models())
    lines.append(
        "Trusted facts, notes, `/ops`, and allowlisted procedures still use their own deterministic or local-system paths instead of relying on the broad-chat model alone."
    )
    return "\n".join(lines)


def get_capability_answer(prompt: str) -> Optional[str]:
    pl = _normalize(prompt)

    if not _matches_any(pl, CAPABILITY_QUESTION_MARKERS):
        return None

    try:
        snapshot = describe_broad_model()
        broad_model_line = f"Broad chat currently runs through `{snapshot['model']}`."
    except RuntimeError as exc:
        broad_model_line = (
            f"Broad chat is configured for `{DEFAULT_MODEL}`, but I could not verify that local Ollama model right now: {exc}."
        )

    return "\n".join(
        [
            "In this ISLA_V2 setup, I am strongest at concrete local operator work rather than generic internet-style chatbot tasks.",
            "",
            "What I can do reliably here:",
            "- answer trusted exact facts and show fact history/search",
            "- capture and recall lower-trust operator notes separately from facts",
            "- run deterministic `/ops` status, logs, audit, pending-confirmation, restart, recovery, and rollback flows",
            "- require confirmation before destructive actions",
            "- run allowlisted procedures such as preflight, stack health, watchdog view, and health snapshot",
            "- help with Telegram-facing operation and structured troubleshooting of the local stack",
            f"- {broad_model_line}",
            "",
            "What broad chat is good for here:",
            "- troubleshooting guidance",
            "- architecture-aware explanations of this local AI stack",
            "- planning, writing, and operator support that benefits from local facts or notes when grounding is enabled",
            "",
            "What I should not pretend to do:",
            "- I do not have a built-in live web, market-data, or news feed in this broad-chat path",
            "- I should not invent current prices, current events, or active model details that I cannot verify locally",
        ]
    )


def get_broad_chat_answer(prompt: str) -> Optional[str]:
    pl = _normalize(prompt)

    if _matches_any(pl, MODEL_QUESTION_MARKERS):
        return _describe_configured_model()

    if _matches_any(pl, CAPABILITY_QUESTION_MARKERS):
        return get_capability_answer(prompt)

    if _matches_any(pl, REALTIME_MARKERS) and _matches_any(pl, EXTERNAL_REALTIME_MARKERS):
        return "\n".join(
            [
                "I cannot verify live external prices or other real-time public data from this ISLA_V2 broad-chat path.",
                "I do not have a built-in market feed or general web lookup here, so I should not guess the gold price right now.",
                "If you paste a current quote from a live source, I can help interpret it. If you want local system truth instead, I can check configured models, facts, notes, ops status, or procedures.",
            ]
        )

    return None
