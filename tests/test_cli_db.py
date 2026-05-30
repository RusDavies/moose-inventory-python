from __future__ import annotations

from pathlib import Path

import pytest

from moose_inventory.cli import main


def write_config(tmp_path: Path, db_path: Path) -> Path:
    config = tmp_path / "config.yml"
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


def test_database_status_reports_missing_unmigrated_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path, tmp_path / "inventory.db")

    assert main(["--config", str(config), "database", "status"]) == 0

    captured = capsys.readouterr()
    assert "Adapter: sqlite3\n" in captured.out
    assert "Schema version: unknown\n" in captured.out
    assert "Expected schema version: 4\n" in captured.out
    assert "- hosts: missing\n" in captured.out
    assert captured.err == ""


def test_db_alias_migrate_creates_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path, tmp_path / "inventory.db")

    assert main(["--config", str(config), "db", "migrate"]) == 0

    captured = capsys.readouterr()
    assert captured.out == "Database schema is at version 4.\n"
    assert captured.err == ""

    assert main(["--config", str(config), "database", "status"]) == 0
    captured = capsys.readouterr()
    assert "Schema version: 4\n" in captured.out
    assert "- groups_tags: present\n" in captured.out


def test_database_doctor_fails_before_migration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path, tmp_path / "inventory.db")

    assert main(["--config", str(config), "database", "doctor"]) == 1

    captured = capsys.readouterr()
    assert "Database doctor found issue(s):\n" in captured.out
    assert "- Missing tables:" in captured.out
    assert "- Schema version is None; expected 4.\n" in captured.out
    assert captured.err == ""


def test_database_doctor_passes_after_migration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path, tmp_path / "inventory.db")
    assert main(["--config", str(config), "database", "migrate"]) == 0
    capsys.readouterr()

    assert main(["--config", str(config), "database", "doctor"]) == 0

    captured = capsys.readouterr()
    assert captured.out == "Database doctor found no issues.\n"
    assert captured.err == ""


def test_database_backup_copies_sqlite_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "inventory.db"
    backup_path = tmp_path / "backup" / "inventory.db"
    config = write_config(tmp_path, db_path)
    assert main(["--config", str(config), "database", "migrate"]) == 0
    capsys.readouterr()

    assert main(["--config", str(config), "database", "backup", str(backup_path)]) == 0

    captured = capsys.readouterr()
    assert captured.out == f"Backed up database to {backup_path.resolve()}.\n"
    assert captured.err == ""
    assert backup_path.read_bytes() == db_path.read_bytes()


def test_database_backup_requires_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_config(tmp_path, tmp_path / "inventory.db")

    assert main(["--config", str(config), "database", "backup"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: Expected FILE after database backup\n"
