#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CURRENT_DIR="$(pwd -P)"
RUNTIME_ROOT="${ISLA_V2_RUNTIME_ROOT:-/home/ai/ai-agents}"
EXCLUDE_FILE="$SOURCE_ROOT/deploy/runtime-sync.exclude"

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

echo "=== parity config ==="
echo "source: $SOURCE_ROOT"
echo "runtime: $RUNTIME_ROOT"
echo "exclude: $EXCLUDE_FILE"

PARITY_DIFF="$(
  rsync -rcn --delete-delay --itemize-changes \
    --exclude-from="$EXCLUDE_FILE" \
    "$SOURCE_ROOT"/ "$RUNTIME_ROOT"/
)"

if [[ -n "$PARITY_DIFF" ]]; then
  echo
  echo "=== parity diff ==="
  printf '%s\n' "$PARITY_DIFF"
  echo
  fail "source and runtime differ for source-controlled files"
fi

echo
echo "PARITY_PASS: source and runtime match for source-controlled files"
