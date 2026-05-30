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


def test_host_tags_normalize_dedupe_and_remove(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path)
    assert main(["--config", str(config), "host", "add", "app01"]) == 0
    capsys.readouterr()

    assert (
        main(["--config", str(config), "host", "addtag", "app01", "Prod", "PROD", "critical"])
        == 0
    )
    captured = capsys.readouterr()
    assert "Added host tag(s) to 'app01': prod, critical.\n" == captured.out

    assert main(["--config", str(config), "host", "listtags", "app01"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "Host 'app01' tags: critical, prod\n"

    assert main(["--config", str(config), "host", "rmtag", "app01", "PROD", "--yes"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "Removed host tag(s) from 'app01': prod.\n"


def test_group_tags_lifecycle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_config(tmp_path)
    assert main(["--config", str(config), "group", "add", "web"]) == 0
    assert (
        main(["--config", str(config), "group", "addtag", "web", "frontend", "owner-platform"])
        == 0
    )
    capsys.readouterr()

    assert main(["--config", str(config), "group", "listtags", "web"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "Group 'web' tags: frontend, owner-platform\n"


def test_tagging_missing_entity_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_config(tmp_path)

    assert main(["--config", str(config), "group", "addtag", "missing", "prod"]) == 1
    captured = capsys.readouterr()
    assert "ERROR: The group 'missing' does not exist.\n" == captured.err
