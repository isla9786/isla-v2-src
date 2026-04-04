# ISLA_V2 Operator Cheatsheet

- Scope: Daily operator quick reference for the current live ISLA_V2 stack
- Repo path: `/home/ai/ai-agents`
- Source of truth: [ISLA_V2 Operator Manual](/home/ai/ai-agents/docs/ISLA_V2_OPERATOR_MANUAL.md)
- Rule: implementation and scripts win over stale help text

## Quickest Health Verification Flow

Telegram:

- `/status alert`
- `/ops main health`
- `/ops v2 status`
- `/ops gateway status`
- `/ops watchdog status`

Local:

- `/home/ai/bin/isla-v2-preflight`
- `/home/ai/bin/isla-check`
- `/home/ai/bin/isla-v2-status`

Healthy signals:

- `No active issues detected.`
- `PREFLIGHT_OK`
- bot service is `active (running)`
- gateway, Ollama, Open WebUI, and Qdrant show `[OK]`

## Core Telegram Commands

Health and status:

- `/help`
- `/help ops`
- `/status alert`
- `/ops main health`
- `/ops v2 status`
- `/ops gateway status`
- `/ops watchdog status`
- `/ops ollama status`
- `/ops webui status`
- `/ops qdrant status`

Logs:

- `/ops v2 logs`
- `/ops gateway logs`
- `/ops watchdog logs`
- `/ops ollama logs`
- `/ops audit trail`

Restart and recovery:

- `/ops restart gateway`
- `/ops confirm restart gateway`
- `/ops restart v2`
- `/ops confirm restart v2`
- `/ops recover main`
- `/ops confirm recover main`
- `/ops recover all`
- `/ops confirm recover all`
- `/ops force restart ollama`
- `/ops confirm force restart ollama`

Rollback and release state:

- `/ops golden status`
- `/ops rollback golden`
- `/ops confirm rollback golden`
- `/ops rollback report`
- `/ops pending confirms`

Procedures:

- `/ops procedures`
- `/ops procedure history`
- `/ops procedure run preflight`
- `/ops procedure run health snapshot`

Facts and notes:

- `/factget system bridge_canary`
- `/factlist system`
- `/factsearch bridge`
- `/facthistory system bridge_canary`
- `/noteadd project gateway timeout observed`
- `/noterecent project`
- `/notesearch timeout`

## Core Plain-Text Commands

Shared ops surface:

- `gateway status`
- `gateway logs`
- `watchdog status`
- `watchdog logs`
- `ollama status`
- `ollama logs`
- `main health`
- `audit trail`
- `pending confirms`

Safely destructive plain-text flows:

- `restart gateway`
- `confirm restart gateway`
- `restart v2`
- `confirm restart v2`
- `recover main`
- `confirm recover main`
- `recover all`
- `confirm recover all`
- `force restart ollama`
- `confirm force restart ollama`
- `rollback golden`
- `confirm rollback golden`

Useful exact/fact prompts:

- `where is aquari hotel`
- `aquari hotel phone`
- `bridge_canary`
- `what can you do`
- `reply with exactly: hello`

## Core Local CLI Commands

Health and logs:

- `/home/ai/bin/isla-v2-preflight`
- `/home/ai/bin/isla-check`
- `/home/ai/bin/isla-v2-status`
- `/home/ai/bin/isla-v2-logs "15 min ago"`
- `/home/ai/bin/isla-v2-watchdog-status`
- `/home/ai/bin/isla-v2-watchdog-logs`
- `/home/ai/bin/isla-v2-watchdog-run`

Rollback and packaging:

- `/home/ai/bin/isla-v2-bundle --create pre-change "Before risky work"`
- `/home/ai/bin/isla-v2-restore --show latest`
- `/home/ai/bin/isla-v2-restore --restore latest`
- `/home/ai/bin/isla-v2-restore --restore golden`
- `/home/ai/bin/isla-v2-promote --show`
- `/home/ai/bin/isla-v2-release "name" "note"`

Facts and procedures:

- `python -m isla_v2.core.memory.fact_store get system bridge_canary`
- `python -m isla_v2.core.memory.fact_store search bridge`
- `python -m isla_v2.core.workflows.runner list`
- `python -m isla_v2.core.workflows.runner history`
- `python -m isla_v2.core.workflows.runner run preflight`
- `python -m isla_v2.core.workflows.runner run health_snapshot`

## Safest Restart Flow

Use this pattern for destructive actions:

1. Inspect first:
   - `/ops gateway status`
   - `/ops gateway logs`
   - or `/ops ollama status`
   - or `/ops ollama logs`
2. Request the action:
   - `/ops restart gateway`
   - or `/ops recover main`
   - or `/ops force restart ollama`
3. Confirm within 60 seconds:
   - `/ops confirm restart gateway`
   - `/ops confirm recover main`
   - `/ops confirm force restart ollama`
4. Recheck:
   - `/ops main health`
   - `/ops pending confirms`
   - `/ops audit trail`

If confirm fails:

- rerun the request command
- confirm again immediately
- remember pending confirmations disappear if the bot restarts

## Rollback Safety Commands

Before risky work:

- `/home/ai/bin/isla-v2-bundle --create pre-change "Before risky work"`
- `/home/ai/bin/isla-v2-promote --show`

Rollback drill:

- `/ops golden status`
- `/ops rollback golden`
- `/ops confirm rollback golden`
- wait about 10 seconds
- `/ops rollback report`

Restore locally:

- `/home/ai/bin/isla-v2-restore --show latest`
- `/home/ai/bin/isla-v2-restore --restore latest`
- `/home/ai/bin/isla-v2-restore --restore golden`

After restore:

- `/home/ai/bin/isla-v2-preflight`
- `/home/ai/bin/isla-check`
- `/home/ai/bin/isla-v2-status`

## Facts and Notes

Facts are authoritative:

- `/factget <namespace> <key>`
- `/factlist <namespace>`
- `/factsearch <query>`
- `/facthistory <namespace> <key>`
- `/factset <namespace> <key> <value>`
- `/factdelete <namespace> <key>`

Notes are lower-trust operator context:

- `/noteadd <namespace> <text>`
- `/noterecent [namespace]`
- `/notesearch <query>`

Remember:

- fact TTL is CLI-only and soft-state
- expired facts can still be returned by exact lookup
- notes have no edit/delete command

## Procedures

Allowlisted procedures:

- `preflight`
- `stack_health`
- `watchdog_view`
- `health_snapshot`

Most useful commands:

- `/ops procedures`
- `/ops procedure history`
- `/ops procedure run preflight`
- `/ops procedure run health snapshot`

Common failure cue:

- `PROCEDURE_ALREADY_RUNNING: <name>`

What to do:

- check `/ops procedure history`
- inspect `/home/ai/ai-agents/isla_v2/data/events/procedure_history.jsonl`
- inspect the referenced run log under `/home/ai/ai-agents/isla_v2/data/events/procedure_runs/`

## Top Troubleshooting Cues

- Bot silent:
  - `/home/ai/bin/isla-v2-status`
  - `/home/ai/bin/isla-v2-logs "15 min ago"`
  - `/home/ai/bin/isla-v2-preflight`

- Unknown `/ops` command:
  - run `/help ops`
  - use the canonical command name

- Confirmation expired:
  - run `/ops pending confirms`
  - rerun the request and confirm within 60 seconds

- Ollama trouble:
  - `/ops ollama status`
  - `/ops ollama logs`
  - `restart ollama` is advisory only
  - actual destructive path is `force restart ollama`

- Bundle warning:
  - inspect `README.txt` inside the bundle
  - warnings do not always mean bundle failure

## Top Cautions / Non-Features

- Crew sidecar is retired on this host.
- Pending confirmations are in memory only and disappear on bot restart.
- `restart ollama` does not restart Ollama by itself.
- Grounding is optional and off by default.
- Grounding uses local fact/note search, not Qdrant retrieval.
- Procedure scheduling is not enabled; only the watchdog timer is active.
- `isla-v2-doctor` and `isla-v2-drill` are not read-only.
- `isla-v2-preflight` includes literal source-text checks and can fail after valid refactors.
