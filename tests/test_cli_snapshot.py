from __future__ import annotations

from pathlib import Path

import pytest
import yaml

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


def test_export_snapshot_yaml(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_config(tmp_path)
    assert main(["--config", str(config), "group", "add", "web"]) == 0
    assert main(["--config", str(config), "host", "add", "web01", "--groups", "web"]) == 0
    assert main(["--config", str(config), "host", "addvar", "web01", "os=fedora"]) == 0
    capsys.readouterr()

    assert main(["--config", str(config), "export"]) == 0
    captured = capsys.readouterr()
    snapshot = yaml.safe_load(captured.out)
    assert snapshot["version"] == 1
    assert snapshot["hosts"]["web01"]["groups"] == ["web"]
    assert snapshot["hosts"]["web01"]["vars"] == {"os": "fedora"}
    assert "web" in snapshot["groups"]


def test_import_snapshot_preview_and_apply(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path)
    snapshot = tmp_path / "snapshot.yml"
    snapshot.write_text(
        "version: 1\n"
        "hosts:\n"
        "  web01:\n"
        "    groups: [web]\n"
        "    tags: [Prod]\n"
        "    vars:\n"
        "      os: fedora\n"
        "groups:\n"
        "  web:\n"
        "    children: []\n"
        "    tags: [frontend]\n"
        "    vars:\n"
        "      role: frontend\n",
        encoding="utf-8",
    )

    assert main(["--config", str(config), "import", str(snapshot), "--preview"]) == 0
    captured = capsys.readouterr()
    assert "Snapshot import preview. No changes applied.\n" in captured.out
    assert "Hosts created: 1\n" in captured.out
    assert "Groups created: 1\n" in captured.out

    assert main(["--config", str(config), "import", str(snapshot)]) == 0
    captured = capsys.readouterr()
    assert f"Imported inventory snapshot from {snapshot}.\n" in captured.out
    assert "Created hosts: 1\n" in captured.out
    assert "Created groups: 1\n" in captured.out
    assert "Variables changed: 2\n" in captured.out
    assert "Associations added: 3\n" in captured.out
