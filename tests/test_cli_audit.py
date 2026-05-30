from __future__ import annotations

from pathlib import Path

import pytest

from moose_inventory.cli import main


def write_config(tmp_path: Path) -> Path:
    config = tmp_path / "config.yml"
    config.write_text(
        "general:\n"
        "  defaultenv: dev\n"
        "dev:\n"
        "  db:\n"
        "    adapter: sqlite3\n"
        f"    file: {tmp_path / 'inventory.db'}\n",
        encoding="utf-8",
    )
    return config


def test_audit_log_starts_empty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_config(tmp_path)

    assert main(["--config", str(config), "audit", "list"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "No audit events recorded.\n"


def test_audit_records_mutating_host_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path)
    assert main(["--config", str(config), "host", "add", "app01"]) == 0
    capsys.readouterr()

    assert main(["--config", str(config), "audit", "list"]) == 0
    captured = capsys.readouterr()
    assert " host add host=app01 action=add\n" in captured.out


def test_audit_does_not_record_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path)
    assert main(["--config", str(config), "host", "add", "app01", "--dry-run"]) == 0
    capsys.readouterr()

    assert main(["--config", str(config), "audit", "list"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "No audit events recorded.\n"
