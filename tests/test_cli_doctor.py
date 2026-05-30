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


def test_inventory_doctor_ok(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_config(tmp_path)

    assert main(["--config", str(config), "doctor"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "Inventory doctor found no issues.\n"
    assert captured.err == ""


def test_inventory_doctor_reports_cycle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_config(tmp_path)
    assert main(["--config", str(config), "group", "add", "parent"]) == 0
    assert main(["--config", str(config), "group", "add", "child"]) == 0
    assert main(["--config", str(config), "group", "addchild", "parent", "child"]) == 0
    assert main(["--config", str(config), "group", "addchild", "child", "parent"]) == 0
    capsys.readouterr()

    assert main(["--config", str(config), "doctor"]) == 1
    captured = capsys.readouterr()
    assert "Inventory doctor found" in captured.out
    assert "circular_group_relationship" in captured.out
    assert "Group hierarchy contains a cycle:" in captured.out
