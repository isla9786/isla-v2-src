import argparse

from isla_v2.core.memory.fact_store import get_fact
from isla_v2.core.memory.retrieval import build_grounding_context
from isla_v2.core.models.local_chat import chat as broad_chat
from isla_v2.core.policies.capability_answers import get_broad_chat_answer
from isla_v2.core.router.deterministic_router import route_prompt
from isla_v2.core.tools.ops_actions import maybe_run_action
from isla_v2.core.tools.ops_catalog import unknown_ops_text


def respond(prompt: str, user_id: int | None = None) -> str:
    action_result = maybe_run_action(prompt, user_id=user_id)
    if action_result is not None:
        return action_result

    decision = route_prompt(prompt)

    if decision.route == "exact":
        return decision.exact_text or ""

    if decision.route == "fact_lookup":
        if not decision.namespace or not decision.key:
            return "FACT_ROUTE_ERROR"
        value = get_fact(decision.namespace, decision.key)
        return value if value is not None else "FACT_NOT_FOUND"

    if decision.route == "ops":
        return unknown_ops_text(prompt)

    guided_broad_chat_answer = get_broad_chat_answer(prompt)
    if guided_broad_chat_answer:
        return guided_broad_chat_answer

    context_blocks = build_grounding_context(prompt)
    return broad_chat(prompt, context_blocks=context_blocks)


def main() -> None:
    parser = argparse.ArgumentParser(description="ISLA v2 responder")
    parser.add_argument("prompt")
    args = parser.parse_args()
    print(respond(args.prompt))


if __name__ == "__main__":
    main()
