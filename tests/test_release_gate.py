from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from scripts import release_gate


SOURCE_HEAD = "1111111111111111111111111111111111111111"
PREVIOUS_RUNTIME_HEAD = "2222222222222222222222222222222222222222"
OTHER_HEAD = "3333333333333333333333333333333333333333"


@dataclass(frozen=True)
class ExpectedCall:
    cwd: Path | None
    command: tuple[str, ...]
    result: subprocess.CompletedProcess[str]


class FakeRunner:
    def __init__(self, expected_calls: list[ExpectedCall]) -> None:
        self.expected_calls = list(expected_calls)
        self.calls: list[tuple[Path | None, tuple[str, ...]]] = []

    def __call__(self, command, cwd):
        actual = (cwd, tuple(command))
        self.calls.append(actual)

        if not self.expected_calls:
            raise AssertionError(f"unexpected command: {actual}")

        expected = self.expected_calls.pop(0)
        assert actual == (expected.cwd, expected.command)
        return expected.result


def completed(command: tuple[str, ...], *, rc: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(command, rc, stdout=stdout, stderr=stderr)


def gate_config(tmp_path: Path) -> release_gate.ReleaseConfig:
    source_root = tmp_path / "source"
    runtime_root = tmp_path / "runtime"
    python_bin = tmp_path / "venv2026" / "bin" / "python"

    source_root.mkdir(parents=True)
    runtime_root.mkdir(parents=True)
    python_bin.parent.mkdir(parents=True)
    python_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    python_bin.chmod(0o755)

    return release_gate.ReleaseConfig(
        source_root=source_root,
        runtime_root=runtime_root,
        python_bin=python_bin,
        service_name="isla-v2-bot.service",
    )


def preflight_calls(config: release_gate.ReleaseConfig) -> list[ExpectedCall]:
    python = str(config.python_bin)
    return [
        ExpectedCall(
            cwd=config.source_root,
            command=("git", "rev-parse", "--show-toplevel"),
            result=completed(("git", "rev-parse", "--show-toplevel"), stdout=f"{config.source_root}\n"),
        ),
        ExpectedCall(
            cwd=config.runtime_root,
            command=("git", "rev-parse", "--show-toplevel"),
            result=completed(("git", "rev-parse", "--show-toplevel"), stdout=f"{config.runtime_root}\n"),
        ),
        ExpectedCall(
            cwd=config.source_root,
            command=("git", "status", "--short", "--untracked-files=all"),
            result=completed(("git", "status", "--short", "--untracked-files=all")),
        ),
        ExpectedCall(
            cwd=config.runtime_root,
            command=("git", "status", "--short", "--untracked-files=all"),
            result=completed(("git", "status", "--short", "--untracked-files=all")),
        ),
        ExpectedCall(
            cwd=config.source_root,
            command=("git", "rev-parse", "--abbrev-ref", "HEAD"),
            result=completed(("git", "rev-parse", "--abbrev-ref", "HEAD"), stdout="main\n"),
        ),
        ExpectedCall(
            cwd=config.source_root,
            command=("git", "fetch", "--quiet", "origin", "main"),
            result=completed(("git", "fetch", "--quiet", "origin", "main")),
        ),
        ExpectedCall(
            cwd=config.source_root,
            command=("git", "rev-parse", "HEAD"),
            result=completed(("git", "rev-parse", "HEAD"), stdout=f"{SOURCE_HEAD}\n"),
        ),
        ExpectedCall(
            cwd=config.source_root,
            command=("git", "rev-parse", "origin/main"),
            result=completed(("git", "rev-parse", "origin/main"), stdout=f"{SOURCE_HEAD}\n"),
        ),
        ExpectedCall(
            cwd=config.source_root,
            command=(python, "-m", "compileall", "-q", "isla_v2", "tests"),
            result=completed((python, "-m", "compileall", "-q", "isla_v2", "tests")),
        ),
        ExpectedCall(
            cwd=config.source_root,
            command=("git", "rev-parse", "HEAD"),
            result=completed(("git", "rev-parse", "HEAD"), stdout=f"{SOURCE_HEAD}\n"),
        ),
    ]


def runtime_success_calls(config: release_gate.ReleaseConfig) -> list[ExpectedCall]:
    python = str(config.python_bin)
    return [
        ExpectedCall(
            cwd=config.runtime_root,
            command=("git", "rev-parse", "HEAD"),
            result=completed(("git", "rev-parse", "HEAD"), stdout=f"{PREVIOUS_RUNTIME_HEAD}\n"),
        ),
        ExpectedCall(
            cwd=config.runtime_root,
            command=("git", "fetch", "--quiet", str(config.source_root), "main"),
            result=completed(("git", "fetch", "--quiet", str(config.source_root), "main")),
        ),
        ExpectedCall(
            cwd=config.runtime_root,
            command=("git", "checkout", "--force", "--detach", SOURCE_HEAD),
            result=completed(("git", "checkout", "--force", "--detach", SOURCE_HEAD)),
        ),
        ExpectedCall(
            cwd=config.runtime_root,
            command=("git", "rev-parse", "HEAD"),
            result=completed(("git", "rev-parse", "HEAD"), stdout=f"{SOURCE_HEAD}\n"),
        ),
        ExpectedCall(
            cwd=config.runtime_root,
            command=("git", "status", "--short", "--untracked-files=all"),
            result=completed(("git", "status", "--short", "--untracked-files=all")),
        ),
        ExpectedCall(
            cwd=config.runtime_root,
            command=(python, "-m", "pytest", "-q"),
            result=completed((python, "-m", "pytest", "-q")),
        ),
        ExpectedCall(
            cwd=None,
            command=("systemctl", "--user", "restart", config.service_name),
            result=completed(("systemctl", "--user", "restart", config.service_name)),
        ),
        ExpectedCall(
            cwd=None,
            command=("systemctl", "--user", "is-active", config.service_name),
            result=completed(("systemctl", "--user", "is-active", config.service_name), stdout="active\n"),
        ),
    ]


def rollback_calls(config: release_gate.ReleaseConfig) -> list[ExpectedCall]:
    return [
        ExpectedCall(
            cwd=config.runtime_root,
            command=("git", "checkout", "--force", "--detach", PREVIOUS_RUNTIME_HEAD),
            result=completed(("git", "checkout", "--force", "--detach", PREVIOUS_RUNTIME_HEAD)),
        ),
        ExpectedCall(
            cwd=None,
            command=("systemctl", "--user", "restart", config.service_name),
            result=completed(("systemctl", "--user", "restart", config.service_name)),
        ),
        ExpectedCall(
            cwd=None,
            command=("systemctl", "--user", "is-active", config.service_name),
            result=completed(("systemctl", "--user", "is-active", config.service_name), stdout="active\n"),
        ),
    ]


def test_preflight_failure_exits_before_any_runtime_mutation(tmp_path):
    config = gate_config(tmp_path)
    runner = FakeRunner(
        [
            ExpectedCall(
                cwd=config.source_root,
                command=("git", "rev-parse", "--show-toplevel"),
                result=completed(("git", "rev-parse", "--show-toplevel"), stdout=f"{config.source_root}\n"),
            ),
            ExpectedCall(
                cwd=config.runtime_root,
                command=("git", "rev-parse", "--show-toplevel"),
                result=completed(("git", "rev-parse", "--show-toplevel"), stdout=f"{config.runtime_root}\n"),
            ),
            ExpectedCall(
                cwd=config.source_root,
                command=("git", "status", "--short", "--untracked-files=all"),
                result=completed(
                    ("git", "status", "--short", "--untracked-files=all"),
                    stdout=" M isla_v2/core/router/responder.py\n",
                ),
            ),
        ]
    )

    rc = release_gate.ReleaseGate(config, runner=runner).run()

    assert rc == 1
    assert not any(command[0:2] == ("git", "checkout") for _, command in runner.calls)
    assert not any(command[0:2] == ("systemctl", "--user") for _, command in runner.calls)
    assert not runner.expected_calls


def test_source_test_failure_exits_before_any_runtime_mutation(tmp_path):
    config = gate_config(tmp_path)
    python = str(config.python_bin)
    runner = FakeRunner(
        preflight_calls(config)
        + [
            ExpectedCall(
                cwd=config.source_root,
                command=(python, "-m", "pytest", "-q"),
                result=completed((python, "-m", "pytest", "-q"), rc=1, stdout="F\n", stderr="tests failed\n"),
            )
        ]
    )

    rc = release_gate.ReleaseGate(config, runner=runner).run()

    assert rc == 1
    assert not any(command[0:2] == ("git", "checkout") for _, command in runner.calls)
    assert not any(command[0:2] == ("systemctl", "--user") for _, command in runner.calls)
    assert not runner.expected_calls


def test_successful_release_runs_deploy_runtime_validation_and_service_restart(tmp_path):
    config = gate_config(tmp_path)
    python = str(config.python_bin)
    runner = FakeRunner(
        preflight_calls(config)
        + [
            ExpectedCall(
                cwd=config.source_root,
                command=(python, "-m", "pytest", "-q"),
                result=completed((python, "-m", "pytest", "-q")),
            )
        ]
        + runtime_success_calls(config)
    )

    rc = release_gate.ReleaseGate(config, runner=runner).run()

    assert rc == 0
    assert not runner.expected_calls


def test_runtime_test_failure_triggers_rollback_to_previous_runtime_head(tmp_path):
    config = gate_config(tmp_path)
    python = str(config.python_bin)
    runner = FakeRunner(
        preflight_calls(config)
        + [
            ExpectedCall(
                cwd=config.source_root,
                command=(python, "-m", "pytest", "-q"),
                result=completed((python, "-m", "pytest", "-q")),
            ),
            ExpectedCall(
                cwd=config.runtime_root,
                command=("git", "rev-parse", "HEAD"),
                result=completed(("git", "rev-parse", "HEAD"), stdout=f"{PREVIOUS_RUNTIME_HEAD}\n"),
            ),
            ExpectedCall(
                cwd=config.runtime_root,
                command=("git", "fetch", "--quiet", str(config.source_root), "main"),
                result=completed(("git", "fetch", "--quiet", str(config.source_root), "main")),
            ),
            ExpectedCall(
                cwd=config.runtime_root,
                command=("git", "checkout", "--force", "--detach", SOURCE_HEAD),
                result=completed(("git", "checkout", "--force", "--detach", SOURCE_HEAD)),
            ),
            ExpectedCall(
                cwd=config.runtime_root,
                command=("git", "rev-parse", "HEAD"),
                result=completed(("git", "rev-parse", "HEAD"), stdout=f"{SOURCE_HEAD}\n"),
            ),
            ExpectedCall(
                cwd=config.runtime_root,
                command=("git", "status", "--short", "--untracked-files=all"),
                result=completed(("git", "status", "--short", "--untracked-files=all")),
            ),
            ExpectedCall(
                cwd=config.runtime_root,
                command=(python, "-m", "pytest", "-q"),
                result=completed((python, "-m", "pytest", "-q"), rc=1, stdout="F\n", stderr="runtime tests failed\n"),
            ),
        ]
        + rollback_calls(config)
    )

    rc = release_gate.ReleaseGate(config, runner=runner).run()

    assert rc == 1
    assert ("git", "checkout", "--force", "--detach", PREVIOUS_RUNTIME_HEAD) in [command for _, command in runner.calls]
    assert not runner.expected_calls


def test_runtime_head_mismatch_triggers_rollback_to_previous_runtime_head(tmp_path):
    config = gate_config(tmp_path)
    python = str(config.python_bin)
    runner = FakeRunner(
        preflight_calls(config)
        + [
            ExpectedCall(
                cwd=config.source_root,
                command=(python, "-m", "pytest", "-q"),
                result=completed((python, "-m", "pytest", "-q")),
            ),
            ExpectedCall(
                cwd=config.runtime_root,
                command=("git", "rev-parse", "HEAD"),
                result=completed(("git", "rev-parse", "HEAD"), stdout=f"{PREVIOUS_RUNTIME_HEAD}\n"),
            ),
            ExpectedCall(
                cwd=config.runtime_root,
                command=("git", "fetch", "--quiet", str(config.source_root), "main"),
                result=completed(("git", "fetch", "--quiet", str(config.source_root), "main")),
            ),
            ExpectedCall(
                cwd=config.runtime_root,
                command=("git", "checkout", "--force", "--detach", SOURCE_HEAD),
                result=completed(("git", "checkout", "--force", "--detach", SOURCE_HEAD)),
            ),
            ExpectedCall(
                cwd=config.runtime_root,
                command=("git", "rev-parse", "HEAD"),
                result=completed(("git", "rev-parse", "HEAD"), stdout=f"{OTHER_HEAD}\n"),
            ),
        ]
        + rollback_calls(config)
    )

    rc = release_gate.ReleaseGate(config, runner=runner).run()

    assert rc == 1
    assert ("git", "checkout", "--force", "--detach", PREVIOUS_RUNTIME_HEAD) in [command for _, command in runner.calls]
    assert not runner.expected_calls


def test_service_restart_failure_triggers_rollback_to_previous_runtime_head(tmp_path):
    config = gate_config(tmp_path)
    python = str(config.python_bin)
    runner = FakeRunner(
        preflight_calls(config)
        + [
            ExpectedCall(
                cwd=config.source_root,
                command=(python, "-m", "pytest", "-q"),
                result=completed((python, "-m", "pytest", "-q")),
            ),
            ExpectedCall(
                cwd=config.runtime_root,
                command=("git", "rev-parse", "HEAD"),
                result=completed(("git", "rev-parse", "HEAD"), stdout=f"{PREVIOUS_RUNTIME_HEAD}\n"),
            ),
            ExpectedCall(
                cwd=config.runtime_root,
                command=("git", "fetch", "--quiet", str(config.source_root), "main"),
                result=completed(("git", "fetch", "--quiet", str(config.source_root), "main")),
            ),
            ExpectedCall(
                cwd=config.runtime_root,
                command=("git", "checkout", "--force", "--detach", SOURCE_HEAD),
                result=completed(("git", "checkout", "--force", "--detach", SOURCE_HEAD)),
            ),
            ExpectedCall(
                cwd=config.runtime_root,
                command=("git", "rev-parse", "HEAD"),
                result=completed(("git", "rev-parse", "HEAD"), stdout=f"{SOURCE_HEAD}\n"),
            ),
            ExpectedCall(
                cwd=config.runtime_root,
                command=("git", "status", "--short", "--untracked-files=all"),
                result=completed(("git", "status", "--short", "--untracked-files=all")),
            ),
            ExpectedCall(
                cwd=config.runtime_root,
                command=(python, "-m", "pytest", "-q"),
                result=completed((python, "-m", "pytest", "-q")),
            ),
            ExpectedCall(
                cwd=None,
                command=("systemctl", "--user", "restart", config.service_name),
                result=completed(
                    ("systemctl", "--user", "restart", config.service_name),
                    rc=1,
                    stderr="restart failed\n",
                ),
            ),
        ]
        + rollback_calls(config)
    )

    rc = release_gate.ReleaseGate(config, runner=runner).run()

    assert rc == 1
    assert ("git", "checkout", "--force", "--detach", PREVIOUS_RUNTIME_HEAD) in [command for _, command in runner.calls]
    assert not runner.expected_calls


def test_source_head_mismatch_with_origin_main_fails_before_deploy(tmp_path):
    config = gate_config(tmp_path)
    runner = FakeRunner(
        preflight_calls(config)[:6]
        + [
            ExpectedCall(
                cwd=config.source_root,
                command=("git", "rev-parse", "HEAD"),
                result=completed(("git", "rev-parse", "HEAD"), stdout=f"{SOURCE_HEAD}\n"),
            ),
            ExpectedCall(
                cwd=config.source_root,
                command=("git", "rev-parse", "origin/main"),
                result=completed(("git", "rev-parse", "origin/main"), stdout=f"{OTHER_HEAD}\n"),
            ),
        ]
    )

    rc = release_gate.ReleaseGate(config, runner=runner).run()

    assert rc == 1
    assert not any(command[0:2] == ("git", "checkout") for _, command in runner.calls)
    assert not any(command[0:2] == ("systemctl", "--user") for _, command in runner.calls)
    assert not runner.expected_calls
