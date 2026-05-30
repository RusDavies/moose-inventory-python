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


@pytest.mark.parametrize(
    "args",
    [
        ("host", "add", "web01"),
        ("host", "add", "dry-run-host", "--dry-run"),
        ("host", "get", "missing"),
        ("host", "list"),
    ],
)
def test_core_host_single_command_output_matches_ruby(
    tmp_path: Path, args: tuple[str, ...]
) -> None:
    run = make_compatibility_run(tmp_path)

    ruby_result, python_result = run.compare(args)

    assert python_result == ruby_result


def test_core_host_stateful_flow_matches_ruby(tmp_path: Path) -> None:
    run = make_compatibility_run(tmp_path)
    for args in [
        ("host", "add", "web01"),
        ("host", "get", "web01"),
        ("host", "list"),
        ("host", "rm", "web01", "--yes"),
        ("host", "get", "web01"),
    ]:
        ruby_result, python_result = run.compare(args)
        assert python_result == ruby_result


@pytest.mark.parametrize(
    "args",
    [
        ("group", "add", "web"),
        ("group", "add", "dry-run-group", "--dry-run"),
        ("group", "get", "missing"),
        ("group", "list"),
        ("group", "add", "ungrouped"),
    ],
)
def test_core_group_single_command_output_matches_ruby(
    tmp_path: Path, args: tuple[str, ...]
) -> None:
    run = make_compatibility_run(tmp_path)

    ruby_result, python_result = run.compare(args)

    assert python_result == ruby_result


def test_core_group_stateful_flow_matches_ruby(tmp_path: Path) -> None:
    run = make_compatibility_run(tmp_path)
    for args in [
        ("group", "add", "web"),
        ("group", "get", "web"),
        ("group", "list"),
        ("group", "rm", "web", "--yes"),
        ("group", "get", "web"),
    ]:
        ruby_result, python_result = run.compare(args)
        assert python_result == ruby_result


@pytest.mark.parametrize(
    "flow",
    [
        [
            ("host", "add", "web01"),
            ("group", "add", "web"),
            ("host", "addgroup", "web01", "web"),
        ],
        [
            ("host", "add", "web01"),
            ("host", "addgroup", "web01", "web"),
            ("host", "rmgroup", "web01", "web", "--yes"),
        ],
        [("group", "add", "web"), ("group", "addhost", "web", "web01")],
        [
            ("group", "add", "web"),
            ("group", "addhost", "web", "web01"),
            ("group", "rmhost", "web", "web01", "--yes"),
        ],
    ],
)
def test_association_command_flows_match_ruby(
    tmp_path: Path, flow: list[tuple[str, ...]]
) -> None:
    run = make_compatibility_run(tmp_path)
    for args in flow:
        ruby_result, python_result = run.compare(args)
        assert python_result == ruby_result


@pytest.mark.parametrize(
    "flow",
    [
        [
            ("host", "add", "web01"),
            ("host", "addvar", "web01", "os=fedora"),
            ("host", "listvars", "web01"),
            ("host", "rmvar", "web01", "os", "--yes"),
        ],
        [
            ("group", "add", "web"),
            ("group", "addvar", "web", "role=frontend"),
            ("group", "listvars", "web"),
            ("group", "rmvar", "web", "role", "--yes"),
        ],
        [
            ("host", "add", "web01"),
            ("host", "addvar", "web01", "os=fedora"),
            ("--host", "web01"),
        ],
        [
            ("group", "add", "web"),
            ("group", "addvar", "web", "role=frontend"),
            ("--ansible", "group", "listvars", "web"),
        ],
    ],
)
def test_variable_command_flows_match_ruby(
    tmp_path: Path, flow: list[tuple[str, ...]]
) -> None:
    run = make_compatibility_run(tmp_path)
    for args in flow:
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
