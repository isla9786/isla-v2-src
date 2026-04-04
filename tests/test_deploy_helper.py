from pathlib import Path
import subprocess


ROOT = Path("/home/ai/ai-agents-src")
EXCLUDE_FILE = ROOT / "deploy" / "runtime-sync.exclude"
SCRIPT_FILE = ROOT / "deploy" / "sync-to-runtime.sh"


def test_deploy_exclude_contains_runtime_only_paths():
    body = EXCLUDE_FILE.read_text()
    expected_lines = [
        "venv2026/",
        "downloads/",
        "secrets/",
        "isla_v2/secrets/",
        "isla_v2/data/facts.db",
        "isla_v2/data/notes.db",
        "isla_v2/data/ops-audit.log",
        "isla_v2/data/events/procedure_runs/",
    ]
    for line in expected_lines:
        assert line in body


def test_deploy_script_uses_checked_in_exclude_and_two_root_defaults():
    body = SCRIPT_FILE.read_text()
    assert 'CURRENT_DIR="$(pwd -P)"' in body
    assert 'run this helper from $SOURCE_ROOT or a subdirectory' in body
    assert 'EXCLUDE_FILE="$SOURCE_ROOT/deploy/runtime-sync.exclude"' in body
    assert 'RUNTIME_ROOT="${ISLA_V2_RUNTIME_ROOT:-/home/ai/ai-agents}"' in body
    assert 'print_sync_context "$MODE"' in body
    assert 'CHECK_OK: preflight' in body
    assert 'CHECK_OK: stack-check' in body
    assert 'SYNC_DRY_RUN_OK' in body
    assert 'SYNC_APPLY_OK' in body
    assert 'SYNC_FAIL:' in body
    assert '/home/ai/bin/isla-v2-preflight' in body
    assert '/home/ai/bin/isla-check' in body


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
