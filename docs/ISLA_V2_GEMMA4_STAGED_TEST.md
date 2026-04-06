# ISLA_V2 Gemma 4 Staged Test Path

- Scope: low-risk local Gemma 4 trial path for the current ISLA_V2 repo and Ollama runtime
- Source repo: `/home/ai/ai-agents-src`
- Runtime repo: `/home/ai/ai-agents`
- Last validated date: `2026-04-04`
- Source of truth: live repo behavior wins; this path is optional and does not change the production default model

This is not a standard release workflow.

- Normal releases still go through `cd /home/ai/ai-agents-src && /home/ai/ai-agents/venv2026/bin/python scripts/release_gate.py`.
- Do not treat manual runtime edits under `/home/ai/ai-agents` as a normal deployment method.

## Decision

Gemma 4 is safe to add only as an optional staged test path right now.

Why:

- The repo already supports broad-chat model selection by env var in [local_chat.py](/home/ai/ai-agents/isla_v2/core/models/local_chat.py):
  - `ISLA_V2_BROAD_MODEL`
- The repo already supports per-invocation testing without changing defaults:
  - `python -m isla_v2.core.models.local_chat --model <name> "<prompt>"`
- The live production default remains:
  - `isla-default:latest`
- The wider OpenClaw gateway model policy lives outside the repo in:
  - `/home/ai/bin/isla-model-policy.env`
- The repo now validates the configured broad-chat model tag before broad-chat execution and during preflight.

Because of that, the safest path is:

- keep the current default model unchanged
- do not change gateway model policy
- test Gemma 4 only through the existing optional broad-chat seam first

## Verified Current Repo State

Repo-backed model selection:

- Broad chat default in [local_chat.py](/home/ai/ai-agents/isla_v2/core/models/local_chat.py):
  - `DEFAULT_MODEL = os.getenv("ISLA_V2_BROAD_MODEL", "isla-default:latest")`
- Direct CLI override in [local_chat.py](/home/ai/ai-agents/isla_v2/core/models/local_chat.py):
  - `python -m isla_v2.core.models.local_chat --model MODEL "<prompt>"`

Adjacent local workflow state:

- Current local Ollama version on this host:
  - `0.17.7`
- Currently installed local models included:
  - `isla-default:latest`
  - `isla-reason:latest`
  - `isla-code:latest`
  - `isla-fallback:latest`
  - `gemma4:e4b`
  - `qwen2.5:14b`
  - `llama3:latest`
- Bare `ollama show gemma4` is not the right probe for this host's installed tag.
- `ollama show gemma4:e4b` succeeds on this host.

Official upstream model availability:

- Ollama library page: [gemma4](https://ollama.com/library/gemma4)
- Official Ollama examples show:
  - `ollama run gemma4`
  - `ollama run gemma4:e2b`
  - `ollama run gemma4:e4b`
  - `ollama run gemma4:26b`
  - `ollama run gemma4:31b`

## Recommended First Test Model

Recommended first staged candidate:

- `gemma4:e4b`

Reason:

- it is listed by Ollama as a smaller edge/workstation-friendly variant than `26b` and `31b`
- it keeps the first trial closer to the repo’s current `isla-default:latest` footprint than the larger workstation models

Not recommended as the first local trial on this host:

- `gemma4:26b`
- `gemma4:31b`

Those may still be usable, but they are not the lowest-risk first step for ISLA_V2 broad-chat testing.

## Stage 0: Baseline Checks

Run these before changing anything:

```bash
ollama list
/home/ai/bin/isla-check
cd /home/ai/ai-agents-src && /home/ai/ai-agents/venv2026/bin/python -m pytest -q
```

Expected result:

- existing stack remains healthy
- current default workflow remains on `isla-default:latest`

## Stage 1: Install Gemma 4 Without Changing ISLA_V2 Defaults

Pull the test model into Ollama:

```bash
ollama pull gemma4:e4b
```

Verify it is now present:

```bash
ollama show gemma4:e4b
ollama list | grep gemma4
```

If you want a lighter exploratory trial first, you can use:

```bash
ollama pull gemma4:e2b
```

## Stage 2: Repo-Local Smoke Test Without Touching the Bot

Use the repo-owned broad-chat validation path first:

```bash
cd /home/ai/ai-agents-src
/home/ai/ai-agents/venv2026/bin/python -m isla_v2.core.models.local_chat --validate --model gemma4:e4b
```

To validate the currently configured broad model instead, omit `--model`:

```bash
cd /home/ai/ai-agents-src
/home/ai/ai-agents/venv2026/bin/python -m isla_v2.core.models.local_chat --validate
```

Expected success shape:

```text
ISLA broad chat validation
model: gemma4:e4b
status: OK
elapsed_ms: <number>
response: OK
```

If the model tag is missing locally, expected failure shape is:

```text
ISLA broad chat validation
model: gemma4:e4b
status: FAIL
elapsed_ms: <number>
error: OLLAMA_MODEL_NOT_FOUND: gemma4:e4b. Pull it with: ollama pull gemma4:e4b
```

You can also validate with a custom prompt:

```bash
cd /home/ai/ai-agents-src
/home/ai/ai-agents/venv2026/bin/python -m isla_v2.core.models.local_chat --validate --model gemma4:e4b "Summarize the current ISLA_V2 stack in five short bullets."
```

This is the safest first proof because it:

- uses the repo’s existing Ollama wrapper
- records model, success/failure, and basic timing
- does not change the bot service
- does not change the gateway
- does not change operator-facing defaults

## Stage 3: Exceptional-Only Live Runtime Trial

Any direct Gemma edit under `/home/ai/ai-agents` is exceptional-only and not part of the normal staged-test flow.

If you absolutely need that live runtime procedure after the CLI smoke test, use [ISLA_V2 Exceptional Ops Only: Gemma Runtime Edit](/home/ai/ai-agents/docs/ISLA_V2_EXCEPTIONAL_OPS_GEMMA_RUNTIME_EDIT.md).

Standard production changes still use:

```bash
cd /home/ai/ai-agents-src
/home/ai/ai-agents/venv2026/bin/python scripts/release_gate.py
```

## What Not To Change Yet

Do not change these as part of the first Gemma 4 trial:

- default repo fallback from `isla-default:latest`
- gateway model policy in `/home/ai/bin/isla-model-policy.env`
- destructive ops behavior
- procedures
- watchdog logic
- memory/retrieval behavior

Reason:

- the repo only owns the bot broad-chat seam directly
- the gateway has its own external model policy
- repo validation only covers the broad-chat seam, not the gateway's external model policy

## Rollback

If you used the exceptional live runtime trial, follow the recovery steps in [ISLA_V2 Exceptional Ops Only: Gemma Runtime Edit](/home/ai/ai-agents/docs/ISLA_V2_EXCEPTIONAL_OPS_GEMMA_RUNTIME_EDIT.md).

If you want to clean up the test model itself:

```bash
ollama rm gemma4:e4b
```

## Current Limitations

- This repo path is text-chat oriented; Gemma 4 image/audio features are not wired into ISLA_V2.
- The repo validates the configured broad-chat model tag, but not the gateway's external model policy.
- The wider OpenClaw gateway stack is not being changed here.
- `gemma4:e4b` is available locally and basic broad-chat invocation works on this host, but sustained quality/latency testing was not done in this pass.

## Practical Recommendation

Use Gemma 4 only as:

- an optional local smoke-test model first
- then only if absolutely necessary, an exceptional-only bot trial using [ISLA_V2 Exceptional Ops Only: Gemma Runtime Edit](/home/ai/ai-agents/docs/ISLA_V2_EXCEPTIONAL_OPS_GEMMA_RUNTIME_EDIT.md)

Do not make it the production default until you have manually validated:

- response quality
- latency
- bot stability
- operator satisfaction on real prompts
