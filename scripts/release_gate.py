#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


DEFAULT_SOURCE_ROOT = Path("/home/ai/ai-agents-src")
DEFAULT_RUNTIME_ROOT = Path("/home/ai/ai-agents")
DEFAULT_PYTHON_BIN = Path("/home/ai/ai-agents/venv2026/bin/python")
DEFAULT_SERVICE_NAME = "isla-v2-bot.service"

Runner = Callable[[Sequence[str], Path | None], subprocess.CompletedProcess[str]]


class ReleaseGateError(RuntimeError):
    """Raised when the release gate must fail closed."""


@dataclass(frozen=True)
class ReleaseConfig:
    source_root: Path = DEFAULT_SOURCE_ROOT
    runtime_root: Path = DEFAULT_RUNTIME_ROOT
    python_bin: Path = DEFAULT_PYTHON_BIN
    service_name: str = DEFAULT_SERVICE_NAME


def default_runner(command: Sequence[str], cwd: Path | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        check=False,
    )


class ReleaseGate:
    def __init__(self, config: ReleaseConfig, runner: Runner = default_runner) -> None:
        self.config = config
        self.runner = runner
        self.runtime_mutated = False

    def run(self) -> int:
        source_head = ""
        previous_runtime_head: str | None = None

        try:
            self._log_config()
            source_head = self._run_preflight()
            self._validate_source()
            previous_runtime_head = self._capture_runtime_head()
            self._deploy_runtime_commit(source_head)
            self._validate_runtime(source_head)
            self._restart_service()
            self._assert_service_active()
        except ReleaseGateError as exc:
            rollback_error = None
            if self.runtime_mutated and previous_runtime_head is not None:
                rollback_error = self._rollback(previous_runtime_head)

            print()
            if rollback_error is None and self.runtime_mutated and previous_runtime_head is not None:
                print(f"ROLLBACK_OK: {previous_runtime_head}")
            elif rollback_error is not None:
                print(f"ROLLBACK_FAIL: {rollback_error}", file=sys.stderr)

            print(f"RELEASE_GATE_FAIL: {exc}", file=sys.stderr)
            return 1

        print()
        print(f"RELEASE_GATE_OK: {source_head}")
        return 0

    def _run_preflight(self) -> str:
        self._require_directory(self.config.source_root, "source repo")
        self._require_directory(self.config.runtime_root, "runtime repo")
        self._require_executable(self.config.python_bin, "venv python")

        self._git_root(self.config.source_root, "source repo")
        self._git_root(self.config.runtime_root, "runtime repo")
        self._require_clean_worktree(self.config.source_root, "source repo")
        self._require_clean_worktree(self.config.runtime_root, "runtime repo")
        self._require_main_branch()
        self._require_origin_main_match()
        self._compile_sanity(self.config.source_root, "source")
        return self._git_output(self.config.source_root, ["git", "rev-parse", "HEAD"], "source HEAD")

    def _validate_source(self) -> None:
        self._run_checked(
            [str(self.config.python_bin), "-m", "pytest", "-q"],
            cwd=self.config.source_root,
            step="source test suite",
        )

    def _capture_runtime_head(self) -> str:
        return self._git_output(self.config.runtime_root, ["git", "rev-parse", "HEAD"], "runtime HEAD")

    def _deploy_runtime_commit(self, source_head: str) -> None:
        self._run_checked(
            ["git", "fetch", "--quiet", str(self.config.source_root), "main"],
            cwd=self.config.runtime_root,
            step="fetch source main into runtime",
        )

        self.runtime_mutated = True
        self._run_checked(
            ["git", "checkout", "--force", "--detach", source_head],
            cwd=self.config.runtime_root,
            step=f"deploy source commit {source_head} into runtime",
        )

    def _validate_runtime(self, source_head: str) -> None:
        runtime_head = self._git_output(
            self.config.runtime_root,
            ["git", "rev-parse", "HEAD"],
            "runtime HEAD after deploy",
        )
        if runtime_head != source_head:
            raise ReleaseGateError(
                f"runtime HEAD {runtime_head} does not match source HEAD {source_head} after deploy"
            )

        self._require_clean_worktree(self.config.runtime_root, "runtime repo after deploy")
        self._run_checked(
            [str(self.config.python_bin), "-m", "pytest", "-q"],
            cwd=self.config.runtime_root,
            step="runtime test suite",
        )

    def _restart_service(self) -> None:
        self._run_checked(
            ["systemctl", "--user", "restart", self.config.service_name],
            cwd=None,
            step=f"restart {self.config.service_name}",
        )

    def _assert_service_active(self) -> None:
        active = self._run_checked(
            ["systemctl", "--user", "is-active", self.config.service_name],
            cwd=None,
            step=f"confirm {self.config.service_name} is active",
        ).stdout.strip()
        if active != "active":
            raise ReleaseGateError(
                f"{self.config.service_name} is not active after restart (reported state: {active or 'unknown'})"
            )

    def _rollback(self, previous_runtime_head: str) -> str | None:
        print()
        print("=== rollback ===")

        try:
            self._run_checked(
                ["git", "checkout", "--force", "--detach", previous_runtime_head],
                cwd=self.config.runtime_root,
                step=f"restore runtime to {previous_runtime_head}",
            )
            self._run_checked(
                ["systemctl", "--user", "restart", self.config.service_name],
                cwd=None,
                step=f"restart {self.config.service_name} on rolled-back runtime",
            )
            active = self._run_checked(
                ["systemctl", "--user", "is-active", self.config.service_name],
                cwd=None,
                step=f"confirm {self.config.service_name} is active after rollback",
            ).stdout.strip()
            if active != "active":
                raise ReleaseGateError(
                    f"{self.config.service_name} is not active after rollback (reported state: {active or 'unknown'})"
                )
        except ReleaseGateError as exc:
            return str(exc)

        return None

    def _require_directory(self, path: Path, label: str) -> None:
        print()
        print(f"=== {label} exists ===")
        if not path.is_dir():
            raise ReleaseGateError(f"{label} missing: {path}")
        print(f"CHECK_OK: {label} exists")

    def _require_executable(self, path: Path, label: str) -> None:
        print()
        print(f"=== {label} exists ===")
        if not path.is_file() or not os.access(path, os.X_OK):
            raise ReleaseGateError(f"{label} missing or not executable: {path}")
        print(f"CHECK_OK: {label} exists")

    def _git_root(self, path: Path, label: str) -> None:
        root = self._git_output(path, ["git", "rev-parse", "--show-toplevel"], f"{label} git root")
        if Path(root) != path:
            raise ReleaseGateError(f"{label} git root mismatch: expected {path}, got {root}")

    def _require_clean_worktree(self, cwd: Path, label: str) -> None:
        status = self._git_output(
            cwd,
            ["git", "status", "--short", "--untracked-files=all"],
            f"{label} clean worktree",
            allow_empty=True,
        )
        if status:
            raise ReleaseGateError(f"{label} worktree is dirty:\n{status}")

    def _require_main_branch(self) -> None:
        branch = self._git_output(
            self.config.source_root,
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            "source branch",
        )
        if branch != "main":
            raise ReleaseGateError(f"source repo must be on main, found {branch}")

    def _require_origin_main_match(self) -> None:
        self._run_checked(
            ["git", "fetch", "--quiet", "origin", "main"],
            cwd=self.config.source_root,
            step="refresh origin/main",
        )
        source_head = self._git_output(
            self.config.source_root,
            ["git", "rev-parse", "HEAD"],
            "source HEAD",
        )
        origin_main = self._git_output(
            self.config.source_root,
            ["git", "rev-parse", "origin/main"],
            "origin/main",
        )
        if source_head != origin_main:
            raise ReleaseGateError(
                "source HEAD does not match origin/main; push or sync main before releasing "
                f"(source HEAD {source_head}, origin/main {origin_main})"
            )

    def _compile_sanity(self, cwd: Path, label: str) -> None:
        self._run_checked(
            [str(self.config.python_bin), "-m", "compileall", "-q", "isla_v2", "tests"],
            cwd=cwd,
            step=f"{label} compile sanity",
        )

    def _git_output(
        self,
        cwd: Path,
        command: Sequence[str],
        step: str,
        *,
        allow_empty: bool = False,
    ) -> str:
        result = self._run_checked(command, cwd=cwd, step=step)
        output = result.stdout.strip()
        if not output and not allow_empty:
            raise ReleaseGateError(f"{step} returned no output")
        return output

    def _run_checked(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None,
        step: str,
    ) -> subprocess.CompletedProcess[str]:
        print()
        print(f"=== {step} ===")
        result = self.runner(command, cwd)
        self._emit_output(result)
        if result.returncode != 0:
            raise ReleaseGateError(self._format_command_failure(step, command, cwd, result))
        print(f"CHECK_OK: {step}")
        return result

    @staticmethod
    def _emit_output(result: subprocess.CompletedProcess[str]) -> None:
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)

    @staticmethod
    def _format_command_failure(
        step: str,
        command: Sequence[str],
        cwd: Path | None,
        result: subprocess.CompletedProcess[str],
    ) -> str:
        lines = [
            f"{step} failed with rc={result.returncode}",
            f"command: {shlex.join(command)}",
        ]
        if cwd is not None:
            lines.append(f"cwd: {cwd}")
        if result.stdout:
            lines.append(f"stdout:\n{result.stdout.rstrip()}")
        if result.stderr:
            lines.append(f"stderr:\n{result.stderr.rstrip()}")
        return "\n".join(lines)

    def _log_config(self) -> None:
        print("=== release gate config ===")
        print(f"source: {self.config.source_root}")
        print(f"runtime: {self.config.runtime_root}")
        print(f"python: {self.config.python_bin}")
        print(f"service: {self.config.service_name}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the fail-closed ISLA release gate.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    parse_args(argv)
    gate = ReleaseGate(ReleaseConfig())
    return gate.run()


if __name__ == "__main__":
    raise SystemExit(main())
