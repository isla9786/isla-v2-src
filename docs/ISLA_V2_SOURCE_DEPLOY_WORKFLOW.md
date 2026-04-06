# ISLA_V2 Source-To-Runtime Deploy Workflow

- Scope: the only supported release path for the current two-repo ISLA_V2 setup
- Source repo: `/home/ai/ai-agents-src`
- Runtime repo: `/home/ai/ai-agents`
- Canonical release gate: `scripts/release_gate.py`

## Operator Policy

- Make code and tracked file changes in the source repo only.
- Push source `main` to `origin/main` before releasing.
- Release only with the gate command shown below.
- Do not manually edit `/home/ai/ai-agents` during normal operations.
- Do not manually `git checkout`, `git reset`, `rsync`, `cp`, or patch the runtime repo during normal operations.
- The runtime repo is a deploy target, not a development workspace.
- Detached `HEAD` in the runtime repo is expected by design.

Why this policy exists:

- manual runtime edits break source-to-runtime parity
- manual runtime git manipulation makes rollback less trustworthy
- manual sync shortcuts bypass preflight, tests, parity checks, and automatic rollback

## Only Supported Release Command

Run exactly:

```bash
cd /home/ai/ai-agents-src
/home/ai/ai-agents/venv2026/bin/python scripts/release_gate.py
```

This is the only supported operator release path.

## What The Release Gate Enforces

In order, the gate requires:

- source repo exists
- runtime repo exists
- explicit venv python exists at `/home/ai/ai-agents/venv2026/bin/python`
- source repo is a clean git worktree
- runtime repo is a clean git worktree before deploy
- source repo is on `main`
- source `HEAD` exactly matches `origin/main`
- source compile sanity passes
- source test suite passes
- runtime deploys the exact source commit
- runtime `HEAD` matches source `HEAD`
- runtime repo is clean after deploy
- runtime test suite passes
- `isla-v2-bot.service` restarts and returns `active`

If any post-deploy check fails, the gate:

- resets the runtime repo back to the previously captured runtime commit
- restarts `isla-v2-bot.service` on the rolled-back runtime
- exits non-zero

## Expected Success Shape

Typical success markers include:

- `CHECK_OK: source repo clean worktree`
- `CHECK_OK: runtime repo clean worktree`
- `CHECK_OK: source HEAD`
- `CHECK_OK: origin/main`
- `CHECK_OK: source test suite`
- `CHECK_OK: runtime HEAD after deploy`
- `CHECK_OK: runtime repo after deploy clean worktree`
- `CHECK_OK: runtime test suite`
- `CHECK_OK: confirm isla-v2-bot.service is active`
- `RELEASE_GATE_OK: <commit>`

## Expected Failure Behavior

If the gate fails before deploy:

- runtime is not modified
- the service is not restarted
- the command exits non-zero with the first failing step

If the gate fails after deploy:

- runtime is rolled back to the previously captured runtime commit
- the service is restarted on the rolled-back runtime
- the command exits non-zero

Do not try to "help" a failed release by manually editing or manually syncing the runtime repo.

## Read-Only Verification After A Release

If you want to confirm the live state after a successful run, use read-only checks:

```bash
cd /home/ai/ai-agents-src
git rev-parse HEAD

cd /home/ai/ai-agents
git rev-parse HEAD
git status --short

systemctl --user status isla-v2-bot.service --no-pager
journalctl --user -u isla-v2-bot.service -n 60 --no-pager
```

Healthy signals:

- source and runtime commit IDs match exactly
- `git status --short` in the runtime repo prints nothing
- `isla-v2-bot.service` is `active (running)`

## Runtime-Only State

The runtime repo intentionally keeps some local-only state outside tracked source behavior, including items such as:

- `venv2026/`
- `downloads/`
- `reports/`
- `secrets/`
- `isla_v2/secrets/`
- runtime databases and logs under `isla_v2/data/`

That state must stay outside normal source edits and outside manual release shortcuts.

## Internal Helpers

These checked-in scripts still exist, but they are not the documented operator release command:

- `/home/ai/ai-agents-src/deploy/sync-to-runtime.sh`
- `/home/ai/ai-agents-src/deploy/verify-runtime-parity.sh`

Treat them as implementation details or exceptional troubleshooting aids, not as the standard release workflow.
