# ISLA_V2 Exceptional Ops Only: Gemma Runtime Edit

- Scope: exceptional-only temporary Gemma bot trial by direct edit in the live runtime tree
- Source root: `/home/ai/ai-agents-src`
- Runtime root: `/home/ai/ai-agents`

> WARNING:
> This is not a release workflow.
> `/home/ai/ai-agents` is a deploy target, not a development workspace.
> Live runtime edits are temporary and higher risk than the normal release path.
> Use this only for exceptional local Gemma trials.

## Standard Release Path

Standard production changes must use:

```bash
cd /home/ai/ai-agents-src
/home/ai/ai-agents/venv2026/bin/python scripts/release_gate.py
```

Do not use the runtime procedure below as a standard release path.

## Purpose

This runbook covers the narrow case where a short-lived local Gemma bot trial is required after the repo-local smoke test and an operator is intentionally accepting a temporary live runtime edit.

## Use Only When

- the repo-local Gemma smoke test already passed
- you need a short-lived local Gemma bot trial before returning to the normal gated path
- an operator explicitly accepts the higher-risk live runtime change
- you have a clear rollback owner and an immediate plan to return to the normal workflow

## Risks

- This bypasses the normal release gate and must not become the standard release path.
- Direct edits in `/home/ai/ai-agents` create source/runtime drift until they are removed or replaced by a normal gated release.
- Restarting the live bot changes operator-visible behavior immediately.
- Leaving the runtime edit in place increases the chance of confusion during later deploys and parity checks.

## Exceptional Procedure

Edit:

- `/home/ai/ai-agents/isla_v2/secrets/isla_v2_bot.env`

Add:

```bash
ISLA_V2_BROAD_MODEL=gemma4:e4b
```

Then restart only the bot:

```bash
systemctl --user restart isla-v2-bot.service
systemctl --user --no-pager status isla-v2-bot.service
/home/ai/bin/isla-v2-preflight
```

If the configured `ISLA_V2_BROAD_MODEL` tag is missing locally, both broad chat and preflight fail clearly with:

```text
OLLAMA_MODEL_NOT_FOUND: <model>. Pull it with: ollama pull <model>
```

Safe operator checks after restart:

- Telegram:
  - `/status alert`
  - `/ask summarize the current stack`
  - a plain-text non-ops prompt
- Local:

```bash
/home/ai/bin/isla-check
cd /home/ai/ai-agents-src && /home/ai/ai-agents/venv2026/bin/python -m isla_v2.apps.watchdog.watchdog --show
```

## Recovery Back To Normal Gate-Only Workflow

Remove or change:

```bash
ISLA_V2_BROAD_MODEL=gemma4:e4b
```

in:

- `/home/ai/ai-agents/isla_v2/secrets/isla_v2_bot.env`

Then restart the bot and confirm the runtime is healthy again:

```bash
systemctl --user restart isla-v2-bot.service
/home/ai/bin/isla-v2-preflight
```

If you want to clean up the test model itself:

```bash
ollama rm gemma4:e4b
```

After the trial ends, return to the normal gate-only workflow for any lasting change:

```bash
cd /home/ai/ai-agents-src
/home/ai/ai-agents/venv2026/bin/python scripts/release_gate.py
```
