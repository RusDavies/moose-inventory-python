from __future__ import annotations

from pathlib import Path

import pytest

from moose_inventory import __version__
from moose_inventory.cli import main


def test_version_exports_package_version() -> None:
    assert __version__ == "0.0.0"


def test_version_command_prints_ruby_style_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version"]) == 0

    captured = capsys.readouterr()
    assert captured.out == "Version 0.0.0\n"
    assert captured.err == ""


def test_help_command_mentions_parity_baseline(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["help"]) == 0

    captured = capsys.readouterr()
    assert "Usage: moose-inventory" in captured.out
    assert "ruby-parity-baseline.md" in captured.out
    assert captured.err == ""


def test_unimplemented_command_fails_after_runtime_parsing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "config.yml"
    config.write_text(
        "general:\n  defaultenv: dev\ndev:\n  db:\n    adapter: sqlite3\n    file: ./dev.db\n",
        encoding="utf-8",
    )

    assert main(["--config", str(config), "group", "list"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "command 'group' is not implemented" in captured.err


def test_config_error_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--config"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: Expected a value after --config\n"
