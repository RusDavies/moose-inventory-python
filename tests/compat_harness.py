"""Ruby-vs-Python CLI compatibility harness for moose-inventory.

The harness runs each implementation against its own disposable SQLite database, then
normalizes temporary paths so tests can compare CLI behavior directly.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final = Path(__file__).resolve().parents[1]
RUBY_PROJECT_ROOT: Final = PROJECT_ROOT.parent / "moose-inventory"
PYTHON_ENV: Final = {
    **os.environ,
    "PYTHONPATH": str(PROJECT_ROOT / "src"),
}


@dataclass(frozen=True)
class CliResult:
    """Captured CLI result."""

    returncode: int
    stdout: str
    stderr: str

    def normalized(self, root: Path) -> CliResult:
        """Return result with volatile temporary paths normalized."""
        root_text = str(root.resolve())
        return CliResult(
            returncode=self.returncode,
            stdout=self.stdout.replace(root_text, "<RUN_ROOT>"),
            stderr=self.stderr.replace(root_text, "<RUN_ROOT>"),
        )


@dataclass(frozen=True)
class CliImplementation:
    """One moose-inventory implementation under test."""

    name: str
    command_prefix: tuple[str, ...]
    cwd: Path
    env: dict[str, str] | None = None

    def run(self, config: Path, args: tuple[str, ...], stdin: str | None = None) -> CliResult:
        """Run a command with a Ruby-compatible explicit config flag."""
        completed = subprocess.run(
            [*self.command_prefix, "--config", str(config), *args],
            cwd=self.cwd,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
            input=stdin,
        )
        return CliResult(completed.returncode, completed.stdout, completed.stderr)


@dataclass(frozen=True)
class CompatibilityRun:
    """Disposable parity run context for both implementations."""

    ruby: CliImplementation
    python: CliImplementation
    root: Path
    ruby_root: Path
    python_root: Path
    ruby_config: Path
    python_config: Path

    def compare(
        self, args: tuple[str, ...], stdin: str | None = None
    ) -> tuple[CliResult, CliResult]:
        """Run a command on both implementations and return normalized results."""
        ruby_args = materialize_args(args, self.ruby_root)
        python_args = materialize_args(args, self.python_root)
        ruby_result = self.ruby.run(self.ruby_config, ruby_args, stdin=stdin).normalized(
            self.ruby_root
        )
        python_result = self.python.run(
            self.python_config, python_args, stdin=stdin
        ).normalized(self.python_root)
        return ruby_result, python_result

    def for_manifest_case(self, case: dict[str, object]) -> CompatibilityRun:
        """Return a run context adjusted for manifest case options."""
        del case
        return self


def ruby_available() -> bool:
    """Return whether the sibling Ruby implementation can be executed."""
    return (
        RUBY_PROJECT_ROOT.exists()
        and (RUBY_PROJECT_ROOT / "bin" / "moose-inventory").exists()
        and shutil.which("bundle") is not None
        and shutil.which("ruby") is not None
    )


def make_compatibility_run(tmp_path: Path) -> CompatibilityRun:
    """Create disposable DB/config roots for a parity run."""
    ruby_root = tmp_path / "ruby"
    python_root = tmp_path / "python"
    ruby_config = write_config(ruby_root)
    python_config = write_config(python_root)

    return CompatibilityRun(
        ruby=CliImplementation(
            name="ruby",
            command_prefix=("bundle", "exec", "ruby", "-Ilib", "bin/moose-inventory"),
            cwd=RUBY_PROJECT_ROOT,
        ),
        python=CliImplementation(
            name="python",
            command_prefix=(sys.executable, "-m", "moose_inventory.cli"),
            cwd=PROJECT_ROOT,
            env=PYTHON_ENV,
        ),
        root=tmp_path,
        ruby_root=ruby_root,
        python_root=python_root,
        ruby_config=ruby_config,
        python_config=python_config,
    )


def materialize_args(args: tuple[str, ...], root: Path) -> tuple[str, ...]:
    """Replace manifest placeholders with implementation-specific paths."""
    return tuple(arg.replace("<RUN_ROOT>", str(root.resolve())) for arg in args)


def write_config(root: Path) -> Path:
    """Write a Ruby-compatible SQLite config for an implementation run."""
    root.mkdir(parents=True, exist_ok=True)
    config = root / "config.yml"
    db_path = root / "inventory.db"
    config.write_text(
        "general:\n"
        "  defaultenv: dev\n"
        "dev:\n"
        "  db:\n"
        "    adapter: sqlite3\n"
        f"    file: {db_path}\n",
        encoding="utf-8",
    )
    return config
