import os
from pathlib import Path

from isla_v2.core.tools import ops_actions
from isla_v2.core.workflows import runner
from isla_v2.core.workflows.procedures import ProcedureSpec


def configure_runner_paths(monkeypatch, tmp_path: Path):
    history = tmp_path / "events" / "procedure_history.jsonl"
    locks = tmp_path / "procedures" / "locks"
    runs = tmp_path / "events" / "procedure_runs"

    monkeypatch.setattr(runner, "PROCEDURE_HISTORY_FILE", history)
    monkeypatch.setattr(runner, "PROCEDURE_LOCKS_DIR", locks)
    monkeypatch.setattr(runner, "PROCEDURE_RUNS_DIR", runs)
    monkeypatch.setattr(
        runner,
        "ensure_dirs",
        lambda: (locks.mkdir(parents=True, exist_ok=True), runs.mkdir(parents=True, exist_ok=True), history.parent.mkdir(parents=True, exist_ok=True)),
    )


def test_list_procedures_text_contains_allowlisted_items():
    body = runner.list_procedures_text()
    assert body.startswith("ISLA procedures")
    assert "preflight" in body
    assert "health_snapshot" in body


def test_run_procedure_unknown_returns_deterministic_error():
    assert runner.run_procedure("not_real") == "PROCEDURE_UNKNOWN: not_real"


def test_run_procedure_writes_history(monkeypatch, tmp_path: Path):
    configure_runner_paths(monkeypatch, tmp_path)

    monkeypatch.setattr(
        runner,
        "get_procedure",
        lambda name: ProcedureSpec(
            name="demo",
            description="demo",
            timeout_seconds=5,
            handler=lambda: "DEMO_OK",
        ),
    )

    result = runner.run_procedure("demo")
    assert "status: OK" in result
    assert runner.PROCEDURE_HISTORY_FILE.exists()
    assert "demo" in runner.PROCEDURE_HISTORY_FILE.read_text(encoding="utf-8")


def test_run_procedure_blocks_duplicate(monkeypatch, tmp_path: Path):
    configure_runner_paths(monkeypatch, tmp_path)

    monkeypatch.setattr(
        runner,
        "get_procedure",
        lambda name: ProcedureSpec(
            name="demo",
            description="demo",
            timeout_seconds=5,
            handler=lambda: "DEMO_OK",
        ),
    )

    lock = runner.lock_path("demo")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text('{"pid": %d}' % os.getpid(), encoding="utf-8")

    result = runner.run_procedure("demo")
    assert result == "PROCEDURE_ALREADY_RUNNING: demo"


def test_procedure_ops_commands_route_to_runner(monkeypatch):
    monkeypatch.setattr(ops_actions, "list_procedures_text", lambda: "PROCEDURE_LIST")
    monkeypatch.setattr(ops_actions, "procedure_history_text", lambda: "PROCEDURE_HISTORY")
    monkeypatch.setattr(ops_actions, "run_procedure", lambda name: f"RUN:{name}")

    assert ops_actions.maybe_run_action("procedures", user_id=1) == "PROCEDURE_LIST"
    assert ops_actions.maybe_run_action("procedure history", user_id=1) == "PROCEDURE_HISTORY"
    assert ops_actions.maybe_run_action("procedure run health snapshot", user_id=1) == "RUN:health snapshot"
