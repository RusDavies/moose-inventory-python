from __future__ import annotations

import io
from pathlib import Path

import pytest

from moose_inventory.cli import main
from moose_inventory.config import parse_runtime_options
from moose_inventory.console import run_console
from moose_inventory.db import database_from_runtime


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


def test_console_quit_from_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO("quit\n"))

    assert main(["--config", str(config), "console"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "Moose Inventory console (read-only). Type help or quit.\nGoodbye.\n"


def test_console_browses_inventory(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_config(tmp_path)
    assert main(["--config", str(config), "group", "add", "web"]) == 0
    assert main(["--config", str(config), "host", "add", "web01", "--groups", "web"]) == 0
    assert main(["--config", str(config), "host", "addtag", "web01", "Prod"]) == 0
    capsys.readouterr()

    runtime = parse_runtime_options(["--config", str(config), "console"])
    output = io.StringIO()
    assert (
        run_console(
            database_from_runtime(runtime),
            io.StringIO("hosts\nhost web01\ntags host web01\nquit\n"),
            output,
        )
        == 0
    )

    assert output.getvalue() == (
        "Moose Inventory console (read-only). Type help or quit.\n"
        "Hosts: web01\n"
        "Host: web01\n"
        "Groups: web\n"
        "Tags: prod\n"
        "prod\n"
        "Goodbye.\n"
    )
