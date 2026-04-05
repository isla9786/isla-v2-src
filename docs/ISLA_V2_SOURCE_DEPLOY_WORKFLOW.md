# ISLA_V2 Source-To-Runtime Deploy Workflow

- Scope: tracked source mirror to live runtime sync for the current two-root ISLA_V2 setup
- Source root: `/home/ai/ai-agents-src`
- Runtime root: `/home/ai/ai-agents`
- Rule: edit and commit in source, deploy into runtime, keep services pointed at runtime

## Purpose

This workflow keeps:

- `/home/ai/ai-agents-src` as the tracked source tree
- `/home/ai/ai-agents` as the live runtime/deployment root

It does not:

- point services at source
- replace bundle/restore rollback
- move runtime secrets or state into Git

## Checked-In Deploy Helper

- Script: `/home/ai/ai-agents-src/deploy/sync-to-runtime.sh`
- Excludes: `/home/ai/ai-agents-src/deploy/runtime-sync.exclude`

The helper supports:

- dry-run mode
- optional bundle-before-deploy
- real deploy mode
- clean-source enforcement before deploy or verification
- runtime revision marker writes to `/home/ai/ai-agents/deploy/runtime-revision.env`
- post-sync restart of `isla-v2-bot.service`
- post-deploy parity verification plus `isla-v2-preflight` and `isla-check`
- explicit refusal when invoked outside `/home/ai/ai-agents-src`

Parity verification helper:

- Script: `/home/ai/ai-agents-src/deploy/verify-runtime-parity.sh`
- Uses the same checked-in exclude file as deployment
- Reports source commit, runtime revision marker, service binding, and service health
- Prints `PARITY_PASS` or `PARITY_FAIL`

## Standard Workflow

1. Make changes in source only.
2. Commit the source tree so deploy can point at one exact revision.
3. Run tests from source.
4. Review the deployment diff with dry-run.
5. Optionally create a bundle before deployment.
6. Apply the sync into runtime.
7. Let post-deploy parity and health checks confirm the live service is running that exact runtime.

## Exact Commands

### Dry-run only

```bash
cd /home/ai/ai-agents-src
deploy/sync-to-runtime.sh --dry-run
```

Expected result:

- prints source, runtime, exclude, and mode
- prints the source commit/tree and current runtime revision marker if one exists
- shows planned file changes only
- ends with `SYNC_DRY_RUN_OK: <commit>`

If the source repo is dirty, dry-run stops immediately with:

```text
SYNC_FAIL: source git tree is dirty; commit or stash changes before deploying
```

### Apply with bundle-before-deploy

```bash
cd /home/ai/ai-agents-src
deploy/sync-to-runtime.sh --apply --bundle-before-deploy --bundle-note "Before syncing source mirror into runtime"
```

Expected result:

- prints source, runtime, exclude, and mode
- creates a runtime bundle
- syncs source files into `/home/ai/ai-agents`
- writes `/home/ai/ai-agents/deploy/runtime-revision.env`
- restarts `isla-v2-bot.service` only after sync and marker write succeed
- waits for the service to return `active/running`
- runs `deploy/verify-runtime-parity.sh`
- runs:
  - `/home/ai/bin/isla-v2-preflight`
  - `/home/ai/bin/isla-check`
- prints:
  - `CHECK_OK: revision marker`
  - `CHECK_OK: service active`
  - `CHECK_OK: runtime parity`
  - `CHECK_OK: preflight`
  - `CHECK_OK: stack-check`
- ends with `SYNC_APPLY_OK: <commit>`

### Apply without creating a new bundle

```bash
cd /home/ai/ai-agents-src
deploy/sync-to-runtime.sh --apply
```

Use this only if you already created the bundle you want.

### Invocation guard

If you run the helper from outside the source repo, it fails immediately.

Example:

```bash
cd /home/ai
/home/ai/ai-agents-src/deploy/sync-to-runtime.sh --dry-run
```

Expected result:

```text
SYNC_FAIL: run this helper from /home/ai/ai-agents-src or a subdirectory (current: /home/ai)
```

## What The Exclude File Protects

The checked-in exclude file keeps runtime-only state out of source deployments, including:

- `.git`
- `.pytest_cache`
- `venv2026`
- `downloads`
- `reports`
- top-level `secrets`
- `isla_v2/secrets`
- facts/notes DBs
- audit log
- rollback report
- watchdog state
- procedure run history and logs
- procedure lock files
- the runtime revision marker file

## Verification After Deploy

### Source/runtime parity

```bash
cd /home/ai/ai-agents-src
deploy/verify-runtime-parity.sh
```

Expected pass result:

```text
=== parity config ===
source: /home/ai/ai-agents-src
runtime: /home/ai/ai-agents
exclude: /home/ai/ai-agents-src/deploy/runtime-sync.exclude
revision_file: /home/ai/ai-agents/deploy/runtime-revision.env
service: isla-v2-bot.service

=== source revision ===
source_commit: <commit>

=== runtime revision ===
runtime_commit: <commit>

=== service target ===
service_binding_match: yes
service_state: active/running

PARITY_PASS: source commit <commit> matches runtime revision and source-controlled files; service is active/running
```

Expected fail result:

```text
PARITY_FAIL: runtime parity verification failed
```

If it fails, review the listed diff and determine whether:

- runtime was hotfixed directly
- source changes were not deployed yet
- the exclude file needs explicit review
- the service unit drifted away from `/home/ai/ai-agents`
- the service is unhealthy and needs log review

### Runtime health

```bash
/home/ai/bin/isla-v2-preflight
/home/ai/bin/isla-check
systemctl --user --no-pager status isla-v2-bot.service openclaw-gateway.service isla-v2-watchdog.timer
```

Healthy signals:

- `PREFLIGHT_OK`
- stack checks show `[OK]`
- bot service is `active (running)`
- watchdog timer is `active (waiting)` or `active (running)`

## Safety Notes

- Do not edit `/home/ai/ai-agents` directly for normal work.
- If you make an emergency hotfix in runtime, back-port it into source immediately.
- Git rollback belongs in source.
- Bundle/restore rollback remains the live deployment safety net.
- Any dirty source tree, failed bundle, failed rsync, missing venv, bad service binding, failed restart, failed parity check, failed preflight, or failed stack check exits non-zero and prints a `SYNC_FAIL:` or `PARITY_FAIL:` summary.
