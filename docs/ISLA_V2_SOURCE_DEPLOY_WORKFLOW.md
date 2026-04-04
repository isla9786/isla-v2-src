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
- post-deploy `isla-v2-preflight` and `isla-check`
- explicit refusal when invoked outside `/home/ai/ai-agents-src`

## Standard Workflow

1. Make changes in source only.
2. Run tests from source.
3. Review the deployment diff with dry-run.
4. Optionally create a bundle before deployment.
5. Apply the sync into runtime.
6. Let post-deploy checks confirm the runtime is still healthy.

## Exact Commands

### Dry-run only

```bash
cd /home/ai/ai-agents-src
deploy/sync-to-runtime.sh --dry-run
```

Expected result:

- prints source, runtime, exclude, and mode
- shows planned file changes only
- ends with `SYNC_DRY_RUN_OK`

### Apply with bundle-before-deploy

```bash
cd /home/ai/ai-agents-src
deploy/sync-to-runtime.sh --apply --bundle-before-deploy --bundle-note "Before syncing source mirror into runtime"
```

Expected result:

- prints source, runtime, exclude, and mode
- creates a runtime bundle
- syncs source files into `/home/ai/ai-agents`
- runs:
  - `/home/ai/bin/isla-v2-preflight`
  - `/home/ai/bin/isla-check`
- prints:
  - `CHECK_OK: preflight`
  - `CHECK_OK: stack-check`
- ends with `SYNC_APPLY_OK`

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
- top-level `secrets`
- `isla_v2/secrets`
- facts/notes DBs
- audit log
- rollback report
- watchdog state
- procedure run history and logs
- procedure lock files

## Verification After Deploy

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
- Any failed bundle, rsync, preflight, or stack check exits non-zero and prints a `SYNC_FAIL:` summary.
