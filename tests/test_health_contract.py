import re
from pathlib import Path

from isla_v2.apps.watchdog import watchdog


ISLA_CHECK = Path("/home/ai/bin/isla-check")
ISLA_HEALTHCHECK = Path("/home/ai/bin/isla-healthcheck.sh")


def test_isla_check_tracks_live_runtime_imports_not_legacy_deps():
    text = ISLA_CHECK.read_text(encoding="utf-8")

    required_imports = [
        '"isla_v2.apps.telegram_sidecar.bot"',
        '"isla_v2.core.router.responder"',
        '"isla_v2.core.workflows.runner"',
        '"isla_v2.apps.watchdog.watchdog"',
    ]
    for name in required_imports:
        assert name in text, f"missing required live import check: {name}"

    legacy_hard_requirements = [
        "qdrant_client",
        "sentence_transformers",
        "crewai",
        "ai_memory",
    ]
    for name in legacy_hard_requirements:
        assert name not in text, f"legacy hard requirement still present: {name}"

    assert 'fail "aiwork launcher missing: /home/ai/bin/aiwork"' not in text
    assert 'warn "aiwork launcher missing: /home/ai/bin/aiwork"' in text
    assert 'fail "docker not found in PATH"' in text
    assert 'fail "curl not found in PATH"' in text
    assert 'warn "docker not found in PATH"' not in text
    assert 'warn "curl not found in PATH"' not in text


def test_health_scripts_track_failures_in_exit_status():
    for path in (ISLA_CHECK, ISLA_HEALTHCHECK):
        text = path.read_text(encoding="utf-8")
        assert "FAILED=0" in text, f"{path} missing FAILED sentinel"
        assert 'exit "$FAILED"' in text, f"{path} missing explicit exit status"
        assert re.search(r'fail\(\)\s*\{\s*echo "\[FAIL\] \$1";\s*FAILED=1;\s*\}', text), (
            f"{path} fail() no longer flips FAILED=1"
        )


def test_watchdog_evaluate_ignores_optional_warning_lines(monkeypatch):
    def fake_run_text(cmd, timeout=30):
        if cmd == ["systemctl", "--user", "is-active", "isla-v2-bot.service"]:
            return "active"
        if cmd == ["systemctl", "--user", "status", "isla-crew-bot.service", "--no-pager"]:
            return "Unit isla-crew-bot.service could not be found."
        if cmd == ["/home/ai/bin/isla-crew-check"]:
            return "RETIRED"
        if cmd == ["/home/ai/bin/isla-check"]:
            return "\n".join(
                [
                    "=== ISLA full stack check ===",
                    "[OK]   OpenClaw Gateway is active",
                    "[OK]   Ollama API reachable on 127.0.0.1:11434",
                    "[OK]   Open WebUI API reachable on 127.0.0.1:3000",
                    "[OK]   Qdrant API reachable on 127.0.0.1:6333",
                    "[WARN] Optional legacy AI libraries are not part of the live health contract",
                    "=== Done ===",
                ]
            )
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(watchdog, "run_text", fake_run_text)

    report = watchdog.evaluate()

    assert report["issues"] == []
    assert report["snapshot"]["gateway"] == "OK"
    assert report["snapshot"]["ollama"] == "OK"
    assert report["snapshot"]["webui"] == "OK"
    assert report["snapshot"]["qdrant"] == "OK"
