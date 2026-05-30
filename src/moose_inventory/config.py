"""Configuration and runtime option parsing for moose-inventory.

This module intentionally mirrors the Ruby CLI's pre-dispatch global flag handling.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml


class ConfigError(RuntimeError):
    """Raised when runtime arguments or YAML configuration are invalid."""


@dataclass(frozen=True)
class RuntimeOptions:
    """Resolved runtime options after Ruby-compatible global parsing."""

    argv: tuple[str, ...]
    config: Path
    env: str
    format: str
    ansible: bool
    trace: bool
    settings: Mapping[str, Any]

    @property
    def output_format(self) -> str:
        """Return the normalized output format."""
        return self.format.lower()


DEFAULT_FORMAT = "json"
VALUE_FLAGS = ("config", "env", "format")
BOOLEAN_FLAGS = ("ansible", "trace")
STANDARD_CONFIG_PATHS = (
    "./.moose-tools/inventory/config",
    "~/.moose-tools/inventory/config",
    "~/local/etc/moose-tools/inventory/config",
    "/etc/moose-tools/inventory/config",
)
JSON_COMPATIBLE_FORMATS = {"p", "pjson", "j", "json"}


def parse_runtime_options(argv: Sequence[str]) -> RuntimeOptions:
    """Parse Ruby-compatible global flags, load config, and return runtime options."""
    args = list(argv)
    confopts: dict[str, Any] = {
        "config": None,
        "env": "",
        "format": DEFAULT_FORMAT,
        "ansible": False,
        "trace": False,
    }

    extract_value_flags(args, confopts)
    extract_boolean_flags(args, confopts)
    apply_ansible_aliases(args, confopts)
    normalize_ansible_format(confopts)

    config_path = resolve_config_file(cast(str | None, confopts["config"]))
    document = load_config_file(config_path)
    selected_env = selected_environment(document, cast(str, confopts["env"]), config_path)
    settings = environment_settings(document, selected_env, config_path)

    return RuntimeOptions(
        argv=tuple(args),
        config=config_path,
        env=selected_env,
        format=cast(str, confopts["format"]),
        ansible=cast(bool, confopts["ansible"]),
        trace=cast(bool, confopts["trace"]),
        settings=settings,
    )


def extract_value_flags(args: list[str], confopts: dict[str, Any]) -> None:
    """Remove value-style global flags from args into confopts."""
    for flag in VALUE_FLAGS:
        extract_value_flag(args, confopts, flag)


def extract_value_flag(args: list[str], confopts: dict[str, Any], flag: str) -> None:
    option = f"--{flag}"
    try:
        index = args.index(option)
    except ValueError:
        return

    value_index = index + 1
    if value_index >= len(args) or args[value_index].startswith("--"):
        raise ConfigError(f"Expected a value after --{flag}")

    confopts[flag] = args[value_index]
    del args[index : index + 2]


def extract_boolean_flags(args: list[str], confopts: dict[str, Any]) -> None:
    """Remove boolean-style global flags from args into confopts."""
    for flag in BOOLEAN_FLAGS:
        extract_boolean_flag(args, confopts, flag)


def extract_boolean_flag(args: list[str], confopts: dict[str, Any], flag: str) -> None:
    option = f"--{flag}"
    try:
        index = args.index(option)
    except ValueError:
        return

    confopts[flag] = True
    del args[index]


def apply_ansible_aliases(args: list[str], confopts: dict[str, Any]) -> None:
    """Apply Ruby-compatible Ansible top-level aliases."""
    if not args:
        return

    if args[0] == "--list":
        confopts["ansible"] = True
        args[:] = ["group", "list"]
        return

    if args[0] == "--host":
        host = args[1] if len(args) > 1 else ""
        confopts["ansible"] = True
        args[:] = ["host", "listvars", host]


def normalize_ansible_format(confopts: dict[str, Any]) -> None:
    """Ruby normalizes non-JSON Ansible format selections back to JSON."""
    requested_format = str(confopts["format"]).lower()
    if confopts["ansible"] is True and requested_format not in JSON_COMPATIBLE_FORMATS:
        confopts["format"] = DEFAULT_FORMAT


def resolve_config_file(explicit_path: str | None) -> Path:
    """Resolve an explicit or default config file path."""
    if explicit_path is not None:
        expanded = Path(explicit_path).expanduser().resolve()
        if not expanded.exists():
            raise ConfigError(f"The configuration file {expanded} does not exist")
        return expanded

    for candidate in STANDARD_CONFIG_PATHS:
        expanded = Path(candidate).expanduser().resolve()
        if expanded.exists():
            return expanded

    raise ConfigError("No configuration either given or found in standard locations.")


def load_config_file(path: Path) -> Mapping[str, Any]:
    """Load a YAML config file safely."""
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Could not parse configuration file {path}: {exc}") from exc

    if not isinstance(loaded, dict):
        raise ConfigError(f"Configuration file {path} must contain a YAML mapping")

    return cast(Mapping[str, Any], loaded)


def selected_environment(document: Mapping[str, Any], requested_env: str, path: Path) -> str:
    """Resolve the environment section to use."""
    if requested_env:
        return requested_env

    general = document.get("general")
    if not isinstance(general, Mapping):
        raise ConfigError(f"Missing 'general' root in {path}")

    default_env = general.get("defaultenv")
    if not isinstance(default_env, str) or default_env == "":
        raise ConfigError(f"No defaultenv set in {path}")

    return default_env


def environment_settings(document: Mapping[str, Any], env: str, path: Path) -> Mapping[str, Any]:
    """Return settings for a selected environment section."""
    settings = document.get(env)
    if not isinstance(settings, Mapping):
        raise ConfigError(f"Missing '{env}' root in {path}")

    return cast(Mapping[str, Any], settings)


def db_settings(runtime: RuntimeOptions) -> Mapping[str, Any]:
    """Return selected database settings."""
    db = runtime.settings.get("db")
    if not isinstance(db, Mapping):
        raise ConfigError("Missing 'db' settings in selected environment")
    return cast(Mapping[str, Any], db)
