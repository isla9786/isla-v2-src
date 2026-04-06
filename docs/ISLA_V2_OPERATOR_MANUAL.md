# ISLA_V2 Operator Manual

- Scope: Current live operator command surface, runbooks, safety model, memory model, procedures, and maintenance workflows for ISLA_V2
- Source repo: `/home/ai/ai-agents-src`
- Runtime repo: `/home/ai/ai-agents`
- Last validated date: `2026-04-05`
- Source of truth: live implementation and scripts win over stale help text, earlier design intent, or undocumented assumptions

# 1. ISLA_V2 Operator Manual Overview

ISLA_V2 is a local operator-facing AI system with one live bot entrypoint, one shared control plane, and a small set of safe local maintenance tools. The live interfaces are:

- Telegram slash commands through the bot
- Plain-text messages to the bot
- Local shell scripts in `/home/ai/bin`
- A few `python -m ...` module CLIs for testing and maintenance

Operationally, it supports:

- stack health and status checks
- bounded log inspection
- confirmation-gated restart, recovery, and rollback actions
- trusted fact lookup and maintenance
- separate operator note capture/search
- allowlisted procedure execution with history
- local broad chat through Ollama, optionally grounded with local fact/note context

Its safety model is implementation-backed:

- Telegram access is allowlisted by user ID
- destructive actions require a 60-second confirmation window
- destructive actions are audited to `/home/ai/ai-agents/isla_v2/data/ops-audit.log`
- unknown `/ops` commands are deterministic, not free-form
- procedures are allowlisted only
- exact facts and notes are stored separately
- grounding is optional and bounded
- there is no arbitrary shell execution or arbitrary service targeting from Telegram

What it explicitly does not do today:

- no live crew sidecar workflow on this host; the sidecar is retired
- no note edit or delete
- no note CLI module
- no scheduled procedure runner beyond the watchdog timer
- no vector/Qdrant retrieval in the grounding path
- no hard-enforced fact expiry; TTL is soft state only

## Release And Runtime Repo Policy

Normal operator release flow:

```bash
cd /home/ai/ai-agents-src
/home/ai/ai-agents/venv2026/bin/python scripts/release_gate.py
```

Required policy:

- make changes in the source repo only
- push source `main` to `origin/main`
- release only via `scripts/release_gate.py`
- do not manually edit files in `/home/ai/ai-agents`
- do not manually `git checkout`, `git reset`, `rsync`, `cp`, or patch the runtime repo during normal operations
- treat `/home/ai/ai-agents` as a deploy target, not a development workspace
- expect detached `HEAD` in the runtime repo during normal operation

Why this matters:

- manual runtime edits break parity between source and runtime
- manual runtime git changes make rollback less trustworthy
- manual shortcuts bypass preflight, source tests, runtime tests, service checks, and automatic rollback

# 2. Live Command Surface Inventory

Where:

- `TG` = Telegram slash command
- `TXT` = plain-text message to the bot
- `CLI` = local shell or `python -m ...`

## Core Telegram commands

| Exact syntax | Aliases | Where | Purpose | Confirmation required | Mutates state |
|---|---|---|---|---|---|
| `/start` | none | TG | show main help | no | no |
| `/help` | none | TG | show main help | no | no |
| `/help facts` | none | TG | show fact/note help | no | no |
| `/help ops` | none | TG | show canonical ops help | no | no |
| `/status` | none | TG | short dashboard | no | no |
| `/status short` | none | TG | short dashboard | no | no |
| `/status full` | none | TG | full dashboard | no | no |
| `/status alert` | not listed in main help, but implemented | TG | issue-focused dashboard | no | no |
| `/ask <prompt>` | none | TG | route prompt through responder | no | no |
| `/ops <command>` | none | TG | run shared ops surface | depends on subcommand | depends on subcommand |
| `/hotel address` | none | TG | return hotel address fact | no | no |
| `/hotel phone` | none | TG | return hotel phone fact | no | no |
| `/system canary` | none | TG | return `bridge_canary` fact | no | no |

## /ops commands

These work in both `/ops ...` form and as the same plain-text message.

### Read-only and advisory ops

| Exact syntax | Aliases accepted | Where | Purpose | Confirmation required | Mutates state |
|---|---|---|---|---|---|
| `alert` | none | TG, TXT, CLI via responder | summarize current issues | no | no |
| `audit trail` | `audit log`, `audit logs` | TG, TXT, CLI | tail recent ops audit | no | no |
| `sidecar status` | `crew sidecar status` | TG, TXT, CLI | sidecar status or retirement message | no | no |
| `sidecar logs` | `crew sidecar logs` | TG, TXT, CLI | sidecar logs or retirement message | no | no |
| `main health` | `main status` | TG, TXT, CLI | run `/home/ai/bin/isla-check` | no | no |
| `v2 status` | `isla v2 bot status` | TG, TXT, CLI | show bot service status | no | no |
| `v2 logs` | `isla v2 bot logs` | TG, TXT, CLI | tail bot logs | no | no |
| `gateway status` | `openclaw gateway status` | TG, TXT, CLI | show gateway service status | no | no |
| `gateway logs` | `openclaw gateway logs` | TG, TXT, CLI | tail gateway logs | no | no |
| `watchdog status` | none | TG, TXT, CLI | show watchdog timer + watchdog view | no | no |
| `watchdog logs` | none | TG, TXT, CLI | tail watchdog logs | no | no |
| `webui status` | `open webui status`, `open-webui status` | TG, TXT, CLI | show WebUI container/API status | no | no |
| `qdrant status` | none | TG, TXT, CLI | show Qdrant container/API status | no | no |
| `golden status` | `release status` | TG, TXT, CLI | show current golden bundle target | no | no |
| `procedures` | `procedure list`, `procedures list` | TG, TXT, CLI | list allowlisted procedures | no | no |
| `procedure history` | `procedures history` | TG, TXT, CLI | show recent procedure runs | no | no |
| `procedure run <name>` | procedure names accept spaced or underscored forms | TG, TXT, CLI | run one allowlisted procedure | no | yes |
| `ollama status` | none | TG, TXT, CLI | show Ollama active/API status | no | no |
| `ollama logs` | none | TG, TXT, CLI | tail Ollama logs | no | no |
| `restart ollama` | none | TG, TXT, CLI | advisory check; does not restart by itself | no | no |
| `rollback report` | none | TG, TXT, CLI | show last rollback drill report | no | no |
| `pending confirms` | `pending confirmation`, `pending confirmations` | TG, TXT, CLI | show outstanding confirmations | no | no |

### Destructive ops

| Exact syntax | Aliases accepted | Where | Purpose | Confirmation required | Mutates state |
|---|---|---|---|---|---|
| `restart sidecar` | `restart crew sidecar service` | TG, TXT, CLI | request sidecar restart | yes | pending/audit only until confirm |
| `confirm restart sidecar` | `confirm restart crew sidecar service` | TG, TXT, CLI | execute sidecar restart | yes, must match pending request | yes |
| `restart v2` | `restart isla v2 bot service` | TG, TXT, CLI | request bot restart | yes | pending/audit only until confirm |
| `confirm restart v2` | `confirm restart isla v2 bot service` | TG, TXT, CLI | schedule bot restart in 2s | yes, must match pending request | yes |
| `recover main` | none | TG, TXT, CLI | request main service recovery | yes | pending/audit only until confirm |
| `confirm recover main` | none | TG, TXT, CLI | start qdrant/open-webui if needed and recheck stack | yes, must match pending request | yes |
| `recover all` | none | TG, TXT, CLI | request broader recovery | yes | pending/audit only until confirm |
| `confirm recover all` | none | TG, TXT, CLI | restart gateway, ensure qdrant/open-webui, recheck Ollama | yes, must match pending request | yes |
| `restart gateway` | none | TG, TXT, CLI | request gateway restart | yes | pending/audit only until confirm |
| `confirm restart gateway` | none | TG, TXT, CLI | restart gateway and show status/health | yes, must match pending request | yes |
| `force restart ollama` | none | TG, TXT, CLI | request privileged Ollama restart | yes | pending/audit only until confirm |
| `confirm force restart ollama` | `confirm restart ollama` | TG, TXT, CLI | attempt privileged Ollama restart via `isla-rootctl` | yes, must match pending request | yes |
| `rollback golden` | none | TG, TXT, CLI | request rollback drill | yes | pending/audit only until confirm |
| `confirm rollback golden` | none | TG, TXT, CLI | launch rollback drill and write report | yes, must match pending request | yes |

## Plain-text operator commands

| Exact syntax / pattern | Aliases | Where | Purpose | Confirmation required | Mutates state |
|---|---|---|---|---|---|
| any supported ops phrase without `/ops` | same aliases as `/ops` | TXT, CLI via responder | shared ops surface | depends on subcommand | depends on subcommand |
| `reply with exactly: <text>` | none | TXT, CLI | exact response passthrough | no | no |
| `say exactly: <text>` | none | TXT, CLI | exact response passthrough | no | no |
| `where is aquari hotel` | `aquari hotel location`, `aquari hotel address`, `address of aquari hotel` | TXT, CLI | fact lookup | no | no |
| `aquari hotel phone` | `aquari hotel phone number`, `phone number of aquari hotel`, `contact number of aquari hotel` | TXT, CLI | fact lookup | no | no |
| `bridge_canary` | `value of bridge_canary` | TXT, CLI | fact lookup | no | no |
| `what can you do` | `how can you help`, `capabilities` | TXT, CLI | capability answer | no | no |
| any other text | none | TXT, CLI | broad chat via Ollama, optionally grounded | no | no |

## Fact commands

| Exact syntax | Aliases | Where | Purpose | Confirmation required | Mutates state |
|---|---|---|---|---|---|
| `/factget <namespace> <key>` | none | TG | get one fact | no | no |
| `/factlist <namespace>` | none | TG | list facts in a namespace | no | no |
| `/factsearch <query>` | none | TG | search facts across namespaces | no | no |
| `/facthistory <namespace> <key>` | none | TG | show fact history | no | no |
| `/factset <namespace> <key> <value>` | none | TG | create/update fact | no | yes |
| `/factdelete <namespace> <key>` | none | TG | delete fact | no | yes |
| `python -m isla_v2.core.memory.fact_store init` | none | CLI | initialize facts DB | no | yes |
| `python -m isla_v2.core.memory.fact_store set ... [--source ...] [--ttl-seconds N]` | none | CLI | create/update fact with optional TTL | no | yes |
| `python -m isla_v2.core.memory.fact_store get|list|search|history|delete ...` | none | CLI | inspect or mutate facts | no | mixed |

## Note commands

| Exact syntax | Aliases | Where | Purpose | Confirmation required | Mutates state |
|---|---|---|---|---|---|
| `/noteadd <namespace> <text>` | none | TG | add note | no | yes |
| `/noterecent [namespace]` | none | TG | show recent notes | no | no |
| `/notesearch <query>` | none | TG | search notes | no | no |

## Procedure commands

| Exact syntax | Aliases | Where | Purpose | Confirmation required | Mutates state |
|---|---|---|---|---|---|
| `/ops procedures` | `procedure list`, `procedures list` | TG, TXT, CLI | list procedures | no | no |
| `/ops procedure history` | `procedures history` | TG, TXT, CLI | show recent procedure runs | no | no |
| `/ops procedure run preflight` | `procedure run preflight` | TG, TXT, CLI | run preflight procedure | no | yes |
| `/ops procedure run stack health` | `procedure run stack_health` | TG, TXT, CLI | run main stack health procedure | no | yes |
| `/ops procedure run watchdog view` | `procedure run watchdog_view` | TG, TXT, CLI | run watchdog view procedure | no | yes |
| `/ops procedure run health snapshot` | `procedure run health_snapshot` | TG, TXT, CLI | write JSON health snapshot | no | yes |

## CLI/operator scripts

| Exact command | Purpose |
|---|---|
| `/home/ai/bin/isla-v2-preflight` | source, compile, route, and health gate |
| `/home/ai/bin/isla-check` | full stack health check |
| `/home/ai/bin/isla-v2-bundle --create <name> "<note>"` | create rollback bundle |
| `/home/ai/bin/isla-v2-restore --restore <target>` | restore bundle or golden |
| `cd /home/ai/ai-agents-src && /home/ai/ai-agents/venv2026/bin/python scripts/release_gate.py` | only supported production release command |
| `/home/ai/bin/isla-v2-snapshot` | write best-effort health snapshot artifacts |
| `/home/ai/bin/isla-v2-doctor` | run golden show, preflight, and restore drill |
| `/home/ai/bin/isla-v2-drill` | restore golden and verify health |
| `/home/ai/bin/isla-v2-status` | show bot service status |
| `/home/ai/bin/isla-v2-logs [since]` | tail recent bot logs |
| `/home/ai/bin/isla-v2-watchdog-status` | show watchdog timer/service status |
| `/home/ai/bin/isla-v2-watchdog-logs` | tail watchdog logs |
| `/home/ai/bin/isla-v2-watchdog-run` | run watchdog once and tail logs |
| `/home/ai/bin/isla-v2-promote --show|--promote <bundle>` | show or set golden bundle |
| `/home/ai/bin/isla-safe-change "<name>" "<note>"` | create protected bundle and print current status |
| `/home/ai/bin/aiwork` | open an interactive shell in the runtime repo when read-only inspection is needed |

# 3. Detailed Command Reference

Unless noted, every `/ops` command also works as the same plain-text message.

## Core Telegram commands

| Command | What it does | When to use it | Example | Expected success response | Common failure responses | Special safety notes | Related commands |
|---|---|---|---|---|---|---|---|
| `/start` | returns main help text | first contact or quick reminder | `/start` | one plain-text help message | `Unauthorized.` | Telegram only | `/help` |
| `/help` | returns main help | quick syntax check | `/help` | one plain-text help message | `Unauthorized.` or `Usage: /help, /help facts, or /help ops` for bad topic | Telegram only | `/help facts`, `/help ops` |
| `/help facts` | returns fact/note usage and examples | learning data commands | `/help facts` | one plain-text help message | `Unauthorized.` | Telegram only | fact/note commands |
| `/help ops` | returns canonical ops help from the live catalog | quick ops list | `/help ops` | one plain-text help message | `Unauthorized.` | shows canonical names, not every alias | `/ops ...` |
| `/status [short\|full\|alert]` | renders dashboard from live service and fact checks | health overview | `/status alert` | preformatted status block | `Unauthorized.` or usage error or `status failed: ...` | implementation supports `alert` even though main help omits it | `/ops alert`, `/ops main health` |
| `/ask <prompt>` | routes prompt through responder | natural-language ops, fact lookup, broad chat | `/ask gateway logs` | plain text or preformatted block depending on result | `Unauthorized.`, usage error, or `ISLA v2 failed: ...` | block formatting is heuristic; multiline replies render as pre blocks | plain-text messages, `/ops` |
| `/ops <command>` | runs the shared ops surface | explicit operator command | `/ops gateway status` | plain text or preformatted block | `Unauthorized.`, deterministic unknown-op help, or `ops failed: ...` | destructive actions use confirmation/audit path | all `/ops` commands |
| `/hotel address` | returns `aquari_hotel.address` | hotel reference | `/hotel address` | plain text fact value | `Unauthorized.`, usage error, `FACT_NOT_FOUND` | Telegram only | `/factget aquari_hotel address` |
| `/hotel phone` | returns `aquari_hotel.phone` | hotel reference | `/hotel phone` | plain text fact value | `Unauthorized.`, usage error, `FACT_NOT_FOUND` | Telegram only | `/factget aquari_hotel phone` |
| `/system canary` | returns `system.bridge_canary` | check canary fact | `/system canary` | plain text fact value | `Unauthorized.`, usage error, `FACT_NOT_FOUND` | Telegram only | `/factget system bridge_canary` |

## Fact and note commands

| Command | What it does | When to use it | Example | Expected success response | Common failure responses | Special safety notes | Related commands |
|---|---|---|---|---|---|---|---|
| `/factget <namespace> <key>` | fetches one exact fact | exact lookup | `/factget system bridge_canary` | `namespace.key = value` | usage error, `FACT_NOT_FOUND`, `factget failed: ...` | Telegram only | plain-text fact lookups, CLI `get` |
| `/factlist <namespace>` | lists facts in one namespace | inspect known exact facts | `/factlist aquari_hotel` | pre block with `namespace.key = value [source=...] [state=...]` | usage error, `NO_FACTS_FOUND`, `factlist failed: ...` | Telegram requires a namespace; CLI can list all | `/factsearch`, CLI `list` |
| `/factsearch <query>` | searches facts by namespace, key, or value | find facts without exact key | `/factsearch bridge` | pre block with matching fact rows | usage error, `NO_FACTS_FOUND`, `factsearch failed: ...` | Telegram search has no namespace filter | `/facthistory`, CLI `search` |
| `/facthistory <namespace> <key>` | shows set/delete history for one fact | audit fact changes | `/facthistory system bridge_canary` | pre block with `set`/`delete` rows and timestamps | usage error, `NO_FACT_HISTORY`, `facthistory failed: ...` | Telegram uses default history limit | CLI `history` |
| `/factset <namespace> <key> <value>` | creates or updates a fact | update authoritative data | `/factset system test_key hello` | `SET_OK: namespace.key` | usage error, `factset failed: ...` | Telegram does not expose TTL; source is `telegram_manual` | CLI `set --ttl-seconds` |
| `/factdelete <namespace> <key>` | deletes a fact | remove stale exact data | `/factdelete system test_key` | `DELETE_OK: namespace.key` or `DELETE_NOT_FOUND: namespace.key` | usage error, `factdelete failed: ...` | delete is recorded in fact history | `/facthistory`, CLI `delete` |
| `/noteadd <namespace> <text>` | appends a note | capture operator context | `/noteadd project gateway timeout observed` | `NOTE_OK: namespace#<id>` | usage error, `noteadd failed: ...` | notes are lower-trust than facts | `/noterecent`, `/notesearch` |
| `/noterecent [namespace]` | shows newest notes | inspect recent operator notes | `/noterecent project` | pre block with `#id namespace: body [kind=...] [source=...] [created_at=...]` | usage error, `NO_NOTES_FOUND`, `noterecent failed: ...` | one optional namespace arg only | `/notesearch` |
| `/notesearch <query>` | searches notes by namespace/body/kind | find note context | `/notesearch gateway timeout` | pre block with matching note rows | usage error, `NO_NOTES_FOUND`, `notesearch failed: ...` | Telegram only; no note CLI today | `/noteadd`, `/noterecent` |

## Read-only and advisory ops

| Command | What it does | When to use it | Example | Expected success response | Common failure responses | Special safety notes | Related commands |
|---|---|---|---|---|---|---|---|
| `alert` | summarizes current issues across bot, gateway, Ollama, WebUI, Qdrant, and canary | quick triage | `/ops alert` | `ISLA ops alert` block; either issues or "No active issues detected." | none expected beyond framework errors | read-only | `/status alert`, `main health` |
| `audit trail` | tails last 30 audit lines | inspect recent destructive requests/confirms | `/ops audit trail` | `ISLA ops audit trail` block | no log yet => "No audit log yet." | read-only | `pending confirms` |
| `sidecar status` | returns retirement text on this host | confirm sidecar is retired | `/ops sidecar status` | retirement message | none expected | runtime short-circuits before underlying status handler | `sidecar logs`, `restart sidecar` |
| `sidecar logs` | returns retirement text on this host | confirm sidecar is retired | `/ops sidecar logs` | retirement message | none expected | runtime short-circuits before missing log wrapper | `sidecar status` |
| `main health` | runs `/home/ai/bin/isla-check` | broad stack health | `/ops main health` | full `isla-check` output | none expected | read-only | `alert`, `gateway status` |
| `v2 status` | shows `systemctl --user status isla-v2-bot.service` | inspect bot runtime | `/ops v2 status` | systemd status block | none expected | read-only | `v2 logs`, `restart v2` |
| `v2 logs` | tails recent bot logs | inspect bot errors | `/ops v2 logs` | last 40 bot log lines | `NO_RECENT_LOGS: ...` from wrapper | output is bounded | `v2 status` |
| `gateway status` | shows gateway service status | inspect OpenClaw gateway | `/ops gateway status` | systemd status block | none expected | read-only | `gateway logs`, `restart gateway` |
| `gateway logs` | tails recent gateway journal | inspect gateway errors | `/ops gateway logs` | last 40 journal lines | none expected | output is bounded | `gateway status` |
| `watchdog status` | combines watchdog timer status and `watchdog --show` output | inspect watchdog state | `/ops watchdog status` | `ISLA ops watchdog status` block | none expected | read-only | `watchdog logs`, `isla-v2-watchdog-run` |
| `watchdog logs` | tails watchdog logs | inspect watchdog behavior | `/ops watchdog logs` | last 40 watchdog log lines | none expected | output is bounded | `watchdog status` |
| `webui status` | shows Open WebUI container and API state | inspect WebUI | `/ops webui status` | `ISLA ops webui status` block | API down => `OPEN_WEBUI_API_DOWN` | read-only | `main health` |
| `qdrant status` | shows Qdrant container and collections API | inspect Qdrant | `/ops qdrant status` | `ISLA ops qdrant status` block | API down => `QDRANT_API_DOWN` | read-only | `main health` |
| `golden status` | shows current golden bundle target | inspect rollback anchor | `/ops golden status` | `GOLDEN_BACKUP: ...` or meta-only/no-golden text | `NO_GOLDEN_BACKUP_SET` | read-only | `rollback golden`, `isla-v2-promote --show` |
| `procedures` | lists allowlisted procedures | see what can be run safely | `/ops procedures` | `ISLA procedures` list with timeouts | none expected | read-only | `procedure history`, `procedure run <name>` |
| `procedure history` | shows recent procedure runs | inspect previous runs | `/ops procedure history` | `ISLA procedure history` with last 8 entries | "No procedure runs yet." | read-only | `procedures`, `procedure run <name>` |
| `procedure run <name>` | runs one allowlisted procedure | execute approved maintenance | `/ops procedure run health snapshot` | `ISLA procedure run` block with status, run_id, log path, and last 40 output lines | `PROCEDURE_UNKNOWN: ...`, `PROCEDURE_ALREADY_RUNNING: ...` | no confirmation, but writes logs/history and may write artifacts | `procedures`, `procedure history` |
| `ollama status` | shows Ollama active/API state plus full stack health | inspect Ollama | `/ops ollama status` | `ISLA ops ollama status` block | API down => `OLLAMA_API_DOWN` | read-only | `ollama logs`, `restart ollama` |
| `ollama logs` | tails Ollama journal | inspect Ollama issues | `/ops ollama logs` | `ISLA ops ollama logs` block | none expected | output is bounded | `ollama status` |
| `restart ollama` | advisory check only | decide whether a forced restart is needed | `/ops restart ollama` | either "already healthy; no restart needed" or "Send exactly: "force restart ollama"" | none expected | despite the name, it does not restart anything | `force restart ollama` |
| `rollback report` | reads `data/rollback-last.txt` | inspect last rollback drill result | `/ops rollback report` | `ISLA rollback report` plus file contents | "No rollback report found yet." | read-only | `rollback golden` |
| `pending confirms` | lists pending destructive confirms | see confirmation window state | `/ops pending confirms` | `ISLA pending confirms` with remaining seconds | "No pending confirmations." | read-only, in-memory only | `audit trail` |

## Destructive ops

| Command | What it does | When to use it | Example | Expected success response | Common failure responses | Special safety notes | Related commands |
|---|---|---|---|---|---|---|---|
| `restart sidecar` | requests sidecar restart | compatibility only on hosts with live sidecar | `/ops restart sidecar` | on this host, retirement message; otherwise confirmation prompt | confirmation expiry if confirmed later on live host | on this host it never reaches the confirm path | `sidecar status` |
| `confirm restart sidecar` | executes sidecar restart | only after pending request on live sidecar host | `/ops confirm restart sidecar` | on this host, retirement message | expiry text if no pending confirm on live host | on this host it is inert | `restart sidecar` |
| `restart v2` | requests bot restart | safe bot restart from Telegram/plain text | `/ops restart v2` | `Confirmation required. Send exactly: "confirm restart v2"` | none expected | writes pending confirm + audit only | `confirm restart v2` |
| `confirm restart v2` | schedules bot restart in 2 seconds | complete bot restart request | `/ops confirm restart v2` | `ACTION_OK: scheduled restart ISLA v2 bot service in 2 seconds` | expiry text | pending confirms are lost if bot restarts before confirm | `v2 status` |
| `recover main` | requests Docker main-service recovery | Qdrant/WebUI remediation | `/ops recover main` | confirmation prompt | none expected | request phase does not change services | `confirm recover main` |
| `confirm recover main` | starts qdrant/open-webui if absent and rechecks stack | recover main services | `/ops confirm recover main` | `ISLA ops recover main` block with steps + `isla-check` output | expiry text | no confirmation persistence across bot restarts | `main health` |
| `recover all` | requests broader recovery | gateway + Docker + Ollama health remediation | `/ops recover all` | confirmation prompt | none expected | request phase does not change services | `confirm recover all` |
| `confirm recover all` | restarts gateway, ensures qdrant/open-webui, and reports Ollama state | broader recovery | `/ops confirm recover all` | `ISLA ops recover all` block with steps + `isla-check` output | expiry text | more invasive than `recover main` | `gateway status`, `ollama status` |
| `restart gateway` | requests gateway restart | bounce OpenClaw gateway safely | `/ops restart gateway` | confirmation prompt | none expected | request phase does not change service | `confirm restart gateway` |
| `confirm restart gateway` | restarts gateway and rechecks status/health | complete gateway restart | `/ops confirm restart gateway` | `ISLA ops restart gateway` block with systemd status + `isla-check` | expiry text | audited on success/failure | `gateway status`, `gateway logs` |
| `force restart ollama` | requests privileged Ollama restart | only when `restart ollama` says it is unhealthy | `/ops force restart ollama` | confirmation prompt | none expected | request phase does not change service | `confirm force restart ollama`, `restart ollama` |
| `confirm force restart ollama` | attempts `sudo /usr/local/bin/isla-rootctl restart ollama` and verifies state | privileged Ollama recovery | `/ops confirm force restart ollama` | `ISLA ops force restart ollama` block with `rc=`, active state, API check, and `isla-check` | expiry text | alias `confirm restart ollama` is accepted | `ollama status`, `ollama logs` |
| `rollback golden` | requests rollback drill | prepare to test rollback path | `/ops rollback golden` | confirmation prompt | none expected | request phase does not start the drill | `confirm rollback golden` |
| `confirm rollback golden` | launches `/home/ai/bin/isla-v2-drill` asynchronously and writes `rollback-last.txt` | run rollback drill | `/ops confirm rollback golden` | `ISLA rollback golden scheduled... Use rollback report in about 10 seconds.` | expiry text | this is a drill/restore action and may briefly restart the bot | `rollback report`, `golden status` |

## Plain-text routed patterns

| Pattern | What it does | When to use it | Example | Expected success response | Common failure responses | Special safety notes | Related commands |
|---|---|---|---|---|---|---|---|
| `reply with exactly: <text>` | returns exactly the provided text | verify deterministic exact reply | `reply with exactly: hello` | exact text only | none | case-insensitive match; useful for smoke tests | `say exactly: ...` |
| `say exactly: <text>` | returns exactly the provided text | same as above | `say exactly: hello` | exact text only | none | case-insensitive match | `reply with exactly: ...` |
| Aquari Hotel address patterns | returns exact address fact | natural-language hotel lookup | `where is aquari hotel` | address value | `FACT_NOT_FOUND` only if fact is missing | hard-coded pattern route | `/hotel address` |
| Aquari Hotel phone patterns | returns exact phone fact | natural-language hotel lookup | `aquari hotel phone number` | phone value | `FACT_NOT_FOUND` only if fact is missing | hard-coded pattern route | `/hotel phone` |
| `bridge_canary` or `value of bridge_canary` | returns exact canary fact | natural-language canary lookup | `bridge_canary` | canary value | `FACT_NOT_FOUND` only if fact is missing | hard-coded pattern route | `/system canary` |
| capability prompts | returns canned capability answer | ask what ISLA_V2 can do | `what can you do` | multiline capability answer | none | bypasses broad chat | `/help`, `/help ops`, `/help facts` |
| other text | falls through to local chat | free-form assistance | `how should I debug a flaky service?` | Ollama response, optionally grounded | broad-chat errors if model/backend fails | grounding is optional and may be off | `/ask <prompt>` |

# 4. Safety and Control Model

- Telegram access is gated by `TELEGRAM_ALLOWED_USER_IDS`. Unauthorized users get `Unauthorized.` on all slash commands.
- Destructive actions are centrally handled in [ops_actions.py](/home/ai/ai-agents/isla_v2/core/tools/ops_actions.py).
- The destructive request phase writes:
  - an in-memory pending confirmation entry
  - an audit line with `result=PENDING: confirm ...`
- Confirmation TTL is 60 seconds.
- Expired or missing confirmations return:
  - `No pending confirmation or it expired. Run the action again and confirm within 60 seconds.`
- Successful destructive confirms append `result=OK` to `/home/ai/ai-agents/isla_v2/data/ops-audit.log`.
- Failed destructive confirms append `result=FAIL: ...`.
- Unknown `/ops` commands return deterministic help:
  - `UNKNOWN_OPS_COMMAND: ...`
  - followed by the supported canonical list
- Plain-text messages that look like ops but do not resolve also return deterministic unknown-op help.
- Telegram output is clipped to 3200 characters by [bot.py](/home/ai/ai-agents/isla_v2/apps/telegram_sidecar/bot.py).
- Most logs are tailed to the last 40 lines before being returned.
- Procedures are allowlisted only. There is no arbitrary procedure name to shell mapping.
- Procedure duplicate prevention uses lock files under `/home/ai/ai-agents/isla_v2/data/procedures/locks`.
- Exact facts and notes are separate stores:
  - facts: `/home/ai/ai-agents/isla_v2/data/facts.db`
  - notes: `/home/ai/ai-agents/isla_v2/data/notes.db`
- Grounding is optional. It is off unless `ISLA_V2_ENABLE_CONTEXT_GROUNDING` is truthy.
- Grounding is bounded by `ISLA_V2_GROUNDING_MAX_CHARS`, default `1200`.
- Grounding failure is silent and safe: if fact/note search errors, broad chat still runs without context.
- Pending confirmations are process memory only. A bot restart clears them.

# 5. Operator Runbooks

## Check whether ISLA_V2 is healthy

- When to use: routine checks, after releases, after restore, after a restart.
- Exact steps:
  - `/status alert` in Telegram
  - `/ops main health` in Telegram
  - `/home/ai/bin/isla-v2-preflight`
  - `/home/ai/bin/isla-check`
- Expected result:
  - `No active issues detected.`
  - `PREFLIGHT_OK`
  - `[OK]` lines for gateway, Ollama, Open WebUI, and Qdrant
- If it fails:
  - inspect `/ops v2 status`, `/ops gateway status`, `/ops watchdog status`
  - then use the relevant restart or recovery runbook

## Inspect the bot

- When to use: bot slow, silent, or recently restarted.
- Exact steps:
  - `/ops v2 status`
  - `/ops v2 logs`
  - local: `/home/ai/bin/isla-v2-status`
  - local: `/home/ai/bin/isla-v2-logs "15 min ago"`
- Expected result:
  - bot service `Active: active (running)`
  - logs without fresh `Traceback`
- If it fails:
  - run `/ops restart v2` then `/ops confirm restart v2`
  - rerun `/home/ai/bin/isla-v2-preflight`

## Inspect the gateway

- When to use: `/ops` works but downstream agent traffic is suspect, or stack health flags gateway.
- Exact steps:
  - `/ops gateway status`
  - `/ops gateway logs`
  - local: `systemctl --user status openclaw-gateway.service --no-pager`
- Expected result:
  - service active, bounded recent logs
- If it fails:
  - `/ops restart gateway`
  - `/ops confirm restart gateway`
  - rerun `/ops main health`

## Inspect the watchdog

- When to use: health alerts, suspected flapping, or after recovery.
- Exact steps:
  - `/ops watchdog status`
  - `/ops watchdog logs`
  - local: `/home/ai/bin/isla-v2-watchdog-status`
  - local: `/home/ai/bin/isla-v2-watchdog-run`
- Expected result:
  - watchdog timer active
  - `No active issues detected.`
- If it fails:
  - inspect `/home/ai/ai-agents/isla_v2/data/watchdog/state.json`
  - rerun `/home/ai/bin/isla-v2-preflight`
  - if needed, local CLI: `python -m isla_v2.apps.watchdog.watchdog --clear-state`

## Inspect Ollama

- When to use: broad chat failing or stack health flags Ollama.
- Exact steps:
  - `/ops ollama status`
  - `/ops ollama logs`
  - advisory: `/ops restart ollama`
- Expected result:
  - `ollama active: active`
  - `OLLAMA_API_OK`
- If it fails:
  - `/ops force restart ollama`
  - `/ops confirm force restart ollama`
  - rerun `/ops ollama status`

## Inspect WebUI

- When to use: WebUI integration or stack health is failing.
- Exact steps:
  - `/ops webui status`
  - local: `curl -fsS http://127.0.0.1:3000/api/version`
- Expected result:
  - container line with `open-webui`
  - API version JSON
- If it fails:
  - use `/ops recover main` then `/ops confirm recover main`
  - rerun `/ops webui status`

## Inspect Qdrant

- When to use: stack health flags Qdrant.
- Exact steps:
  - `/ops qdrant status`
  - local: `curl -fsS http://127.0.0.1:6333/collections`
- Expected result:
  - container line with `qdrant`
  - collections JSON
- If it fails:
  - use `/ops recover main` then `/ops confirm recover main`
  - rerun `/ops qdrant status`

## Safely restart a component

- When to use: one component needs a controlled restart.
- Exact steps:
  - request the action:
    - `/ops restart gateway`
    - `/ops restart v2`
    - `/ops force restart ollama`
  - confirm within 60 seconds:
    - `/ops confirm restart gateway`
    - `/ops confirm restart v2`
    - `/ops confirm force restart ollama`
- Expected result:
  - confirmation prompt on request
  - success block on confirm
  - audit trail entry
- If it fails:
  - check `/ops pending confirms`
  - check `/ops audit trail`
  - rerun the request if the confirm expired

## Recover main services

- When to use: WebUI/Qdrant are down or need recovery without a full rollback drill.
- Exact steps:
  - `/ops recover main`
  - `/ops confirm recover main`
- Expected result:
  - step list such as `- started qdrant`
  - trailing `isla-check` output
- If it fails:
  - escalate to `/ops recover all` then `/ops confirm recover all`

## Inspect audit state

- When to use: you need to prove who requested or confirmed a destructive action.
- Exact steps:
  - `/ops audit trail`
  - `/ops pending confirms`
  - local: `tail -n 30 /home/ai/ai-agents/isla_v2/data/ops-audit.log`
- Expected result:
  - recent `user=... action=... result=...` lines
- If it fails:
  - confirm the bot is running and the action went through `maybe_run_action`
  - inspect bot logs for handler exceptions

## Run preflight

- When to use: before release, after restore, after code changes, after service restart.
- Exact steps:
  - `/home/ai/bin/isla-v2-preflight`
- Expected result:
  - `PREFLIGHT_SOURCE_OK`
  - `PREFLIGHT_COMPILE_OK`
  - `PREFLIGHT_ROUTE_OK`
  - `PREFLIGHT_HEALTH_OK`
  - `PREFLIGHT_OK`
- If it fails:
  - read the first failing section
  - fix source/compile/runtime issue before continuing

## Run the release gate

- When to use: every normal production release.
- Exact steps:
  - `cd /home/ai/ai-agents-src`
  - `/home/ai/ai-agents/venv2026/bin/python scripts/release_gate.py`
- Expected result:
  - `CHECK_OK` for preflight, source tests, runtime parity, runtime tests, and service health
  - `RELEASE_GATE_OK: <commit>`
- If it fails:
  - stop at the first failing gate step
  - fix the source, branch, push, or runtime health issue that the gate reports
  - do not manually edit or manually sync `/home/ai/ai-agents`
  - rerun the release gate after the failing condition is resolved

## Create a bundle

- When to use: before risky changes, before release, before manual rollback work.
- Exact steps:
  - `/home/ai/bin/isla-v2-bundle --create <name> "<note>"`
  - example: `/home/ai/bin/isla-v2-bundle --create pre-maintenance "Before gateway recovery"`
- Expected result:
  - `BUNDLE_OK: ...`
  - `README_OK: ...`
  - `MANIFEST_OK: ...`
  - optional `BUNDLE_WARN: ...`
- If it fails:
  - look for `BUNDLE_METADATA_FAIL: ...`
  - if only warnings appear, the bundle still succeeded
  - inspect the generated `README.txt` and `BUNDLE_MANIFEST.txt`

## Restore from bundle

- When to use: revert to a previous bundle or golden.
- Exact steps:
  - inspect: `/home/ai/bin/isla-v2-restore --show latest`
  - restore: `/home/ai/bin/isla-v2-restore --restore latest`
  - or restore golden: `/home/ai/bin/isla-v2-restore --restore golden`
- Expected result:
  - `PRE_RESTORE_SNAPSHOT_OK: ...`
  - `RESTORE_OK: ...`
  - bot and watchdog restarted
- If it fails:
  - inspect printed skip warnings for privileged restore
  - rerun `/home/ai/bin/isla-v2-preflight`
  - inspect `/home/ai/bin/isla-v2-status`

## Run a procedure manually

- When to use: safe maintenance/check without arbitrary shelling.
- Exact steps:
  - Telegram: `/ops procedure run preflight`
  - local: `python -m isla_v2.core.workflows.runner run preflight`
- Expected result:
  - `ISLA procedure run`
  - `status: OK` or failure/timeout status
  - `log: /home/ai/ai-agents/isla_v2/data/events/procedure_runs/<run_id>.log`
- If it fails:
  - inspect `procedure history`
  - inspect the referenced log file
  - check for duplicate lock

## Inspect procedure history

- When to use: prove a procedure ran or failed.
- Exact steps:
  - Telegram: `/ops procedure history`
  - local: `python -m isla_v2.core.workflows.runner history`
- Expected result:
  - list of recent runs with timestamp, name, status, and `run_id`
- If it fails:
  - inspect `/home/ai/ai-agents/isla_v2/data/events/procedure_history.jsonl`

## Inspect facts

- When to use: verify exact memory.
- Exact steps:
  - Telegram:
    - `/factget system bridge_canary`
    - `/factlist system`
    - `/factsearch bridge`
    - `/facthistory system bridge_canary`
  - local:
    - `python -m isla_v2.core.memory.fact_store get system bridge_canary`
    - `python -m isla_v2.core.memory.fact_store list system`
- Expected result:
  - exact values and history rows
- If it fails:
  - verify the namespace and key
  - inspect `facts.db`
  - rerun with CLI for exact error visibility

## Inspect notes

- When to use: review lower-trust operator context.
- Exact steps:
  - Telegram:
    - `/noteadd project gateway timeout observed`
    - `/noterecent project`
    - `/notesearch timeout`
- Expected result:
  - `NOTE_OK: project#<id>`
  - note rows with `kind`, `source`, `created_at`
- If it fails:
  - remember there is no note delete/edit command
  - verify namespace spelling and query text

## Verify memory grounding behavior

- When to use: confirm whether broad chat is being grounded.
- Exact steps:
  - local:
```bash
cd /home/ai/ai-agents
source venv2026/bin/activate
export ISLA_V2_ENABLE_CONTEXT_GROUNDING=1
python - <<'PY'
from isla_v2.core.memory.retrieval import build_grounding_context
print(build_grounding_context("bridge"))
PY
```
- Expected result:
  - a list of `Authoritative facts:` and/or `Operator notes:` blocks when matching data exists
- If it fails:
  - if grounding is disabled, output is `[]`
  - if searches error, output is also `[]`
  - broad chat still works without context

# 6. Memory Model Reference

- Facts are the authoritative memory layer.
  - path: `/home/ai/ai-agents/isla_v2/data/facts.db`
  - storage: `facts` table plus `fact_history`
  - access:
    - Telegram slash commands
    - plain-text fact lookup patterns
    - CLI: `python -m isla_v2.core.memory.fact_store ...`

- Fact history is built in.
  - every `set` inserts a history row
  - every `delete` inserts a history row
  - history records namespace, key, value, source, updated time, expiry, and operation

- Fact search is substring-based.
  - fields searched: namespace, key, value
  - Telegram: `/factsearch <query>`
  - CLI: `python -m isla_v2.core.memory.fact_store search <query> [--namespace <ns>] [--limit N]`

- Soft TTL exists for facts, but only through the CLI today.
  - CLI: `python -m isla_v2.core.memory.fact_store set <ns> <key> <value> --ttl-seconds N`
  - expired facts are marked `state=expired`
  - expired facts are still returned by `get_fact()`
  - TTL is informational state, not hard eviction

- Notes are a separate lower-trust memory layer.
  - path: `/home/ai/ai-agents/isla_v2/data/notes.db`
  - fields: namespace, body, kind, source, created_at
  - Telegram:
    - `/noteadd`
    - `/noterecent`
    - `/notesearch`
  - there is no note CLI module today

- Grounding is optional and bounded.
  - code path: [retrieval.py](/home/ai/ai-agents/isla_v2/core/memory/retrieval.py)
  - enabled by `ISLA_V2_ENABLE_CONTEXT_GROUNDING`
  - max chars set by `ISLA_V2_GROUNDING_MAX_CHARS`, default `1200`
  - it searches:
    - up to 4 fact matches from `search_facts`
    - up to 4 note matches from `search_notes`
  - it does not use Qdrant or embeddings today

- Trust model:
  - exact facts are highest trust
  - notes are lower trust
  - grounded broad chat may use both, but should not overrule exact facts
  - if grounding fails, broad chat runs ungrounded

# 7. Procedure and Automation Reference

## Procedures

| Procedure name | Aliases accepted | What it does | Timeout | Output artifact |
|---|---|---|---|---|
| `preflight` | none | runs `/home/ai/bin/isla-v2-preflight` | 180s | run log only |
| `stack_health` | `stack health` | runs `/home/ai/bin/isla-check` | 90s | run log only |
| `watchdog_view` | `watchdog view` | runs `python -m isla_v2.apps.watchdog.watchdog --show` | 90s | run log only |
| `health_snapshot` | `health snapshot` | writes bounded JSON health snapshot | 120s | JSON snapshot under `data/events/procedure_runs/` |

## How to run procedures

- Telegram:
  - `/ops procedures`
  - `/ops procedure history`
  - `/ops procedure run preflight`
- Plain text:
  - `procedure run preflight`
- CLI:
  - `python -m isla_v2.core.workflows.runner list`
  - `python -m isla_v2.core.workflows.runner history`
  - `python -m isla_v2.core.workflows.runner run health_snapshot`

## Duplicate prevention

- lock file path:
  - `/home/ai/ai-agents/isla_v2/data/procedures/locks/<name>.lock`
- if a live PID is in the lock file, the runner returns:
  - `PROCEDURE_ALREADY_RUNNING: <name>`
- stale locks are removed automatically only if the recorded PID is no longer alive

## Procedure history and logs

- history file:
  - `/home/ai/ai-agents/isla_v2/data/events/procedure_history.jsonl`
- run logs:
  - `/home/ai/ai-agents/isla_v2/data/events/procedure_runs/<run_id>.log`
- runner return shape:
  - `ISLA procedure run`
  - `name: ...`
  - `status: OK|FAIL|FAIL(<rc>)|TIMEOUT`
  - `run_id: ...`
  - `log: ...`
  - last 40 lines of output

## Scheduling status

- Procedure scheduling is intentionally not enabled.
- There is no maintenance timer for procedures.
- The only active scheduler in the live stack is the watchdog timer:
  - `isla-v2-watchdog.timer`

# 8. CLI and Maintenance Reference

## Primary scripts in `/home/ai/bin`

| Script | Purpose | Safe example | Expected result | Caution |
|---|---|---|---|---|
| `isla-v2-preflight` | code-shape, compile, route, and health gate | `/home/ai/bin/isla-v2-preflight` | `PREFLIGHT_OK` | includes literal source-text gates for `bot.py` |
| `isla-check` | full stack health check | `/home/ai/bin/isla-check` | `[OK]` and `[INFO]` lines; `=== Done ===` | depends on `/home/ai/bin/isla-healthcheck.sh` |
| `isla-v2-bundle` | create/read change bundles | `/home/ai/bin/isla-v2-bundle --create pre-change "Before gateway work"` | `BUNDLE_OK`, `README_OK`, `MANIFEST_OK` | may warn and skip privileged files if sudo copy is unavailable |
| `isla-v2-restore` | restore a bundle or golden | `/home/ai/bin/isla-v2-restore --restore golden` | `PRE_RESTORE_SNAPSHOT_OK`, `RESTORE_OK` | restarts bot and watchdog timer |
| `release_gate.py` | fail-closed source-to-runtime release gate | `cd /home/ai/ai-agents-src && /home/ai/ai-agents/venv2026/bin/python scripts/release_gate.py` | `RELEASE_GATE_OK: <commit>` | only supported release path; do not replace with manual runtime edits |
| `isla-v2-snapshot` | write best-effort health snapshot files | `/home/ai/bin/isla-v2-snapshot` | `SNAPSHOT_OK: <dir>` | snapshots what it can; individual capture failures do not abort |
| `isla-v2-doctor` | run golden show, preflight, and drill | `/home/ai/bin/isla-v2-doctor` | `DOCTOR_PASS` or `DOCTOR_FAIL` | not read-only; it runs the restore drill |
| `isla-v2-drill` | restore golden and verify health | `/home/ai/bin/isla-v2-drill` | `DRILL_PASS` or `DRILL_FAIL` | mutating restore test; may restart bot |
| `isla-v2-status` | bot service status wrapper | `/home/ai/bin/isla-v2-status` | `systemctl --user status` output | read-only |
| `isla-v2-logs` | recent bot logs | `/home/ai/bin/isla-v2-logs "15 min ago"` | last 40 log lines or `NO_RECENT_LOGS` | bounded output |
| `isla-v2-watchdog-status` | watchdog timer/service status | `/home/ai/bin/isla-v2-watchdog-status` | timer status + service status | read-only |
| `isla-v2-watchdog-logs` | recent watchdog logs | `/home/ai/bin/isla-v2-watchdog-logs` | last 50 lines | bounded output |
| `isla-v2-watchdog-run` | start watchdog once and tail logs | `/home/ai/bin/isla-v2-watchdog-run` | service start plus recent logs | mutates watchdog state only |
| `isla-v2-promote` | show or set golden bundle | `/home/ai/bin/isla-v2-promote --show` | `GOLDEN_BACKUP: ...` or related text | `--promote` mutates rollback anchor |
| `isla-safe-change` | create protected bundle and print current state | `/home/ai/bin/isla-safe-change "pre-change" "Before test"` | bundle info + current status/watchdog/golden | not the supported production release command |
| `aiwork` | enter repo with venv activated | `/home/ai/bin/aiwork` | interactive shell in `/home/ai/ai-agents` | use for inspection only; do not treat runtime as a development workspace |

## Useful module CLIs

| Command | Purpose | Example |
|---|---|---|
| `python -m isla_v2.core.memory.fact_store ...` | facts DB maintenance | `python -m isla_v2.core.memory.fact_store search bridge` |
| `python -m isla_v2.core.workflows.runner ...` | procedure list/history/run | `python -m isla_v2.core.workflows.runner run preflight` |
| `python -m isla_v2.core.tools.ops_status status|logs <target>` | direct status/log access | `python -m isla_v2.core.tools.ops_status status gateway` |
| `python -m isla_v2.core.router.responder <prompt>` | test responder output | `python -m isla_v2.core.router.responder "gateway status"` |
| `python -m isla_v2.core.router.deterministic_router <prompt>` | inspect routing decision | `python -m isla_v2.core.router.deterministic_router "aquari hotel address"` |
| `python -m isla_v2.core.models.local_chat [--model MODEL] <prompt>` | test broad chat directly | `python -m isla_v2.core.models.local_chat "summarize the stack"` |
| `python -m isla_v2.apps.watchdog.watchdog --show|--once|--force-alert|--clear-state` | inspect or operate watchdog directly | `python -m isla_v2.apps.watchdog.watchdog --show` |

# 9. Troubleshooting Guide

## Bot not responding

- Likely cause: `isla-v2-bot.service` is not active, Telegram user is unauthorized, or bot logs contain an exception.
- Exact checks:
  - `/home/ai/bin/isla-v2-status`
  - `/home/ai/bin/isla-v2-logs "15 min ago"`
  - `/home/ai/bin/isla-v2-preflight`
- Next action:
  - if service is down, use `/ops restart v2` then `/ops confirm restart v2`
  - if unauthorized, verify your Telegram user ID is in `isla_v2_bot.env`

## Unknown /ops command

- Likely cause: wrong canonical name, alias not obvious, or plain text got routed as ops.
- Exact checks:
  - `/help ops`
  - `/ops not-real-command`
  - local:
```bash
python - <<'PY'
from isla_v2.core.tools.ops_catalog import ops_help_text
print(ops_help_text())
PY
```
- Next action:
  - use the canonical command from the ops help list
  - remember aliases exist even when help only shows the canonical form

## Confirmation expired

- Likely cause: more than 60 seconds passed, or the bot restarted and lost in-memory pending confirmations.
- Exact checks:
  - `/ops pending confirms`
  - `/ops audit trail`
- Next action:
  - rerun the request command
  - confirm again immediately with the exact `confirm ...` text

## Procedure already running

- Likely cause: a live lock file exists for that procedure.
- Exact checks:
  - `/ops procedure history`
  - `ls -l /home/ai/ai-agents/isla_v2/data/procedures/locks`
  - `cat /home/ai/ai-agents/isla_v2/data/procedures/locks/<name>.lock`
- Next action:
  - wait for the current run to finish
  - if the PID in the lock is stale, inspect carefully before deleting the lock file

## Preflight failed

- Likely cause: source-shape regression in `bot.py`, compile error, broken route path, or unhealthy runtime.
- Exact checks:
  - `/home/ai/bin/isla-v2-preflight`
- Next action:
  - fix the first failing section in order:
    - source invariants
    - compile
    - text-routed `/ops` smoke
    - health

## Bundle warnings

- Likely cause: optional privileged files could not be copied non-interactively.
- Exact checks:
  - inspect the bundle `README.txt`
  - inspect `BUNDLE_WARN: ...` output
- Next action:
  - if the warning is about `isla-rootctl.sudoers`, the bundle still succeeded
  - if you need that privileged file in the bundle, rerun from a shell with the required sudo access

## Memory command confusion

- Likely cause: facts and notes are different stores, or TTL expectations are wrong.
- Exact checks:
  - facts: `/factget`, `/factlist`, `/factsearch`, `/facthistory`
  - notes: `/noteadd`, `/noterecent`, `/notesearch`
  - CLI facts: `python -m isla_v2.core.memory.fact_store --help`
- Next action:
  - use facts for authoritative values
  - use notes for operator context
  - remember TTL is CLI-only and soft, not hard expiry

## Grounding disabled or unavailable

- Likely cause: `ISLA_V2_ENABLE_CONTEXT_GROUNDING` is off, or local search failed.
- Exact checks:
```bash
cd /home/ai/ai-agents
source venv2026/bin/activate
python - <<'PY'
from isla_v2.core.memory.retrieval import grounding_enabled, build_grounding_context
print("enabled=", grounding_enabled())
print(build_grounding_context("bridge"))
PY
```
- Next action:
  - set `ISLA_V2_ENABLE_CONTEXT_GROUNDING=1` for the process you are testing
  - if output is still empty, verify matching facts/notes exist

## Log output unavailable

- Likely cause: no recent logs, retired sidecar, or the target has no log handler.
- Exact checks:
  - `/ops v2 logs`
  - `/ops gateway logs`
  - `/ops watchdog logs`
  - `/ops ollama logs`
- Next action:
  - widen the window with local scripts where supported
  - for sidecar, expect the retirement message on this host

## Service appears healthy but command fails

- Likely cause: syntax issue, authorization issue, confirmation expiry, or command is advisory only.
- Exact checks:
  - `/help ops`
  - `/ops pending confirms`
  - `/ops audit trail`
  - `/ops ollama status`
- Next action:
  - verify you used the exact canonical command
  - for Ollama, remember `restart ollama` is advisory and `force restart ollama` is the actual destructive path

# 10. Known Limits and Current Non-Features

- The legacy crew sidecar is retired on this host.
- Sidecar ops commands exist for compatibility, but on this host they return a retirement message.
- `/home/ai/bin/isla-crew-logs` is not present, but the runtime retirement short-circuit prevents that path from being used.
- There is no note edit or delete command.
- There is no note CLI module.
- Fact TTL is soft state only.
- Expired facts are still returned by exact fact lookup.
- Telegram fact creation does not expose TTL; TTL is CLI-only.
- Grounding is off by default.
- Grounding uses local fact/note substring search only.
- Qdrant is part of the stack, but not part of the current grounding implementation.
- Procedure scheduling is not enabled.
- The only active timer is the watchdog timer.
- Pending confirmations are in memory only and disappear on bot restart.
- `restart ollama` is advisory, not an actual restart.
- `isla-v2-doctor` is not read-only; it runs the restore drill.
- `isla-v2-drill` restores golden and is therefore mutating.
- `isla-v2-restore` attempts a compile check, but that compile step is best-effort and does not hard-fail the restore.
- `isla-v2-preflight` uses literal source-text checks against `bot.py`, so refactors can fail preflight even if behavior is still valid.

# 11. Quick Reference Appendix

- Telegram health:
  - `/status alert`
  - `/ops main health`
  - `/ops v2 status`
  - `/ops gateway status`
  - `/ops watchdog status`

- Telegram logs:
  - `/ops v2 logs`
  - `/ops gateway logs`
  - `/ops watchdog logs`
  - `/ops ollama logs`

- Safe restart flow:
  - `/ops restart gateway`
  - `/ops confirm restart gateway`
  - `/ops pending confirms`
  - `/ops audit trail`

- Recovery flow:
  - `/ops recover main`
  - `/ops confirm recover main`
  - if still degraded: `/ops recover all`
  - then `/ops confirm recover all`

- Release flow:
  - `cd /home/ai/ai-agents-src`
  - `/home/ai/ai-agents/venv2026/bin/python scripts/release_gate.py`
  - do not manually edit or manually sync `/home/ai/ai-agents`

- Rollback drill flow:
  - `/ops golden status`
  - `/ops rollback golden`
  - `/ops confirm rollback golden`
  - wait about 10 seconds
  - `/ops rollback report`

- Facts and notes:
  - `/factget system bridge_canary`
  - `/factsearch bridge`
  - `/facthistory system bridge_canary`
  - `/noteadd project gateway timeout observed`
  - `/noterecent project`
  - `/notesearch timeout`

- Procedures:
  - `/ops procedures`
  - `/ops procedure history`
  - `/ops procedure run preflight`
  - `/ops procedure run health snapshot`

- Local safety checks:
  - `/home/ai/bin/isla-v2-preflight`
  - `/home/ai/bin/isla-check`
  - `/home/ai/bin/isla-v2-status`
  - `/home/ai/bin/isla-v2-logs "15 min ago"`

# 12. Source-of-Truth Validation Notes

Files used as primary sources:

- [bot.py](/home/ai/ai-agents/isla_v2/apps/telegram_sidecar/bot.py)
- [responder.py](/home/ai/ai-agents/isla_v2/core/router/responder.py)
- [deterministic_router.py](/home/ai/ai-agents/isla_v2/core/router/deterministic_router.py)
- [ops_catalog.py](/home/ai/ai-agents/isla_v2/core/tools/ops_catalog.py)
- [ops_actions.py](/home/ai/ai-agents/isla_v2/core/tools/ops_actions.py)
- [ops_status.py](/home/ai/ai-agents/isla_v2/core/tools/ops_status.py)
- [fact_store.py](/home/ai/ai-agents/isla_v2/core/memory/fact_store.py)
- [note_store.py](/home/ai/ai-agents/isla_v2/core/memory/note_store.py)
- [retrieval.py](/home/ai/ai-agents/isla_v2/core/memory/retrieval.py)
- [procedures.py](/home/ai/ai-agents/isla_v2/core/workflows/procedures.py)
- [runner.py](/home/ai/ai-agents/isla_v2/core/workflows/runner.py)
- [local_chat.py](/home/ai/ai-agents/isla_v2/core/models/local_chat.py)
- [capability_answers.py](/home/ai/ai-agents/isla_v2/core/policies/capability_answers.py)
- [watchdog.py](/home/ai/ai-agents/isla_v2/apps/watchdog/watchdog.py)
- [paths.py](/home/ai/ai-agents/isla_v2/core/common/paths.py)
- [isla-v2-preflight](/home/ai/bin/isla-v2-preflight)
- [isla-v2-bundle](/home/ai/bin/isla-v2-bundle)
- [isla-v2-restore](/home/ai/bin/isla-v2-restore)
- [release_gate.py](/home/ai/ai-agents-src/scripts/release_gate.py)
- [isla-check](/home/ai/bin/isla-check)
- [isla-v2-doctor](/home/ai/bin/isla-v2-doctor)
- [isla-v2-snapshot](/home/ai/bin/isla-v2-snapshot)
- [isla-v2-drill](/home/ai/bin/isla-v2-drill)
- [isla-v2-promote](/home/ai/bin/isla-v2-promote)
- [isla-v2-status](/home/ai/bin/isla-v2-status)
- [isla-v2-logs](/home/ai/bin/isla-v2-logs)
- [isla-v2-watchdog-status](/home/ai/bin/isla-v2-watchdog-status)
- [isla-v2-watchdog-logs](/home/ai/bin/isla-v2-watchdog-logs)
- [isla-v2-watchdog-run](/home/ai/bin/isla-v2-watchdog-run)
- [isla-crew-check](/home/ai/bin/isla-crew-check)
- [isla-healthcheck.sh](/home/ai/bin/isla-healthcheck.sh)

Implementation-over-help mismatches resolved in favor of code:

- [bot.py](/home/ai/ai-agents/isla_v2/apps/telegram_sidecar/bot.py) main help text says `/status [short|full]`, but the implementation also supports `/status alert`. Implementation won.
- [ops_catalog.py](/home/ai/ai-agents/isla_v2/core/tools/ops_catalog.py) help shows canonical ops commands only. The implementation also accepts aliases like `audit logs`, `release status`, `confirm restart ollama`, and `procedure list`. Implementation won.
- Sidecar commands are still listed in the catalog, but [ops_actions.py](/home/ai/ai-agents/isla_v2/core/tools/ops_actions.py) short-circuits them to a retirement message on this host. Runtime behavior won.
- Earlier upgrade intent might suggest retrieval via Qdrant, but [retrieval.py](/home/ai/ai-agents/isla_v2/core/memory/retrieval.py) currently uses only `search_facts()` and `search_notes()`. Implementation won.
- There is no scheduled procedure timer in the live code or user systemd units. Only the watchdog timer exists. Implementation won.
- `restart ollama` sounds destructive, but [ops_actions.py](/home/ai/ai-agents/isla_v2/core/tools/ops_actions.py) implements it as an advisory health check that points to `force restart ollama` when needed. Implementation won.
