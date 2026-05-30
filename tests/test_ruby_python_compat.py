from __future__ import annotations

from pathlib import Path

import pytest

from compat_harness import CliResult, make_compatibility_run, ruby_available

pytestmark = pytest.mark.skipif(
    not ruby_available(), reason="Ruby moose-inventory reference CLI is unavailable"
)


@pytest.mark.parametrize(
    "args",
    [
        ("database", "status"),
        ("database", "doctor"),
        ("database", "migrate"),
        ("db", "status"),
    ],
)
def test_database_lifecycle_output_matches_ruby(tmp_path: Path, args: tuple[str, ...]) -> None:
    run = make_compatibility_run(tmp_path)

    ruby_result, python_result = run.compare(args)

    assert python_result == ruby_result


def test_database_backup_output_and_artifact_match_ruby(tmp_path: Path) -> None:
    run = make_compatibility_run(tmp_path)

    ruby_result = run.ruby.run(
        run.ruby_config, ("database", "backup", str(run.ruby_root / "backup" / "inventory.db"))
    ).normalized(run.ruby_root)
    python_result = run.python.run(
        run.python_config, ("database", "backup", str(run.python_root / "backup" / "inventory.db"))
    ).normalized(run.python_root)

    assert python_result == ruby_result == CliResult(
        returncode=0,
        stdout="Backed up database to <RUN_ROOT>/backup/inventory.db.\n",
        stderr="",
    )
    assert (run.ruby_root / "backup" / "inventory.db").exists()
    assert (run.python_root / "backup" / "inventory.db").exists()
