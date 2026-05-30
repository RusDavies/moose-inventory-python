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


def test_group_addchild_and_rmchild_flow(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path)
    assert main(["--config", str(config), "group", "add", "parent", "child"]) == 0
    capsys.readouterr()

    assert main(["--config", str(config), "group", "addchild", "parent", "child"]) == 0
    captured = capsys.readouterr()
    assert "Associate parent group 'parent' with child group(s) 'child':\n" in captured.out
    assert "- add association {group:parent <-> group:child}...\n" in captured.out
    assert captured.err == ""

    assert main(["--config", str(config), "group", "rmchild", "parent", "child", "--yes"]) == 0
    captured = capsys.readouterr()
    assert "Dissociate parent group 'parent' from child group(s) 'child':\n" in captured.out
    assert "- remove association {group:parent <-> group:child}...\n" in captured.out
    assert captured.err == ""


def test_group_addchild_rejects_cycle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_config(tmp_path)
    assert main(["--config", str(config), "group", "add", "parent", "child"]) == 0
    assert main(["--config", str(config), "group", "addchild", "parent", "child"]) == 0
    capsys.readouterr()

    assert main(["--config", str(config), "group", "addchild", "child", "parent"]) == 1
    captured = capsys.readouterr()
    assert "ERROR: circular group relationship rejected: child -> parent.\n" in captured.err


def test_group_rmchild_delete_orphans(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_config(tmp_path)
    assert main(["--config", str(config), "group", "add", "parent"]) == 0
    assert main(["--config", str(config), "group", "add", "child", "--hosts", "child-host"]) == 0
    assert main(["--config", str(config), "group", "add", "grandchild"]) == 0
    assert main(["--config", str(config), "group", "addchild", "parent", "child"]) == 0
    assert main(["--config", str(config), "group", "addchild", "child", "grandchild"]) == 0
    capsys.readouterr()

    assert (
        main(
            [
                "--config",
                str(config),
                "group",
                "rmchild",
                "--delete-orphans",
                "parent",
                "child",
                "--yes",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert "- Recursively delete orphaned group 'child'...\n" in captured.out
    assert "- Recursively delete orphaned group 'grandchild'...\n" in captured.out
    assert (
        "- Adding automatic association {group:ungrouped <-> host:child-host}...\n"
        in captured.out
    )
