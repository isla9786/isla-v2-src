from pathlib import Path
import subprocess


ROOT = Path("/home/ai/ai-agents-src")
GITIGNORE_FILE = ROOT / ".gitignore"
EXCLUDE_FILE = ROOT / "deploy" / "runtime-sync.exclude"
SCRIPT_FILE = ROOT / "deploy" / "sync-to-runtime.sh"
PARITY_SCRIPT_FILE = ROOT / "deploy" / "verify-runtime-parity.sh"
RELEASE_GATE_FILE = ROOT / "scripts" / "release_gate.py"
MAKEFILE = ROOT / "Makefile"


def test_deploy_exclude_contains_runtime_only_paths():
    body = EXCLUDE_FILE.read_text()
    expected_lines = [
        "venv2026/",
        "downloads/",
        "reports/",
        "secrets/",
        "isla_v2/secrets/",
        "isla_v2/data/facts.db",
        "isla_v2/data/notes.db",
        "isla_v2/data/ops-audit.log",
        "isla_v2/data/events/procedure_runs/",
        "deploy/runtime-revision.env",
    ]
    for line in expected_lines:
        assert line in body


def test_gitignore_covers_runtime_git_only_paths():
    body = GITIGNORE_FILE.read_text()
    for line in ["reports/", "deploy/runtime-revision.env", "downloads/", "venv2026/"]:
        assert line in body


def test_deploy_script_uses_checked_in_exclude_and_two_root_defaults():
    body = SCRIPT_FILE.read_text()
    assert 'CURRENT_DIR="$(pwd -P)"' in body
    assert 'run this helper from $SOURCE_ROOT or a subdirectory' in body
    assert 'EXCLUDE_FILE="$SOURCE_ROOT/deploy/runtime-sync.exclude"' in body
    assert 'RUNTIME_ROOT="${ISLA_V2_RUNTIME_ROOT:-/home/ai/ai-agents}"' in body
    assert 'SERVICE_NAME="${ISLA_V2_SERVICE_NAME:-isla-v2-bot.service}"' in body
    assert 'REVISION_FILE_REL="deploy/runtime-revision.env"' in body
    assert 'print_sync_context "$MODE"' in body
    assert 'source git tree is dirty; commit or stash changes before deploying' in body
    assert 'SYNC_DRY_RUN_OK' in body
    assert 'SYNC_FAIL:' in body
    assert '=== release gate ===' in body
    assert 'exec "$RUNTIME_PYTHON" "$SOURCE_ROOT/scripts/release_gate.py"' in body


def test_release_entry_points_use_explicit_runtime_python():
    makefile = MAKEFILE.read_text()
    release_gate = RELEASE_GATE_FILE.read_text()

    assert 'PYTHON := /home/ai/ai-agents/venv2026/bin/python' in makefile
    assert 'release:' in makefile
    assert '$(PYTHON) scripts/release_gate.py' in makefile
    assert 'DEFAULT_SOURCE_ROOT = Path("/home/ai/ai-agents-src")' in release_gate
    assert 'DEFAULT_RUNTIME_ROOT = Path("/home/ai/ai-agents")' in release_gate
    assert 'DEFAULT_PYTHON_BIN = Path("/home/ai/ai-agents/venv2026/bin/python")' in release_gate
    assert 'DEFAULT_SERVICE_NAME = "isla-v2-bot.service"' in release_gate


def test_runtime_revision_helpers_prefer_git_identity_before_marker():
    sync_body = SCRIPT_FILE.read_text()
    parity_body = PARITY_SCRIPT_FILE.read_text()

    sync_git = 'if git -C "$RUNTIME_ROOT" rev-parse --show-toplevel >/dev/null 2>&1; then'
    sync_marker = 'if [[ -f "$REVISION_FILE" ]]; then'
    parity_git = 'if git -C "$RUNTIME_ROOT" rev-parse --show-toplevel >/dev/null 2>&1; then'
    parity_marker = 'if [[ -f "$REVISION_FILE" ]]; then'

    assert sync_body.index(sync_git) < sync_body.index(sync_marker)
    assert parity_body.index(parity_git) < parity_body.index(parity_marker)


def test_deploy_script_refuses_invocation_outside_source_repo():
    result = subprocess.run(
        ["bash", "-lc", "cd /home/ai && /home/ai/ai-agents-src/deploy/sync-to-runtime.sh --dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "SYNC_FAIL: run this helper from /home/ai/ai-agents-src or a subdirectory" in combined


def test_parity_script_uses_checked_in_exclude_and_pass_fail_output():
    body = PARITY_SCRIPT_FILE.read_text()
    assert 'CURRENT_DIR="$(pwd -P)"' in body
    assert 'EXCLUDE_FILE="$SOURCE_ROOT/deploy/runtime-sync.exclude"' in body
    assert 'SERVICE_NAME="${ISLA_V2_SERVICE_NAME:-isla-v2-bot.service}"' in body
    assert 'REVISION_FILE_REL="deploy/runtime-revision.env"' in body
    assert 'run this helper from $SOURCE_ROOT or a subdirectory' in body
    assert '=== parity config ===' in body
    assert '=== source revision ===' in body
    assert '=== runtime revision ===' in body
    assert '=== service target ===' in body
    assert 'service_binding_match:' in body
    assert '=== parity diff ===' in body
    assert 'source git tree is dirty; commit or stash changes before verification' in body
    assert 'journalctl --user -u "$SERVICE_NAME" -n 50 --no-pager' in body
    assert 'PARITY_PASS: source commit $SOURCE_COMMIT matches runtime revision and source-controlled files; service is active/running' in body
    assert 'PARITY_FAIL:' in body
    assert 'rsync -rcn --delete-delay --itemize-changes' in body


def test_parity_script_refuses_invocation_outside_source_repo():
    result = subprocess.run(
        ["bash", "-lc", "cd /home/ai && /home/ai/ai-agents-src/deploy/verify-runtime-parity.sh"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "PARITY_FAIL: run this helper from /home/ai/ai-agents-src or a subdirectory" in combined
