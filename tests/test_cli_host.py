from __future__ import annotations

import json
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


def test_host_add_get_list_and_rm_flow(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_config(tmp_path)

    assert main(["--config", str(config), "host", "add", "web01"]) == 0
    captured = capsys.readouterr()
    assert captured.out == (
        "Add host 'web01':\n"
        "  - Creating host 'web01'...\n"
        "    - OK\n"
        "  - Adding automatic association {host:web01 <-> group:ungrouped}...\n"
        "    - OK\n"
        "  - All OK\n"
        "Succeeded\n"
    )
    assert captured.err == ""

    assert main(["--config", str(config), "host", "get", "web01"]) == 0
    captured = capsys.readouterr()
    assert captured.out == '{"web01":{"groups":["ungrouped"]}}\n'

    assert main(["--config", str(config), "host", "list"]) == 0
    captured = capsys.readouterr()
    assert captured.out == '{"web01":{"groups":["ungrouped"]}}\n'

    assert main(["--config", str(config), "host", "rm", "web01", "--yes"]) == 0
    captured = capsys.readouterr()
    assert captured.out == (
        "Remove host 'web01':\n"
        "  - Retrieve host 'web01'...\n"
        "    - OK\n"
        "  - Destroy host 'web01'...\n"
        "    - OK\n"
        "  - All OK\n"
        "Succeeded.\n"
    )
    assert captured.err == ""

    assert main(["--config", str(config), "host", "get", "web01"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "{}\n"


def test_host_add_dry_run_does_not_write(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path)

    assert main(["--config", str(config), "host", "add", "dry-run-host", "--dry-run"]) == 0
    captured = capsys.readouterr()
    assert "Dry run complete. No changes applied.\n" in captured.out
    assert captured.err == ""

    assert main(["--config", str(config), "host", "get", "dry-run-host"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "{}\n"


def test_host_rm_requires_confirmation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_config(tmp_path)
    assert main(["--config", str(config), "host", "add", "web01"]) == 0
    capsys.readouterr()

    assert main(["--config", str(config), "host", "rm", "web01"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "ERROR: host rm web01 is destructive. Re-run with --yes to confirm, "
        "or use --dry-run to preview.\n"
    )


def test_host_rm_plan_format_is_machine_readable_and_non_mutating(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path)
    assert main(["--config", str(config), "host", "add", "web01"]) == 0
    capsys.readouterr()

    assert (
        main(
            [
                "--config",
                str(config),
                "host",
                "rm",
                "web01",
                "--dry-run",
                "--plan-format",
                "json",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    plan = json.loads(captured.out)
    assert plan["command"] == "host rm"
    assert plan["dry_run"] is True
    assert plan["changes_applied"] is False
    assert plan["exit_code"] == 0
    assert "Dry run complete. No changes applied." in plan["stdout"]
    assert any(event["type"] == "dry_run_summary" for event in plan["events"])
    assert captured.err == ""

    assert main(["--config", str(config), "host", "get", "web01"]) == 0
    captured = capsys.readouterr()
    assert captured.out == '{"web01":{"groups":["ungrouped"]}}\n'


def test_host_add_with_group_creates_missing_group(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path)

    assert main(["--config", str(config), "host", "add", "web01", "--groups", "web"]) == 0

    captured = capsys.readouterr()
    assert "WARNING: The group 'web' doesn't exist, but will be created.\n" in captured.err
    assert "Adding association {host:web01 <-> group:web}" in captured.out

    assert main(["--config", str(config), "host", "get", "web01"]) == 0
    captured = capsys.readouterr()
    assert captured.out == '{"web01":{"groups":["web"]}}\n'
