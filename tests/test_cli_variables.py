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


def test_host_variable_lifecycle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_config(tmp_path)
    assert main(["--config", str(config), "host", "add", "web01"]) == 0
    capsys.readouterr()

    assert main(["--config", str(config), "host", "addvar", "web01", "os=fedora"]) == 0
    captured = capsys.readouterr()
    assert "Add variables 'os=fedora' to host 'web01':\n" in captured.out
    assert "- add variable 'os=fedora'...\n" in captured.out
    assert captured.err == ""

    assert main(["--config", str(config), "host", "listvars", "web01"]) == 0
    captured = capsys.readouterr()
    assert captured.out == '{"web01":{"os":"fedora"}}\n'

    assert main(["--config", str(config), "host", "rmvar", "web01", "os", "--yes"]) == 0
    captured = capsys.readouterr()
    assert "Remove variable(s) 'os' from host 'web01':\n" in captured.out
    assert "- remove variable 'os'...\n" in captured.out


def test_group_variable_lifecycle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_config(tmp_path)
    assert main(["--config", str(config), "group", "add", "web"]) == 0
    capsys.readouterr()

    assert main(["--config", str(config), "group", "addvar", "web", "role=frontend"]) == 0
    captured = capsys.readouterr()
    assert "Add variables 'role=frontend' to group 'web':\n" in captured.out
    assert "- add variable 'role=frontend'...\n" in captured.out

    assert main(["--config", str(config), "--ansible", "group", "listvars", "web"]) == 0
    captured = capsys.readouterr()
    assert captured.out == '{"role":"frontend"}\n'

    assert main(["--config", str(config), "group", "rmvar", "web", "role", "--yes"]) == 0
    captured = capsys.readouterr()
    assert "Remove variable(s) 'role' from group 'web':\n" in captured.out
    assert "- remove variable 'role'...\n" in captured.out


def test_variable_commands_reject_bad_shapes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path)
    assert main(["--config", str(config), "host", "add", "web01"]) == 0
    capsys.readouterr()

    assert main(["--config", str(config), "host", "addvar", "web01", "broken"]) == 1
    captured = capsys.readouterr()
    assert "ERROR: Incorrect format in '{broken}'. Expected 'key=value'.\n" in captured.err

    assert (
        main(["--config", str(config), "host", "rmvar", "web01", "bad=shape=extra", "--yes"])
        == 1
    )
    captured = capsys.readouterr()
    assert (
        "ERROR: Incorrect format in {bad=shape=extra}. Expected 'key' or 'key=value'.\n"
        in captured.err
    )
