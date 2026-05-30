from __future__ import annotations

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


def test_unimplemented_command_fails_predictably(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["host", "list"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "not implemented" in captured.err
