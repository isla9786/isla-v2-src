from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OpsCommandSpec:
    name: str
    aliases: tuple[str, ...] = ()
    destructive: bool = False


OPS_COMMANDS: tuple[OpsCommandSpec, ...] = (
    OpsCommandSpec("alert"),
    OpsCommandSpec("audit trail", aliases=("audit log", "audit logs")),
    OpsCommandSpec("sidecar status", aliases=("crew sidecar status",)),
    OpsCommandSpec("sidecar logs", aliases=("crew sidecar logs",)),
    OpsCommandSpec("main health", aliases=("main status",)),
    OpsCommandSpec("v2 status", aliases=("isla v2 bot status",)),
    OpsCommandSpec("v2 logs", aliases=("isla v2 bot logs",)),
    OpsCommandSpec("gateway status", aliases=("openclaw gateway status",)),
    OpsCommandSpec("gateway logs", aliases=("openclaw gateway logs",)),
    OpsCommandSpec("watchdog status"),
    OpsCommandSpec("watchdog logs"),
    OpsCommandSpec("webui status", aliases=("open webui status", "open-webui status")),
    OpsCommandSpec("qdrant status"),
    OpsCommandSpec("golden status", aliases=("release status",)),
    OpsCommandSpec("procedures", aliases=("procedure list", "procedures list")),
    OpsCommandSpec("procedure history", aliases=("procedures history",)),
    OpsCommandSpec("procedure run <name>"),
    OpsCommandSpec(
        "restart sidecar",
        aliases=("restart crew sidecar service",),
        destructive=True,
    ),
    OpsCommandSpec(
        "confirm restart sidecar",
        aliases=("confirm restart crew sidecar service",),
        destructive=True,
    ),
    OpsCommandSpec(
        "restart v2",
        aliases=("restart isla v2 bot service",),
        destructive=True,
    ),
    OpsCommandSpec(
        "confirm restart v2",
        aliases=("confirm restart isla v2 bot service",),
        destructive=True,
    ),
    OpsCommandSpec("recover main", destructive=True),
    OpsCommandSpec("confirm recover main", destructive=True),
    OpsCommandSpec("recover all", destructive=True),
    OpsCommandSpec("confirm recover all", destructive=True),
    OpsCommandSpec("restart gateway", destructive=True),
    OpsCommandSpec("confirm restart gateway", destructive=True),
    OpsCommandSpec("ollama status"),
    OpsCommandSpec("ollama logs"),
    OpsCommandSpec("restart ollama"),
    OpsCommandSpec("force restart ollama", destructive=True),
    OpsCommandSpec(
        "confirm force restart ollama",
        aliases=("confirm restart ollama",),
        destructive=True,
    ),
    OpsCommandSpec("rollback golden", destructive=True),
    OpsCommandSpec("confirm rollback golden", destructive=True),
    OpsCommandSpec("rollback report"),
    OpsCommandSpec("pending confirms"),
)

_ALIASES: dict[str, str] = {}
for spec in OPS_COMMANDS:
    _ALIASES[spec.name] = spec.name
    for alias in spec.aliases:
        _ALIASES[alias] = spec.name

OPS_CANONICAL_NAMES = tuple(spec.name for spec in OPS_COMMANDS)


def normalize_ops_text(text: str) -> str:
    return " ".join((text or "").lower().split())


def help_lines() -> list[str]:
    return [f"/ops {spec.name}" for spec in OPS_COMMANDS]


def ops_help_text() -> str:
    return "Ops help\n\n" + "\n".join(help_lines())


def known_ops_names() -> tuple[str, ...]:
    return OPS_CANONICAL_NAMES


def known_ops_phrases() -> list[str]:
    phrases = list(_ALIASES.keys())
    phrases.extend(spec.name for spec in OPS_COMMANDS)
    return sorted(set(phrases))


def canonicalize_ops_text(text: str) -> str:
    normalized = normalize_ops_text(text)
    direct = _ALIASES.get(normalized)
    if direct:
        return direct

    if ("sidecar" in normalized or "crew sidecar" in normalized) and "status" in normalized:
        return "sidecar status"
    if ("sidecar" in normalized or "crew sidecar" in normalized) and "logs" in normalized:
        return "sidecar logs"
    if "main" in normalized and ("health" in normalized or "status" in normalized):
        return "main health"
    if ("v2" in normalized or "isla v2 bot" in normalized) and "status" in normalized:
        return "v2 status"
    if ("v2" in normalized or "isla v2 bot" in normalized) and "logs" in normalized:
        return "v2 logs"
    if ("gateway" in normalized or "openclaw gateway" in normalized) and "status" in normalized:
        return "gateway status"
    if ("gateway" in normalized or "openclaw gateway" in normalized) and "logs" in normalized:
        return "gateway logs"
    if "watchdog" in normalized and "status" in normalized:
        return "watchdog status"
    if "watchdog" in normalized and "logs" in normalized:
        return "watchdog logs"
    if ("webui" in normalized or "open webui" in normalized or "open-webui" in normalized) and "status" in normalized:
        return "webui status"
    if "qdrant" in normalized and "status" in normalized:
        return "qdrant status"
    if ("golden" in normalized or "release" in normalized) and "status" in normalized:
        return "golden status"
    if normalized in {"procedures", "procedure list", "procedures list"}:
        return "procedures"
    if normalized in {"procedure history", "procedures history"}:
        return "procedure history"
    if normalized.startswith("procedure run "):
        return "procedure run <name>"
    if "ollama" in normalized and "status" in normalized:
        return "ollama status"
    if "ollama" in normalized and "logs" in normalized:
        return "ollama logs"
    if normalized in {"pending confirmation", "pending confirmations"}:
        return "pending confirms"
    if normalized in {"audit log", "audit logs"}:
        return "audit trail"

    return normalized


def is_known_ops_command(text: str) -> bool:
    return canonicalize_ops_text(text) in OPS_CANONICAL_NAMES


def unknown_ops_text(prompt: str | None = None) -> str:
    normalized = normalize_ops_text(prompt or "")
    if normalized:
        return (
            f"UNKNOWN_OPS_COMMAND: {normalized}\n\n"
            "Supported ops commands:\n"
            + "\n".join(help_lines())
        )
    return ops_help_text()
