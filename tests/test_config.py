from __future__ import annotations

from pathlib import Path

import pytest

from moose_inventory.config import ConfigError, db_settings, parse_runtime_options


def write_config(path: Path, body: str | None = None) -> Path:
    path.write_text(
        body
        or """
general:
  defaultenv: dev

dev:
  db:
    adapter: sqlite3
    file: ./dev.db

prod:
  db:
    adapter: postgresql
    host: localhost
    database: inventory
    user: moose
    password_env: MOOSE_INVENTORY_PASSWORD
""".lstrip(),
        encoding="utf-8",
    )
    return path


def test_parse_runtime_options_uses_explicit_config_and_default_env(tmp_path: Path) -> None:
    config = write_config(tmp_path / "config.yml")

    runtime = parse_runtime_options(["--config", str(config), "host", "list"])

    assert runtime.argv == ("host", "list")
    assert runtime.config == config.resolve()
    assert runtime.env == "dev"
    assert runtime.output_format == "json"
    assert runtime.ansible is False
    assert runtime.trace is False
    assert db_settings(runtime)["adapter"] == "sqlite3"


def test_parse_runtime_options_supports_env_format_ansible_and_trace(tmp_path: Path) -> None:
    config = write_config(tmp_path / "config.yml")

    runtime = parse_runtime_options(
        [
            "--config",
            str(config),
            "--env",
            "prod",
            "--format",
            "yaml",
            "--ansible",
            "--trace",
            "group",
            "list",
        ]
    )

    assert runtime.argv == ("group", "list")
    assert runtime.env == "prod"
    assert runtime.output_format == "json"
    assert runtime.ansible is True
    assert runtime.trace is True
    assert db_settings(runtime)["adapter"] == "postgresql"


def test_parse_runtime_options_preserves_json_compatible_ansible_format(tmp_path: Path) -> None:
    config = write_config(tmp_path / "config.yml")

    runtime = parse_runtime_options(
        ["--config", str(config), "--format", "pjson", "--ansible", "group", "list"]
    )

    assert runtime.output_format == "pjson"
    assert runtime.ansible is True


def test_parse_runtime_options_applies_list_alias(tmp_path: Path) -> None:
    config = write_config(tmp_path / "config.yml")

    runtime = parse_runtime_options(["--config", str(config), "--list"])

    assert runtime.argv == ("group", "list")
    assert runtime.ansible is True


def test_parse_runtime_options_applies_host_alias(tmp_path: Path) -> None:
    config = write_config(tmp_path / "config.yml")

    runtime = parse_runtime_options(["--config", str(config), "--host", "web01"])

    assert runtime.argv == ("host", "listvars", "web01")
    assert runtime.ansible is True


def test_missing_value_after_global_flag_matches_ruby_error() -> None:
    with pytest.raises(ConfigError, match="Expected a value after --config"):
        parse_runtime_options(["--config"])


def test_missing_explicit_config_fails_with_ruby_style_message(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yml"

    with pytest.raises(ConfigError, match="The configuration file .* does not exist"):
        parse_runtime_options(["--config", str(missing), "host", "list"])


def test_missing_general_root_fails(tmp_path: Path) -> None:
    config = write_config(tmp_path / "config.yml", "dev:\n  db:\n    adapter: sqlite3\n")

    with pytest.raises(ConfigError, match="Missing 'general' root"):
        parse_runtime_options(["--config", str(config), "host", "list"])


def test_missing_defaultenv_fails(tmp_path: Path) -> None:
    config = write_config(
        tmp_path / "config.yml", "general: {}\ndev:\n  db:\n    adapter: sqlite3\n"
    )

    with pytest.raises(ConfigError, match="No defaultenv set"):
        parse_runtime_options(["--config", str(config), "host", "list"])


def test_missing_selected_environment_fails(tmp_path: Path) -> None:
    config = write_config(tmp_path / "config.yml")

    with pytest.raises(ConfigError, match="Missing 'missing' root"):
        parse_runtime_options(["--config", str(config), "--env", "missing", "host", "list"])
