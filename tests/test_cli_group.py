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


def test_group_add_get_list_and_rm_flow(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_config(tmp_path)

    assert main(["--config", str(config), "group", "add", "web"]) == 0
    captured = capsys.readouterr()
    assert captured.out == (
        "Add group 'web':\n"
        "  - create group...\n"
        "    - OK\n"
        "  - all OK\n"
        "Succeeded\n"
    )
    assert captured.err == ""

    assert main(["--config", str(config), "group", "get", "web"]) == 0
    captured = capsys.readouterr()
    assert captured.out == '{"web":{}}\n'

    assert main(["--config", str(config), "group", "list"]) == 0
    captured = capsys.readouterr()
    assert captured.out == '{"web":{}}\n'

    assert main(["--config", str(config), "group", "rm", "web", "--yes"]) == 0
    captured = capsys.readouterr()
    assert captured.out == (
        "Remove group 'web':\n"
        "  - Retrieve group 'web'...\n"
        "    - OK\n"
        "  - Destroy group 'web'...\n"
        "    - OK\n"
        "  - All OK\n"
        "Succeeded.\n"
    )
    assert captured.err == ""

    assert main(["--config", str(config), "group", "get", "web"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "{}\n"


def test_group_add_rejects_ungrouped(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_config(tmp_path)

    assert main(["--config", str(config), "group", "add", "ungrouped"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: Cannot manually manipulate the automatic group 'ungrouped'\n"


def test_group_rm_requires_confirmation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_config(tmp_path)
    assert main(["--config", str(config), "group", "add", "web"]) == 0
    capsys.readouterr()

    assert main(["--config", str(config), "group", "rm", "web"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "ERROR: group rm web is destructive. Re-run with --yes to confirm, "
        "or use --dry-run to preview.\n"
    )


def test_group_add_plan_format_is_machine_readable_and_non_mutating(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path)

    assert (
        main(
            [
                "--config",
                str(config),
                "group",
                "add",
                "web",
                "--dry-run",
                "--plan-format",
                "json",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    plan = json.loads(captured.out)
    assert plan["command"] == "group add"
    assert plan["dry_run"] is True
    assert plan["changes_applied"] is False
    assert plan["exit_code"] == 0
    assert "Dry run complete. No changes applied." in plan["stdout"]
    assert captured.err == ""

    assert main(["--config", str(config), "group", "get", "web"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "{}\n"


def test_group_add_with_missing_host_warns_and_associates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path)

    assert main(["--config", str(config), "group", "add", "web", "--hosts", "web01"]) == 0

    captured = capsys.readouterr()
    assert "WARNING: Host 'web01' doesn't exist, but will be created.\n" in captured.err
    assert "add association {group:web <-> host:web01}" in captured.out

    assert main(["--config", str(config), "group", "get", "web"]) == 0
    captured = capsys.readouterr()
    assert captured.out == '{"web":{"hosts":["web01"]}}\n'
