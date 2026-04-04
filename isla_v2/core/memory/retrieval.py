import os

from isla_v2.core.memory.fact_store import search_facts
from isla_v2.core.memory.note_store import search_notes

DEFAULT_MAX_CONTEXT_CHARS = 1200


def grounding_enabled() -> bool:
    return os.getenv("ISLA_V2_ENABLE_CONTEXT_GROUNDING", "0").strip().lower() in {"1", "true", "yes", "on"}


def _truncate_blocks(blocks: list[str], limit: int) -> list[str]:
    used = 0
    out: list[str] = []
    for block in blocks:
        if used >= limit:
            break
        remaining = limit - used
        clipped = block[:remaining]
        out.append(clipped)
        used += len(clipped)
    return out


def build_grounding_context(prompt: str, max_chars: int | None = None) -> list[str]:
    if not grounding_enabled():
        return []

    limit = max_chars or int(os.getenv("ISLA_V2_GROUNDING_MAX_CHARS", str(DEFAULT_MAX_CONTEXT_CHARS)))
    blocks: list[str] = []

    try:
        fact_rows = search_facts(prompt, limit=4)
        if fact_rows:
            rendered = [
                f"- {row['namespace']}.{row['key']} = {row['value']} [state={row['state']}]"
                for row in fact_rows
            ]
            blocks.append("Authoritative facts:\n" + "\n".join(rendered))
    except Exception:
        pass

    try:
        note_rows = search_notes(prompt, limit=4)
        if note_rows:
            rendered = [
                f"- {row['namespace']}: {row['body']} [kind={row['kind']}]"
                for row in note_rows
            ]
            blocks.append("Operator notes:\n" + "\n".join(rendered))
    except Exception:
        pass

    return _truncate_blocks(blocks, limit)
