#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CURRENT_DIR="$(pwd -P)"
RUNTIME_ROOT="${ISLA_V2_RUNTIME_ROOT:-/home/ai/ai-agents}"
EXCLUDE_FILE="$SOURCE_ROOT/deploy/runtime-sync.exclude"
MODE="dry-run"
BUNDLE_BEFORE_DEPLOY=0
BUNDLE_NOTE="Before syncing ai-agents-src into live runtime"
BUNDLE_NAME="pre-deploy-$(date -u +%Y%m%dT%H%M%SZ)"
ACTIVE_MODE_LABEL=""

fail() {
  echo
  echo "SYNC_FAIL: $1" >&2
  exit 1
}

on_err() {
  local rc=$?
  if [[ $rc -ne 0 ]]; then
    echo
    echo "SYNC_FAIL: ${ACTIVE_MODE_LABEL:-helper} aborted (rc=$rc)" >&2
  fi
  exit "$rc"
}

trap on_err ERR

print_sync_context() {
  echo "=== sync config ==="
  echo "source: $SOURCE_ROOT"
  echo "runtime: $RUNTIME_ROOT"
  echo "exclude: $EXCLUDE_FILE"
  echo "mode: $1"
}

require_source_repo_invocation() {
  if [[ "$CURRENT_DIR" != "$SOURCE_ROOT" && "$CURRENT_DIR" != "$SOURCE_ROOT"/* ]]; then
    fail "run this helper from $SOURCE_ROOT or a subdirectory (current: $CURRENT_DIR)"
  fi

  local repo_root
  repo_root="$(git -C "$SOURCE_ROOT" rev-parse --show-toplevel 2>/dev/null)" || {
    fail "source root is not a git working tree: $SOURCE_ROOT"
  }
  [[ "$repo_root" == "$SOURCE_ROOT" ]] || {
    fail "source root git toplevel mismatch: expected $SOURCE_ROOT, got $repo_root"
  }
}

usage() {
  cat <<EOF
Usage: $(basename "$0") [--dry-run] [--apply] [--bundle-before-deploy] [--bundle-note NOTE]

Modes:
  --dry-run               Show the rsync plan only (default)
  --apply                 Sync source into runtime and run post-deploy checks

Options:
  --bundle-before-deploy  Create a runtime bundle before --apply
  --bundle-note NOTE      Override the default bundle note
  --help                  Show this help

Environment:
  ISLA_V2_RUNTIME_ROOT    Override the runtime root (default: /home/ai/ai-agents)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      MODE="dry-run"
      shift
      ;;
    --apply)
      MODE="apply"
      shift
      ;;
    --bundle-before-deploy)
      BUNDLE_BEFORE_DEPLOY=1
      shift
      ;;
    --bundle-note)
      [[ $# -ge 2 ]] || { echo "SYNC_FAIL: --bundle-note requires a value" >&2; exit 1; }
      BUNDLE_NOTE="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "SYNC_FAIL: unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

[[ -d "$SOURCE_ROOT" ]] || fail "source root missing: $SOURCE_ROOT"
[[ -d "$RUNTIME_ROOT" ]] || fail "runtime root missing: $RUNTIME_ROOT"
[[ -f "$EXCLUDE_FILE" ]] || fail "exclude file missing: $EXCLUDE_FILE"
[[ "$SOURCE_ROOT" != "$RUNTIME_ROOT" ]] || fail "source and runtime roots must differ"
require_source_repo_invocation

if [[ "$MODE" != "apply" && "$BUNDLE_BEFORE_DEPLOY" -eq 1 ]]; then
  fail "--bundle-before-deploy requires --apply"
fi

if [[ "$MODE" == "dry-run" ]]; then
  ACTIVE_MODE_LABEL="dry-run"
  print_sync_context "$MODE"
  echo
  echo "=== rsync dry-run ==="
  rsync -avn --delete-delay --itemize-changes \
    --exclude-from="$EXCLUDE_FILE" \
    "$SOURCE_ROOT"/ "$RUNTIME_ROOT"/
  echo
  echo "SYNC_DRY_RUN_OK"
  exit 0
fi

ACTIVE_MODE_LABEL="apply"
print_sync_context "$MODE"

if [[ "$BUNDLE_BEFORE_DEPLOY" -eq 1 ]]; then
  echo
  echo "=== bundle before deploy ==="
  /home/ai/bin/isla-v2-bundle --create "$BUNDLE_NAME" "$BUNDLE_NOTE"
fi

echo
echo "=== rsync apply ==="
rsync -av --delete-delay --itemize-changes \
  --exclude-from="$EXCLUDE_FILE" \
    "$SOURCE_ROOT"/ "$RUNTIME_ROOT"/

echo
echo "=== post-deploy preflight ==="
/home/ai/bin/isla-v2-preflight
echo "CHECK_OK: preflight"

echo
echo "=== post-deploy stack check ==="
/home/ai/bin/isla-check
echo "CHECK_OK: stack-check"

echo
echo "SYNC_APPLY_OK"
