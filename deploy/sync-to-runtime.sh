#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CURRENT_DIR="$(pwd -P)"
RUNTIME_ROOT="${ISLA_V2_RUNTIME_ROOT:-/home/ai/ai-agents}"
SERVICE_NAME="${ISLA_V2_SERVICE_NAME:-isla-v2-bot.service}"
SERVICE_MODULE="isla_v2.apps.telegram_sidecar.bot"
EXCLUDE_FILE="$SOURCE_ROOT/deploy/runtime-sync.exclude"
REVISION_FILE_REL="deploy/runtime-revision.env"
REVISION_FILE="$RUNTIME_ROOT/$REVISION_FILE_REL"
RUNTIME_PYTHON="$RUNTIME_ROOT/venv2026/bin/python"
MODE="dry-run"
BUNDLE_BEFORE_DEPLOY=0
BUNDLE_NOTE="Before syncing ai-agents-src into live runtime"
BUNDLE_NAME="pre-deploy-$(date -u +%Y%m%dT%H%M%SZ)"
ACTIVE_MODE_LABEL=""
RESTART_WAIT_SECONDS=15
SOURCE_BRANCH=""
SOURCE_COMMIT=""
SOURCE_TREE=""
RUNTIME_REVISION_SOURCE="missing"
RUNTIME_COMMIT=""
RUNTIME_TREE=""
RUNTIME_DEPLOYED_AT_UTC=""
RUNTIME_BRANCH=""

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
  echo "service: $SERVICE_NAME"
  echo "exclude: $EXCLUDE_FILE"
  echo "revision_file: $REVISION_FILE"
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

require_clean_source_repo() {
  local status
  status="$(git -C "$SOURCE_ROOT" status --short --untracked-files=all)"
  if [[ -n "$status" ]]; then
    echo "=== source repo status ==="
    printf '%s\n' "$status"
    fail "source git tree is dirty; commit or stash changes before deploying"
  fi
}

capture_source_revision() {
  SOURCE_BRANCH="$(git -C "$SOURCE_ROOT" rev-parse --abbrev-ref HEAD)"
  SOURCE_COMMIT="$(git -C "$SOURCE_ROOT" rev-parse HEAD)"
  SOURCE_TREE="$(git -C "$SOURCE_ROOT" rev-parse HEAD^{tree})"
}

read_runtime_revision() {
  RUNTIME_REVISION_SOURCE="missing"
  RUNTIME_COMMIT=""
  RUNTIME_TREE=""
  RUNTIME_DEPLOYED_AT_UTC=""
  RUNTIME_BRANCH=""

  if [[ -f "$REVISION_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$REVISION_FILE"
    RUNTIME_REVISION_SOURCE="marker"
    RUNTIME_COMMIT="${DEPLOY_SOURCE_COMMIT:-}"
    RUNTIME_TREE="${DEPLOY_SOURCE_TREE:-}"
    RUNTIME_DEPLOYED_AT_UTC="${DEPLOYED_AT_UTC:-}"
    RUNTIME_BRANCH="${DEPLOY_SOURCE_BRANCH:-}"
    return 0
  fi

  if git -C "$RUNTIME_ROOT" rev-parse --show-toplevel >/dev/null 2>&1; then
    RUNTIME_REVISION_SOURCE="git"
    RUNTIME_COMMIT="$(git -C "$RUNTIME_ROOT" rev-parse HEAD)"
    RUNTIME_TREE="$(git -C "$RUNTIME_ROOT" rev-parse HEAD^{tree})"
    RUNTIME_DEPLOYED_AT_UTC="git-checkout"
    RUNTIME_BRANCH="$(git -C "$RUNTIME_ROOT" rev-parse --abbrev-ref HEAD)"
  fi
}

print_source_revision() {
  echo "=== source revision ==="
  echo "source_branch: $SOURCE_BRANCH"
  echo "source_commit: $SOURCE_COMMIT"
  echo "source_tree: $SOURCE_TREE"
}

print_runtime_revision() {
  echo "=== current runtime revision ==="
  echo "runtime_revision_source: $RUNTIME_REVISION_SOURCE"
  if [[ "$RUNTIME_REVISION_SOURCE" == "missing" ]]; then
    echo "runtime_commit: unavailable"
    echo "runtime_tree: unavailable"
    echo "runtime_deployed_at_utc: unavailable"
    return 0
  fi

  echo "runtime_branch: ${RUNTIME_BRANCH:-unknown}"
  echo "runtime_commit: ${RUNTIME_COMMIT:-unknown}"
  echo "runtime_tree: ${RUNTIME_TREE:-unknown}"
  echo "runtime_deployed_at_utc: ${RUNTIME_DEPLOYED_AT_UTC:-unknown}"
}

require_runtime_preconditions() {
  local service_unit

  [[ -d "$RUNTIME_ROOT" ]] || fail "runtime root missing: $RUNTIME_ROOT"
  [[ -f "$EXCLUDE_FILE" ]] || fail "exclude file missing: $EXCLUDE_FILE"
  [[ "$SOURCE_ROOT" != "$RUNTIME_ROOT" ]] || fail "source and runtime roots must differ"
  [[ -x "$RUNTIME_PYTHON" ]] || fail "runtime venv python missing: $RUNTIME_PYTHON"

  service_unit="$(systemctl --user cat "$SERVICE_NAME" 2>&1)" || {
    printf '%s\n' "$service_unit"
    fail "unable to read systemd user unit: $SERVICE_NAME"
  }

  printf '%s\n' "$service_unit" | grep -Fq "WorkingDirectory=$RUNTIME_ROOT" || {
    printf '%s\n' "$service_unit"
    fail "service WorkingDirectory does not point at runtime root: $RUNTIME_ROOT"
  }

  printf '%s\n' "$service_unit" | grep -Fq "ExecStart=$RUNTIME_PYTHON -m $SERVICE_MODULE" || {
    printf '%s\n' "$service_unit"
    fail "service ExecStart does not point at runtime venv/module"
  }
}

write_revision_marker() {
  local tmp

  mkdir -p "$(dirname "$REVISION_FILE")"
  tmp="$(mktemp "$RUNTIME_ROOT/.runtime-revision.XXXXXX")"
  cat >"$tmp" <<EOF
# Managed by $SOURCE_ROOT/deploy/sync-to-runtime.sh
DEPLOY_SOURCE_ROOT='$SOURCE_ROOT'
DEPLOY_RUNTIME_ROOT='$RUNTIME_ROOT'
DEPLOY_SOURCE_BRANCH='$SOURCE_BRANCH'
DEPLOY_SOURCE_COMMIT='$SOURCE_COMMIT'
DEPLOY_SOURCE_TREE='$SOURCE_TREE'
DEPLOY_SERVICE_NAME='$SERVICE_NAME'
DEPLOYED_AT_UTC='$(date -u +%Y-%m-%dT%H:%M:%SZ)'
EOF
  mv "$tmp" "$REVISION_FILE"
}

show_service_status() {
  echo "=== service status ==="
  systemctl --user --no-pager status "$SERVICE_NAME" || true
}

show_recent_service_logs() {
  echo "=== recent service logs ==="
  journalctl --user -u "$SERVICE_NAME" -n 50 --no-pager || true
}

wait_for_service_running() {
  local attempt active sub

  for attempt in $(seq 1 "$RESTART_WAIT_SECONDS"); do
    active="$(systemctl --user show -p ActiveState --value "$SERVICE_NAME" 2>/dev/null || true)"
    sub="$(systemctl --user show -p SubState --value "$SERVICE_NAME" 2>/dev/null || true)"
    if [[ "$active" == "active" && "$sub" == "running" ]]; then
      echo "service_state: $active/$sub"
      echo "CHECK_OK: service active"
      return 0
    fi
    sleep 1
  done

  echo "service_state: ${active:-unknown}/${sub:-unknown}"
  show_service_status
  show_recent_service_logs
  fail "service unhealthy after restart"
}

run_checked_step() {
  local label="$1"
  shift

  echo
  echo "=== $label ==="
  if "$@"; then
    echo "CHECK_OK: $label"
    return 0
  else
    local rc=$?
    echo "CHECK_FAIL: $label (rc=$rc)" >&2
    show_service_status
    show_recent_service_logs
    exit "$rc"
  fi
}

usage() {
  cat <<EOF
Usage: $(basename "$0") [--dry-run] [--apply] [--bundle-before-deploy] [--bundle-note NOTE]

Modes:
  --dry-run               Show the rsync plan only (default)
  --apply                 Sync source into runtime, write the revision marker, restart the service, and verify parity

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
require_clean_source_repo
capture_source_revision
read_runtime_revision

if [[ "$MODE" != "apply" && "$BUNDLE_BEFORE_DEPLOY" -eq 1 ]]; then
  fail "--bundle-before-deploy requires --apply"
fi

if [[ "$MODE" == "dry-run" ]]; then
  ACTIVE_MODE_LABEL="dry-run"
  print_sync_context "$MODE"
  echo
  print_source_revision
  echo
  print_runtime_revision
  echo
  echo "=== rsync dry-run ==="
  rsync -avn --delete-delay --itemize-changes \
    --exclude-from="$EXCLUDE_FILE" \
    "$SOURCE_ROOT"/ "$RUNTIME_ROOT"/
  echo
  echo "SYNC_DRY_RUN_OK: $SOURCE_COMMIT"
  exit 0
fi

ACTIVE_MODE_LABEL="apply"
print_sync_context "$MODE"
echo
print_source_revision
echo
print_runtime_revision
require_runtime_preconditions

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
echo "=== write runtime revision marker ==="
write_revision_marker
echo "CHECK_OK: revision marker"

echo
echo "=== restart service ==="
systemctl --user restart "$SERVICE_NAME"
wait_for_service_running

run_checked_step "runtime parity" "$SOURCE_ROOT/deploy/verify-runtime-parity.sh"
run_checked_step "preflight" /home/ai/bin/isla-v2-preflight
run_checked_step "stack-check" /home/ai/bin/isla-check

echo
echo "SYNC_APPLY_OK: $SOURCE_COMMIT"
