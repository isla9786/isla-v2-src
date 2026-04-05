from typing import Optional

from isla_v2.core.memory.retrieval import grounding_enabled
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

BROAD_CHAT_QUALITY_MARKERS = (
    "broad chat still feels generic",
    "broad chat feels generic",
    "improve broad chat",
)

SAFE_GROWTH_MARKERS = (
    "broader and smarter",
    "ops safety",
    "safest next step",
)

ARCHITECTURE_MARKERS = (
    "local ai stack",
    "major part does",
    "major parts do",
    "non-technical operator",
    "explain isla_v2",
    "explain isla v2",
)

MODALITY_NOUN_MARKERS = (
    "image",
    "images",
    "audio",
    "screenshot",
    "screenshots",
    "photo",
    "photos",
    "picture",
    "pictures",
    "voice",
    "voice note",
    "voice notes",
    "voice memo",
    "voice memos",
    "voice recording",
    "voice recordings",
    "recording",
    "recordings",
    "media",
    "media attachment",
    "media attachments",
    "attachment",
    "attachments",
    "file",
    "files",
    "attached file",
    "attached files",
    "document",
    "documents",
    "upload",
    "uploads",
    "uploaded",
    "uploaded file",
    "uploaded files",
)

VISUAL_AUDIO_NOUN_MARKERS = (
    "image",
    "images",
    "audio",
    "screenshot",
    "screenshots",
    "photo",
    "photos",
    "picture",
    "pictures",
    "voice",
    "voice note",
    "voice notes",
    "voice memo",
    "voice memos",
    "voice recording",
    "voice recordings",
    "recording",
    "recordings",
    "media",
    "media attachment",
    "media attachments",
)

TEXT_FILE_NOUN_MARKERS = (
    "attachment",
    "attachments",
    "file",
    "files",
    "attached file",
    "attached files",
    "document",
    "documents",
    "pdf",
    "pdfs",
    "spreadsheet",
    "spreadsheets",
    "sheet",
    "sheets",
    "csv",
    "excel",
    "workbook",
    "workbooks",
)

CODE_LOG_NOUN_MARKERS = (
    "codebase",
    "repo",
    "repository",
    "source code",
    "log",
    "logs",
    "log file",
    "log files",
    "production logs",
)

REVIEW_TARGET_MARKERS = VISUAL_AUDIO_NOUN_MARKERS + TEXT_FILE_NOUN_MARKERS + CODE_LOG_NOUN_MARKERS

MODALITY_ACTION_MARKERS = (
    "can you",
    "do you",
    "could you",
    "are you able to",
    "read",
    "process",
    "analyze",
    "analyse",
    "handle",
    "understand",
    "look at",
    "listen to",
    "hear",
    "inspect",
    "review",
    "examine",
    "check",
    "work with",
)

REVIEW_ACTION_MARKERS = (
    "read",
    "process",
    "analyze",
    "analyse",
    "handle",
    "understand",
    "look at",
    "listen to",
    "hear",
    "inspect",
    "review",
    "examine",
    "check",
    "work with",
    "summarize",
    "summarise",
    "compare",
)

UPLOAD_INTENT_MARKERS = (
    "upload",
    "uploads",
    "uploaded",
    "send",
    "later",
    "if i send",
    "if i upload",
    "if i share",
)

WEB_LOOKUP_MARKERS = (
    "browse the web",
    "search the web",
    "look online",
    "google",
)

FALSE_CLAIM_MARKERS = (
    "pretend you already saw",
    "pretend you've already seen",
    "pretend you already reviewed",
    "act like you already saw",
    "act like you already reviewed",
    "say you already reviewed",
    "confirm you reviewed",
    "confirm you already reviewed",
    "already saw the attachment",
    "already reviewed my attachment",
    "even though i haven't uploaded",
    "even though i have not uploaded",
)

COERCION_MARKERS = (
    "ignore your limits",
    "ignore previous instructions",
    "pretend you are unrestricted",
    "pretend you're unrestricted",
    "for this answer only",
    "do not explain limits",
    "just confirm",
    "say yes",
)


def _normalize(prompt: str) -> str:
    return " ".join(prompt.lower().split())


def _matches_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _matches_all(text: str, markers: tuple[str, ...]) -> bool:
    return all(marker in text for marker in markers)


def _is_modality_capability_question(text: str) -> bool:
    return _matches_any(text, MODALITY_NOUN_MARKERS) and _matches_any(text, MODALITY_ACTION_MARKERS)


def _has_inline_material(prompt: str, text: str) -> bool:
    return "```" in prompt or "\n" in prompt or len(text.split()) >= 50


def _is_false_claim_prompt(text: str) -> bool:
    if _matches_any(text, FALSE_CLAIM_MARKERS):
        return True
    return (
        _matches_any(text, ("pretend", "say", "confirm", "act like"))
        and _matches_any(text, ("already", "reviewed", "summarize", "summarise"))
        and _matches_any(text, ("attachment", "file", "document"))
    )


def _is_review_request_without_material(prompt: str, text: str) -> bool:
    if _has_inline_material(prompt, text):
        return False
    if not _matches_any(text, REVIEW_TARGET_MARKERS):
        return False
    return (
        _matches_any(text, REVIEW_ACTION_MARKERS)
        or _matches_any(text, UPLOAD_INTENT_MARKERS)
        or _matches_any(text, CAPABILITY_QUESTION_MARKERS)
    )


def _wants_review_scope(text: str) -> bool:
    return (
        "what kinds of files" in text
        or "what kind of files" in text
        or ("what can you" in text and _matches_any(text, ("review", "inspect", "analyze", "analyse")))
        or "inspect documents or not" in text
        or "able to inspect documents" in text
    )


def _text_only_constraint_line() -> str:
    return (
        "This broad-chat path is text-only, so it cannot directly inspect, review, read, process, or handle "
        "attachments, uploaded files, documents, images, screenshots, photos, audio, voice notes, or media here."
    )


def _text_input_help_line() -> str:
    return "If you want help, paste or type the relevant text here, or summarize the content manually here."


def _storage_help_line() -> str:
    return "If you want the system to reuse it later, store it as a fact or note explicitly."


def _modality_lead(text: str) -> str:
    if _matches_any(text, VISUAL_AUDIO_NOUN_MARKERS):
        return "Not directly."
    return "Yes, if you paste or type the relevant text here."


def _modality_help_line(text: str) -> str:
    if _matches_any(text, VISUAL_AUDIO_NOUN_MARKERS):
        return (
            "If you want help, paste or type the relevant text here, summarize the content manually here, or "
            "share a description, OCR text, or transcript."
        )
    return _text_input_help_line()


def _scope_answer() -> str:
    return (
        "I can review text you paste from documents, PDFs, spreadsheets, code, logs, transcripts, or OCR output. "
        "I can't inspect raw attachments directly in this chat."
    )


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


def _grounding_status_line() -> str:
    if grounding_enabled():
        return (
            "Grounding is enabled for this process, but the current implementation only injects local "
            "fact/note matches when the prompt text actually matches stored rows."
        )
    return (
        "Grounding is currently off unless `ISLA_V2_ENABLE_CONTEXT_GROUNDING` is enabled for the process."
    )


def _grounding_status_clause() -> str:
    if grounding_enabled():
        return (
            "enabled for this process, but it only injects local fact/note matches when the prompt text "
            "actually matches stored rows"
        )
    return "currently off unless `ISLA_V2_ENABLE_CONTEXT_GROUNDING` is enabled for the process"


def _broad_chat_quality_answer() -> str:
    return "\n".join(
        [
            "If broad chat still feels generic, the safest first improvement is not another model swap.",
            "",
            "What to improve first in this ISLA_V2 codebase:",
            "- tighten the broad-chat prompt and policy guardrails so the fallback stays text-only, architecture-aware, and explicit about limits",
            f"- {_grounding_status_line()}",
            "- improve retrieval quality before changing the model again; today the grounding path searches local facts and notes with simple substring matching, not semantic retrieval",
            "- add or refine high-value facts and operator notes for recurring topics you want broad chat to answer more concretely",
            "- keep exact facts, `/ops`, confirmations, and allowlisted procedures on their deterministic paths rather than pushing them into broad chat",
            "",
            "What is not currently implemented and should not be assumed:",
            "- no live web or market feed in broad chat",
            "- no image or audio handling in this path",
            "- no automatic learning from Telegram conversations unless facts or notes are explicitly stored",
            "- no semantic retrieval or embeddings in the current grounding path",
            "",
            "If you want one concrete next step, improve the grounding match quality and keep the current production model in place while you test it.",
        ]
    )


def _architecture_answer() -> str:
    return "\n".join(
        [
            "Practical ISLA_V2 stack view:",
            "- Telegram bot: operator interface for asking questions and issuing approved commands",
            "- Router/responder: checks deterministic actions, facts, ops, and guided policy answers before broad chat runs",
            "- Broad chat fallback: `isla-default:latest` through Ollama for open-ended text answers",
            "- Fact store: trusted exact values in the local facts database",
            "- Note store: lower-trust operator memory kept separate from facts",
            f"- Grounding: optional local fact/note context injection; {_grounding_status_clause()}",
            "- Ops and procedures: deterministic allowlisted flows with confirmations for risky actions",
            "- systemd user services: keep the bot and related services running under the local user",
            "",
            "The important boundary is that broad chat is only the fallback text path. Trusted facts, `/ops`, and procedures do not depend on the broad-chat model to stay safe.",
        ]
    )


def _modality_answer(text: str) -> str:
    return "\n".join(
        [
            _modality_lead(text),
            _text_only_constraint_line(),
            f"{_modality_help_line(text)} {_storage_help_line()}",
        ]
    )


def _review_request_answer(text: str) -> str:
    if _wants_review_scope(text):
        return _scope_answer()

    lines: list[str] = []
    if _matches_any(text, CODE_LOG_NOUN_MARKERS):
        lines.append("I can review code snippets or log lines you paste here.")
        lines.append("I don't have direct access to your codebase, local files, or production logs from broad chat.")
        return "\n".join(lines)

    if _matches_any(text, VISUAL_AUDIO_NOUN_MARKERS):
        lines.append("I can help if you share a description, OCR text, or a transcript.")
        lines.append("I can't inspect the raw image, audio, or attachment directly here.")
        return "\n".join(lines)

    if "compare" in text:
        lines.append("I can help compare them once you share excerpts.")
        lines.append("I shouldn't imply those files are already available here.")
        return "\n".join(lines)

    if "summarize" in text or "summarise" in text:
        lines.append("I can summarize it once you paste the relevant text.")
        lines.append("I can't treat an attachment or document as already available here.")
    elif _matches_any(text, ("spreadsheet", "spreadsheets", "sheet", "sheets", "csv", "excel", "workbook", "workbooks")):
        lines.append("I can help review it if you paste the relevant cells or text.")
        lines.append("I can't inspect a spreadsheet that hasn't been provided here.")
    elif _matches_any(text, ("pdf", "pdfs")):
        lines.append("Yes, if you paste the relevant text.")
        lines.append("I can't inspect a raw PDF directly here.")
    else:
        lines.append("Yes, if you paste the relevant text.")
        lines.append("I can't inspect a raw attachment or document that hasn't been provided here.")

    if _matches_any(text, WEB_LOOKUP_MARKERS):
        lines.append("I also do not have general web browsing in this path.")
    return "\n".join(lines)


def _false_claim_answer() -> str:
    return "\n".join(
        [
            "I can't honestly say I reviewed an attachment, file, or document that wasn't provided in this chat.",
            "If you paste the relevant text, I can help with it.",
        ]
    )


def _mixed_pdf_and_bank_answer() -> str:
    return "\n".join(
        [
            "I can help review or summarize the relevant PDF text if you paste it here.",
            "I can't inspect an uploaded PDF directly in this text-only path, and I can't call your bank or make phone calls for you.",
        ]
    )


def _code_and_physical_install_answer() -> str:
    return "\n".join(
        [
            "I can review code or patch text you paste here.",
            "I can't physically install a patch on your server or make real-world changes on your behalf.",
        ]
    )


def _background_work_answer() -> str:
    return "\n".join(
        [
            "I can help while you're actively chatting with me here.",
            "I can't keep working in the background, monitor things continuously on my own, or message you later by myself.",
            "If you want delayed or recurring work, use an explicit local scheduler or service and have it call the approved local tools.",
        ]
    )


def _coercive_access_answer(text: str) -> Optional[str]:
    if not _matches_any(text, COERCION_MARKERS):
        return None

    if _matches_any(text, ("access my computer", "access my pc", "access my laptop", "your computer")):
        return (
            "No. I can't access your computer from this chat, and asking me to ignore limits doesn't change that."
        )
    return None


def _mixed_capability_boundary_answer(text: str) -> Optional[str]:
    if _matches_any(text, ("pdf", "document", "documents", "upload", "uploaded")) and _matches_any(
        text,
        ("call my bank", "call the bank", "phone call", "make phone calls"),
    ):
        return _mixed_pdf_and_bank_answer()

    if _matches_any(text, ("review code", "code", "patch")) and _matches_any(
        text,
        ("physically install", "install the patch on my server", "patch on my server", "on my server"),
    ):
        return _code_and_physical_install_answer()

    if _matches_any(text, ("work in the background", "background")) and _matches_any(
        text,
        ("message me later", "later", "continuously", "continuous", "asynchronously", "monitor"),
    ):
        return _background_work_answer()

    return None


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

    if _is_false_claim_prompt(pl):
        return _false_claim_answer()

    mixed_boundary_answer = _mixed_capability_boundary_answer(pl)
    if mixed_boundary_answer:
        return mixed_boundary_answer

    coercive_access_answer = _coercive_access_answer(pl)
    if coercive_access_answer:
        return coercive_access_answer

    if _wants_review_scope(pl):
        return _scope_answer()

    if _matches_any(pl, CAPABILITY_QUESTION_MARKERS):
        return get_capability_answer(prompt)

    if _is_review_request_without_material(prompt, pl) and "compare" in pl:
        return _review_request_answer(pl)

    if _is_modality_capability_question(pl) and not _has_inline_material(prompt, pl):
        return _modality_answer(pl)

    if _is_review_request_without_material(prompt, pl):
        return _review_request_answer(pl)

    if _matches_any(pl, BROAD_CHAT_QUALITY_MARKERS) or (
        "broad chat" in pl and "generic" in pl and "improve" in pl
    ):
        return _broad_chat_quality_answer()

    if (
        ("broader" in pl and "smarter" in pl and "ops safety" in pl)
        or ("safest next step" in pl and "ops safety" in pl)
        or _matches_all(pl, SAFE_GROWTH_MARKERS)
    ):
        return _broad_chat_quality_answer()

    if _matches_any(pl, ARCHITECTURE_MARKERS):
        return _architecture_answer()

    if _matches_any(pl, REALTIME_MARKERS) and _matches_any(pl, EXTERNAL_REALTIME_MARKERS):
        return "\n".join(
            [
                "I cannot verify live external prices or other real-time public data from this ISLA_V2 broad-chat path.",
                "I do not have a built-in market feed or general web lookup here, so I should not guess the gold price right now.",
                "If you paste a current quote from a live source, I can help interpret it. If you want local system truth instead, I can check configured models, facts, notes, ops status, or procedures.",
            ]
        )

    return None
