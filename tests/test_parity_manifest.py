from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from compat_harness import CliResult, make_compatibility_run, ruby_available

MANIFEST_PATH = Path(__file__).with_name("parity_manifest.yml")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUBY_PROJECT_ROOT = PROJECT_ROOT.parent / "moose-inventory"
VALID_STATUSES = {"active", "pending_python_port"}
VALID_COMPARE_MODES = {"exact", "pattern", "yaml_structural", "json_structural"}


def load_manifest() -> dict[str, Any]:
    loaded = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return cast(dict[str, Any], loaded)


def cases() -> list[dict[str, Any]]:
    manifest_cases = load_manifest()["cases"]
    assert isinstance(manifest_cases, list)
    return cast(list[dict[str, Any]], manifest_cases)


def active_cases() -> list[dict[str, Any]]:
    return [case for case in cases() if case["status"] == "active"]


def test_parity_manifest_schema_and_sources_are_valid() -> None:
    manifest = load_manifest()

    assert manifest["schema_version"] == 1
    assert manifest["ruby_reference_root"] == "../moose-inventory"
    assert len(cases()) >= 30

    ids: set[str] = set()
    statuses = {case["status"] for case in cases()}
    command_roots = {case["args"][0] for case in cases()}

    for case in cases():
        assert case["id"] not in ids
        ids.add(case["id"])
        assert case["status"] in VALID_STATUSES
        assert case["args"]
        assert case["compare"]["mode"] in VALID_COMPARE_MODES
        assert "description" in case
        assert "expected" in case
        source_path = str(case["source"]).split(":", 1)[0]
        assert (RUBY_PROJECT_ROOT / source_path).exists(), case["source"]

    assert statuses == VALID_STATUSES
    assert {"host", "group", "database", "db", "doctor", "audit", "export", "import"}.issubset(
        command_roots
    )


@pytest.mark.skipif(
    not ruby_available(), reason="Ruby moose-inventory reference CLI is unavailable"
)
@pytest.mark.parametrize("case", active_cases(), ids=lambda case: case["id"])
def test_active_manifest_cases_match_ruby(tmp_path: Path, case: dict[str, Any]) -> None:
    run = make_compatibility_run(tmp_path)

    for setup_args in case.get("setup", []):
        ruby_setup, python_setup = run.compare(tuple(setup_args))
        assert python_setup == ruby_setup

    ruby_result, python_result = run.compare(tuple(case["args"]))

    assert python_result == ruby_result
    assert_result_matches_expected(python_result, cast(dict[str, Any], case["expected"]))

    artifact_paths = case.get("compare", {}).get("artifact_exists", [])
    for artifact_path in artifact_paths:
        assert (run.ruby_root / artifact_path).exists()
        assert (run.python_root / artifact_path).exists()


def assert_result_matches_expected(result: CliResult, expected: dict[str, Any]) -> None:
    """Check manifest expectation snippets for active cases."""
    expected_returncode = expected.get("returncode")
    if isinstance(expected_returncode, int):
        assert result.returncode == expected_returncode
    elif expected_returncode == "nonzero":
        assert result.returncode != 0

    for stream_name in ("stdout", "stderr"):
        if stream_name in expected:
            assert getattr(result, stream_name) == expected[stream_name]
        for snippet in expected.get(f"{stream_name}_contains", []):
            assert snippet in getattr(result, stream_name)
        for snippet in expected.get(f"{stream_name}_not_contains", []):
            assert snippet not in getattr(result, stream_name)
