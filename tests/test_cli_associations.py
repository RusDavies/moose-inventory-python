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


def test_host_addgroup_and_rmgroup_flow(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_config(tmp_path)
    assert main(["--config", str(config), "host", "add", "web01"]) == 0
    assert main(["--config", str(config), "group", "add", "web"]) == 0
    capsys.readouterr()

    assert main(["--config", str(config), "host", "addgroup", "web01", "web"]) == 0
    captured = capsys.readouterr()
    assert "Associate host 'web01' with groups 'web':\n" in captured.out
    assert "- Add association {host:web01 <-> group:web}...\n" in captured.out
    assert "- Remove automatic association {host:web01 <-> group:ungrouped}...\n" in captured.out
    assert captured.err == ""

    assert main(["--config", str(config), "host", "rmgroup", "web01", "web", "--yes"]) == 0
    captured = capsys.readouterr()
    assert "Dissociate host 'web01' from groups 'web':\n" in captured.out
    assert "- Remove association {host:web01 <-> group:web}...\n" in captured.out
    assert "- Add automatic association {host:web01 <-> group:ungrouped}...\n" in captured.out
    assert captured.err == ""


def test_group_addhost_and_rmhost_flow(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_config(tmp_path)
    assert main(["--config", str(config), "group", "add", "web"]) == 0
    capsys.readouterr()

    assert main(["--config", str(config), "group", "addhost", "web", "web01"]) == 0
    captured = capsys.readouterr()
    assert "Associate group 'web' with host(s) 'web01':\n" in captured.out
    assert "- add association {group:web <-> host:web01}...\n" in captured.out
    assert "WARNING: Host 'web01' does not exist and will be created.\n" in captured.err

    assert main(["--config", str(config), "group", "rmhost", "web", "web01", "--yes"]) == 0
    captured = capsys.readouterr()
    assert "Dissociate group 'web' from host(s) 'web01':\n" in captured.out
    assert "- remove association {group:web <-> host:web01}...\n" in captured.out
    assert "- add automatic association {group:ungrouped <-> host:web01}...\n" in captured.out
    assert captured.err == ""


def test_association_commands_reject_ungrouped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path)
    assert main(["--config", str(config), "host", "add", "web01"]) == 0
    capsys.readouterr()

    assert main(["--config", str(config), "host", "addgroup", "web01", "ungrouped"]) == 1
    captured = capsys.readouterr()
    assert captured.err == "ERROR: Cannot manually manipulate the automatic group 'ungrouped'.\n"

    assert main(["--config", str(config), "group", "addhost", "ungrouped", "web01"]) == 1
    captured = capsys.readouterr()
    assert captured.err == "ERROR: Cannot manually manipulate the automatic group 'ungrouped'.\n"
