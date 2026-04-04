import argparse
import re

from isla_v2.core.router.types import RouteDecision
from isla_v2.core.tools.ops_catalog import known_ops_phrases

EXACT_PATTERNS = [
    re.compile(r"^\s*reply with exactly:\s*(.+?)\s*$", re.I | re.S),
    re.compile(r"^\s*say exactly:\s*(.+?)\s*$", re.I | re.S),
]

OPS_KEYWORDS = sorted(
    set(
        known_ops_phrases()
        + [
            "restart service",
            "restart the service",
            "restart bot",
            "sidecar service",
            "crew sidecar",
            "status",
            "health check",
            "healthcheck",
            "logs",
            "journalctl",
            "port 5000",
            "what is using port",
            "service down",
            "qdrant",
            "ollama",
            "openclaw",
            "systemctl",
            "procedure run",
            "procedures",
            "recover",
            "recovery",
            "run full recovery",
        ]
    )
)

OPS_PATTERNS = [
    re.compile(r"\brestart\b.*\b(service|bot|sidecar|gateway|v2)\b", re.I),
    re.compile(r"\b(check|show|get)\b.*\b(status|logs|health)\b", re.I),
    re.compile(r"\brollback\b.*\bgolden\b", re.I),
    re.compile(r"\bpending\b.*\bconfirm", re.I),
    re.compile(r"\baudit\b.*\b(trail|log)s?\b", re.I),
]

BROAD_CHAT_KEYWORDS = [
    "what can you do",
    "capabilities",
    "tell me about yourself",
    "how can you help",
    "how can i upgrade my local ai setup",
]

FACT_RULES = [
    {
        "patterns": [
            r"\bwhere is aquari hotel\b",
            r"\baquari hotel location\b",
            r"\baquari hotel address\b",
            r"\baddress of aquari hotel\b",
        ],
        "namespace": "aquari_hotel",
        "key": "address",
        "reason": "matched Aquari Hotel address rule",
    },
    {
        "patterns": [
            r"\baquari hotel phone\b",
            r"\baquari hotel phone number\b",
            r"\bphone number of aquari hotel\b",
            r"\bcontact number of aquari hotel\b",
        ],
        "namespace": "aquari_hotel",
        "key": "phone",
        "reason": "matched Aquari Hotel phone rule",
    },
    {
        "patterns": [
            r"\bvalue of bridge_canary\b",
            r"\bbridge_canary\b",
        ],
        "namespace": "system",
        "key": "bridge_canary",
        "reason": "matched bridge_canary rule",
    },
]


def normalize(prompt: str) -> str:
    return " ".join(prompt.strip().split())


def route_prompt(prompt: str) -> RouteDecision:
    p = normalize(prompt)
    pl = p.lower()

    for rx in EXACT_PATTERNS:
        m = rx.match(p)
        if m:
            return RouteDecision(
                route="exact",
                reason="matched exact-response pattern",
                exact_text=m.group(1).strip(),
            )

    for rule in FACT_RULES:
        for pat in rule["patterns"]:
            if re.search(pat, pl, re.I):
                return RouteDecision(
                    route="fact_lookup",
                    reason=rule["reason"],
                    namespace=rule["namespace"],
                    key=rule["key"],
                )

    for kw in OPS_KEYWORDS:
        if kw in pl:
            return RouteDecision(
                route="ops",
                reason=f"matched ops keyword: {kw}",
            )

    for rx in OPS_PATTERNS:
        if rx.search(p):
            return RouteDecision(
                route="ops",
                reason=f"matched ops pattern: {rx.pattern}",
            )

    for kw in BROAD_CHAT_KEYWORDS:
        if kw in pl:
            return RouteDecision(
                route="broad_chat",
                reason=f"matched broad-chat keyword: {kw}",
            )

    return RouteDecision(
        route="broad_chat",
        reason="default fallback",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ISLA v2 deterministic router")
    parser.add_argument("prompt")
    args = parser.parse_args()

    result = route_prompt(args.prompt)
    print(f"route={result.route}")
    print(f"reason={result.reason}")
    if result.namespace:
        print(f"namespace={result.namespace}")
    if result.key:
        print(f"key={result.key}")
    if result.exact_text is not None:
        print(f"exact_text={result.exact_text}")


if __name__ == "__main__":
    main()
