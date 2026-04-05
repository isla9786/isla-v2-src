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
SOURCE_BRANCH=""
SOURCE_COMMIT=""
SOURCE_TREE=""
RUNTIME_REVISION_SOURCE="missing"
RUNTIME_BRANCH=""
RUNTIME_COMMIT=""
RUNTIME_TREE=""
RUNTIME_DEPLOYED_AT_UTC=""
SERVICE_FRAGMENT_PATH=""
SERVICE_WORKING_DIRECTORY_LINE=""
SERVICE_EXEC_START_LINE=""
SERVICE_ACTIVE_STATE=""
SERVICE_SUB_STATE=""
PARITY_DIFF=""
declare -a ISSUES=()

fail() {
  echo
  echo "PARITY_FAIL: $1" >&2
  exit 1
}

usage() {
  cat <<EOF
Usage: $(basename "$0")

Checks whether source-controlled files in:
  $SOURCE_ROOT
match the live runtime tree at:
  $RUNTIME_ROOT

The comparison respects:
  $EXCLUDE_FILE

The runtime revision is read from:
  $REVISION_FILE
EOF
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
    fail "source git tree is dirty; commit or stash changes before verification"
  fi
}

capture_source_revision() {
  SOURCE_BRANCH="$(git -C "$SOURCE_ROOT" rev-parse --abbrev-ref HEAD)"
  SOURCE_COMMIT="$(git -C "$SOURCE_ROOT" rev-parse HEAD)"
  SOURCE_TREE="$(git -C "$SOURCE_ROOT" rev-parse HEAD^{tree})"
}

read_runtime_revision() {
  RUNTIME_REVISION_SOURCE="missing"
  RUNTIME_BRANCH=""
  RUNTIME_COMMIT=""
  RUNTIME_TREE=""
  RUNTIME_DEPLOYED_AT_UTC=""

  if [[ -f "$REVISION_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$REVISION_FILE"
    RUNTIME_REVISION_SOURCE="marker"
    RUNTIME_BRANCH="${DEPLOY_SOURCE_BRANCH:-}"
    RUNTIME_COMMIT="${DEPLOY_SOURCE_COMMIT:-}"
    RUNTIME_TREE="${DEPLOY_SOURCE_TREE:-}"
    RUNTIME_DEPLOYED_AT_UTC="${DEPLOYED_AT_UTC:-}"
    return 0
  fi

  if git -C "$RUNTIME_ROOT" rev-parse --show-toplevel >/dev/null 2>&1; then
    RUNTIME_REVISION_SOURCE="git"
    RUNTIME_BRANCH="$(git -C "$RUNTIME_ROOT" rev-parse --abbrev-ref HEAD)"
    RUNTIME_COMMIT="$(git -C "$RUNTIME_ROOT" rev-parse HEAD)"
    RUNTIME_TREE="$(git -C "$RUNTIME_ROOT" rev-parse HEAD^{tree})"
    RUNTIME_DEPLOYED_AT_UTC="git-checkout"
  fi
}

read_service_state() {
  local service_unit

  SERVICE_FRAGMENT_PATH="$(systemctl --user show -p FragmentPath --value "$SERVICE_NAME" 2>/dev/null || true)"
  SERVICE_ACTIVE_STATE="$(systemctl --user show -p ActiveState --value "$SERVICE_NAME" 2>/dev/null || true)"
  SERVICE_SUB_STATE="$(systemctl --user show -p SubState --value "$SERVICE_NAME" 2>/dev/null || true)"

  service_unit="$(systemctl --user cat "$SERVICE_NAME" 2>&1 || true)"
  SERVICE_WORKING_DIRECTORY_LINE="$(printf '%s\n' "$service_unit" | grep -F 'WorkingDirectory=' | tail -1 || true)"
  SERVICE_EXEC_START_LINE="$(printf '%s\n' "$service_unit" | grep -F 'ExecStart=' | tail -1 || true)"
}

record_issue() {
  ISSUES+=("$1")
}

print_source_revision() {
  echo "=== source revision ==="
  echo "source_branch: $SOURCE_BRANCH"
  echo "source_commit: $SOURCE_COMMIT"
  echo "source_tree: $SOURCE_TREE"
}

print_runtime_revision() {
  echo "=== runtime revision ==="
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

print_service_state() {
  local binding="no"

  if [[ "$SERVICE_WORKING_DIRECTORY_LINE" == "WorkingDirectory=$RUNTIME_ROOT" ]] && [[ "$SERVICE_EXEC_START_LINE" == "ExecStart=$RUNTIME_PYTHON -m $SERVICE_MODULE" ]]; then
    binding="yes"
  fi

  echo "=== service target ==="
  echo "service: $SERVICE_NAME"
  echo "fragment_path: ${SERVICE_FRAGMENT_PATH:-unknown}"
  echo "working_directory_line: ${SERVICE_WORKING_DIRECTORY_LINE:-missing}"
  echo "exec_start_line: ${SERVICE_EXEC_START_LINE:-missing}"
  echo "service_binding_match: $binding"
  echo "service_state: ${SERVICE_ACTIVE_STATE:-unknown}/${SERVICE_SUB_STATE:-unknown}"
}

show_service_status() {
  echo "=== service status ==="
  systemctl --user --no-pager status "$SERVICE_NAME" || true
}

show_recent_service_logs() {
  echo "=== recent service logs ==="
  journalctl --user -u "$SERVICE_NAME" -n 50 --no-pager || true
}

if [[ $# -gt 0 ]]; then
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
fi

[[ -d "$SOURCE_ROOT" ]] || fail "source root missing: $SOURCE_ROOT"
[[ -d "$RUNTIME_ROOT" ]] || fail "runtime root missing: $RUNTIME_ROOT"
[[ -f "$EXCLUDE_FILE" ]] || fail "exclude file missing: $EXCLUDE_FILE"
[[ "$SOURCE_ROOT" != "$RUNTIME_ROOT" ]] || fail "source and runtime roots must differ"
require_source_repo_invocation
require_clean_source_repo
capture_source_revision
read_runtime_revision
read_service_state

echo "=== parity config ==="
echo "source: $SOURCE_ROOT"
echo "runtime: $RUNTIME_ROOT"
echo "exclude: $EXCLUDE_FILE"
echo "revision_file: $REVISION_FILE"
echo "service: $SERVICE_NAME"
echo
print_source_revision
echo
print_runtime_revision
echo
print_service_state

[[ -x "$RUNTIME_PYTHON" ]] || record_issue "runtime venv python missing: $RUNTIME_PYTHON"

if [[ "$RUNTIME_REVISION_SOURCE" == "missing" ]]; then
  record_issue "runtime revision marker missing and runtime is not a usable git checkout"
fi

if [[ -n "$RUNTIME_COMMIT" && "$RUNTIME_COMMIT" != "$SOURCE_COMMIT" ]]; then
  record_issue "runtime commit does not match source commit"
fi

if [[ -n "$RUNTIME_TREE" && "$RUNTIME_TREE" != "$SOURCE_TREE" ]]; then
  record_issue "runtime tree does not match source tree"
fi

if [[ "$SERVICE_WORKING_DIRECTORY_LINE" != "WorkingDirectory=$RUNTIME_ROOT" ]]; then
  record_issue "service WorkingDirectory is not pinned to runtime root"
fi

if [[ "$SERVICE_EXEC_START_LINE" != "ExecStart=$RUNTIME_PYTHON -m $SERVICE_MODULE" ]]; then
  record_issue "service ExecStart is not pinned to runtime venv/module"
fi

if [[ "$SERVICE_ACTIVE_STATE" != "active" || "$SERVICE_SUB_STATE" != "running" ]]; then
  record_issue "service is not active/running"
fi

PARITY_DIFF="$(
  rsync -rcn --delete-delay --itemize-changes \
    --exclude-from="$EXCLUDE_FILE" \
    "$SOURCE_ROOT"/ "$RUNTIME_ROOT"/
)"

if [[ -n "$PARITY_DIFF" ]]; then
  echo
  echo "=== parity diff ==="
  printf '%s\n' "$PARITY_DIFF"
  record_issue "source-controlled files differ between source and runtime"
fi

if [[ ${#ISSUES[@]} -gt 0 ]]; then
  echo
  echo "=== parity issues ==="
  printf ' - %s\n' "${ISSUES[@]}"
  if [[ "$SERVICE_ACTIVE_STATE" != "active" || "$SERVICE_SUB_STATE" != "running" ]]; then
    echo
    show_service_status
    echo
    show_recent_service_logs
  fi
  fail "runtime parity verification failed"
fi

echo
echo "PARITY_PASS: source commit $SOURCE_COMMIT matches runtime revision and source-controlled files; service is active/running"
