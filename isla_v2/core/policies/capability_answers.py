from typing import Optional


def get_capability_answer(prompt: str) -> Optional[str]:
    pl = " ".join(prompt.lower().split())

    if (
        "what can you do" in pl
        or "how can you help" in pl
        or "capabilities" in pl
    ):
        return """In your current local AI setup, I can already help in practical ways:

1. Telegram-based remote operation
- Respond through your ISLA v2 bot from your phone
- Handle exact replies, trusted fact questions, note capture, ops checks, confirmed restart flows, procedure runs, and general support queries

2. Trusted fact recall
- Return stored facts from your v2 fact store
- Search facts, show fact history, and track soft-expiry state without collapsing exact facts into a generic memory blob
- Example: Aquari Hotel address, Aquari Hotel phone, bridge_canary

3. Notes and grounded support
- Store lower-trust operator notes separately from authoritative facts
- Use local fact and note matches to ground broader answers when grounding is enabled
- Degrade safely to normal local chat if retrieval is disabled or unavailable

4. Service monitoring and safe control
- Check v2 bot, gateway, Ollama, Open WebUI, and Qdrant health
- Show logs, pending confirmations, and recent ops audit entries
- Require confirmation before destructive restart or rollback actions

5. Local AI routing
- Route prompts deterministically into exact reply, fact lookup, ops, or broad chat
- This makes important answers more controllable than a fully free-form chatbot

6. Local model assistance
- Use your local Ollama model for broader questions that are not exact facts or ops checks
- Useful for troubleshooting guidance, planning, and setup support

7. Troubleshooting support
- Help diagnose bot, service, and routing problems
- Turn error output into step-by-step fixes

8. Writing and operational support
- Help draft prompts, system plans, upgrade ideas, and safe procedure flows for your local AI stack

Right now, v2 is strongest at:
- trusted facts
- fact and note recall
- operator checks
- Telegram interaction
- allowlisted procedures
- structured troubleshooting

The legacy crew sidecar is retired in the current v2 baseline, so sidecar checks return retirement status instead of a live sidecar workflow."""
    return None
