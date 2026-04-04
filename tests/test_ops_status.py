from isla_v2.core.tools import ops_actions, ops_status


def test_status_webui_formats_container_and_api(monkeypatch):
    monkeypatch.setattr(
        ops_status,
        "run_command",
        lambda cmd: "open-webui\tUp 5 hours (healthy)",
    )
    monkeypatch.setattr(
        ops_status,
        "run_shell",
        lambda script: '{"version":"0.8.10"}',
    )

    result = ops_status.status_webui()
    assert result.startswith("ISLA ops webui status")
    assert "open-webui" in result
    assert '"version":"0.8.10"' in result


def test_gateway_and_watchdog_ops_use_status_layer(monkeypatch):
    monkeypatch.setattr(ops_actions, "get_status", lambda target: f"STATUS:{target}")
    monkeypatch.setattr(ops_actions, "get_logs", lambda target: f"LOGS:{target}")

    assert ops_actions.maybe_run_action("gateway status", user_id=1) == "STATUS:gateway"
    assert ops_actions.maybe_run_action("gateway logs", user_id=1) == "LOGS:gateway"
    assert ops_actions.maybe_run_action("watchdog status", user_id=1) == "STATUS:watchdog"
    assert ops_actions.maybe_run_action("golden status", user_id=1) == "STATUS:golden"
