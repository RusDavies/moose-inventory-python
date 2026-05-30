"""Host command operations and renderers."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

import yaml
from sqlalchemy import Connection, delete, select

from moose_inventory.config import RuntimeOptions
from moose_inventory.db import Database, groups, groups_hosts, hosts, hostvars

AUTOMATIC_GROUP = "ungrouped"


@dataclass(frozen=True)
class HostCommandOptions:
    """Parsed host command options."""

    names: tuple[str, ...]
    groups: tuple[str, ...] = ()
    dry_run: bool = False
    yes: bool = False


class HostCommandError(RuntimeError):
    """Raised for host command usage/runtime errors."""


class HostCommands:
    """Implementation of core host CLI commands."""

    def __init__(self, database: Database, runtime: RuntimeOptions) -> None:
        self.database = database
        self.runtime = runtime

    def run(self) -> int:
        """Dispatch the selected host subcommand."""
        args = list(self.runtime.argv[1:])
        if not args or args[0] in {"help", "--help", "-h"}:
            print_host_usage()
            return 0

        action = args[0]
        try:
            if action == "add":
                return self.add(args[1:])
            if action == "list":
                return self.list_hosts(args[1:])
            if action == "get":
                return self.get(args[1:])
            if action == "rm":
                return self.rm(args[1:])
        except HostCommandError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        print(f"ERROR: host action '{action}' is not implemented.", file=sys.stderr)
        return 1

    def add(self, raw_args: Sequence[str]) -> int:
        """Add one or more hosts."""
        options = parse_host_add_options(raw_args)
        if not options.names:
            print("ERROR: Wrong number of arguments, 0 for 1 or more.", file=sys.stderr)
            return 1

        warnings = False
        with self.database.engine.begin() as connection:
            for name in options.names:
                print(f"Add host '{name}':")
                print(f"  - Creating host '{name}'...")
                host_id = find_host_id(connection, name)
                if host_id is None and not options.dry_run:
                    host_id = create_host(connection, name)
                elif host_id is not None:
                    warnings = True
                    print(
                        f"WARNING: The host '{name}' already exists, skipping creation.",
                        file=sys.stderr,
                    )
                print("    - OK")

                target_groups = options.groups or (AUTOMATIC_GROUP,)
                for group_name in target_groups:
                    automatic = group_name == AUTOMATIC_GROUP and not options.groups
                    prefix = "automatic association" if automatic else "association"
                    print(f"  - Adding {prefix} {{host:{name} <-> group:{group_name}}}...")
                    group_id = find_group_id(connection, group_name)
                    if group_id is None:
                        if not automatic:
                            warnings = True
                            print(
                                f"WARNING: The group '{group_name}' doesn't exist, "
                                "but will be created.",
                                file=sys.stderr,
                            )
                        if not options.dry_run:
                            group_id = create_group(connection, group_name)
                    if not options.dry_run and host_id is not None and group_id is not None:
                        ensure_host_group(connection, host_id, group_id)
                    print("    - OK")
                print("  - All OK")

        if options.dry_run:
            print("Dry run complete. No changes applied.")
        print("Succeeded, with warnings." if warnings else "Succeeded")
        return 0

    def list_hosts(self, raw_args: Sequence[str]) -> int:
        """List hosts."""
        filters = parse_host_list_options(raw_args)
        with self.database.connect() as connection:
            data = query_hosts(connection, filters=filters)
        dump_data(data, self.runtime.output_format)
        return 0

    def get(self, raw_args: Sequence[str]) -> int:
        """Get one or more hosts."""
        names = tuple(arg for arg in raw_args if not arg.startswith("--"))
        if not names:
            print("ERROR: Wrong number of arguments, 0 for 1 or more", file=sys.stderr)
            return 1
        with self.database.connect() as connection:
            data = query_hosts(connection, names=names)
        dump_data(data, self.runtime.output_format)
        return 0

    def rm(self, raw_args: Sequence[str]) -> int:
        """Remove one or more hosts."""
        options = parse_host_rm_options(raw_args)
        if not options.names:
            print("ERROR: Wrong number of arguments, 0 for 1 or more.", file=sys.stderr)
            return 1
        if not options.yes and not options.dry_run:
            joined = ",".join(options.names)
            print(
                f"ERROR: host rm {joined} is destructive. Re-run with --yes to confirm, "
                "or use --dry-run to preview.",
                file=sys.stderr,
            )
            return 1

        warnings = False
        with self.database.engine.begin() as connection:
            for name in options.names:
                print(f"Remove host '{name}':")
                print(f"  - Retrieve host '{name}'...")
                host_id = find_host_id(connection, name)
                if host_id is None:
                    warnings = True
                    print(f"WARNING: Host '{name}' does not exist, skipping.", file=sys.stderr)
                    print("    - No such host, skipping.")
                    print("    - OK")
                    print("  - All OK")
                    continue
                print("    - OK")
                print(f"  - Destroy host '{name}'...")
                if not options.dry_run:
                    delete_host(connection, host_id)
                print("    - OK")
                print("  - All OK")

        if options.dry_run:
            print("Dry run complete. No changes applied.")
        print("Succeeded, with warnings." if warnings else "Succeeded.")
        return 0


def print_host_usage() -> None:
    """Print host command usage."""
    print(
        "Usage: moose-inventory host ACTION [ARGS]\n\n"
        "Host commands:\n"
        "  add HOST...   Add hosts\n"
        "  list          List hosts\n"
        "  get HOST...   Get hosts\n"
        "  rm HOST...    Remove hosts\n",
        end="",
    )


def parse_host_add_options(raw_args: Sequence[str]) -> HostCommandOptions:
    """Parse host add args."""
    names: list[str] = []
    requested_groups: list[str] = []
    dry_run = False
    index = 0
    while index < len(raw_args):
        arg = raw_args[index]
        if arg == "--dry-run":
            dry_run = True
            index += 1
        elif arg == "--groups":
            if index + 1 >= len(raw_args):
                raise HostCommandError("Expected a value after --groups")
            requested_groups.extend(split_csv(raw_args[index + 1]))
            index += 2
        elif arg == "--plan-format":
            if not dry_run:
                raise HostCommandError("--plan-format requires --dry-run.")
            index += 2
        else:
            names.append(arg)
            index += 1
    return HostCommandOptions(tuple(names), tuple(requested_groups), dry_run=dry_run)


def parse_host_rm_options(raw_args: Sequence[str]) -> HostCommandOptions:
    """Parse host rm args."""
    names: list[str] = []
    dry_run = False
    yes = False
    for arg in raw_args:
        if arg == "--dry-run":
            dry_run = True
        elif arg == "--yes":
            yes = True
        elif arg == "--plan-format":
            raise HostCommandError("--plan-format requires --dry-run.")
        else:
            names.append(arg)
    return HostCommandOptions(tuple(names), dry_run=dry_run, yes=yes)


def parse_host_list_options(raw_args: Sequence[str]) -> dict[str, tuple[str, ...] | dict[str, str]]:
    """Parse host list filters."""
    filters: dict[str, tuple[str, ...] | dict[str, str]] = {
        "groups": (),
        "tags": (),
        "variables": {},
    }
    index = 0
    while index < len(raw_args):
        arg = raw_args[index]
        if arg in {"--group", "--tag", "--var"}:
            if index + 1 >= len(raw_args):
                raise HostCommandError(f"Expected a value after {arg}")
            value = raw_args[index + 1]
            if arg == "--group":
                filters["groups"] = split_csv(value)
            elif arg == "--tag":
                filters["tags"] = split_csv(value)
            else:
                filters["variables"] = parse_variable_filters(value)
            index += 2
        else:
            raise HostCommandError(f"Unknown host list option '{arg}'")
    return filters


def parse_variable_filters(value: str) -> dict[str, str]:
    """Parse comma-separated key=value variable filters."""
    parsed: dict[str, str] = {}
    for entry in split_csv(value):
        if "=" not in entry:
            raise HostCommandError(f"Invalid variable filter '{entry}'. Expected key=value.")
        key, variable_value = entry.split("=", 1)
        parsed[key] = variable_value
    return parsed


def split_csv(value: str) -> tuple[str, ...]:
    """Split comma-separated CLI values."""
    return tuple(part.strip() for part in value.split(",") if part.strip())


def find_host_id(connection: Connection, name: str) -> int | None:
    """Return host id by name."""
    return connection.execute(select(hosts.c.id).where(hosts.c.name == name)).scalar_one_or_none()


def create_host(connection: Connection, name: str) -> int:
    """Create a host and return its id."""
    result = connection.execute(hosts.insert().values(name=name))
    return int(cast(Sequence[Any], result.inserted_primary_key)[0])


def find_group_id(connection: Connection, name: str) -> int | None:
    """Return group id by name."""
    return connection.execute(select(groups.c.id).where(groups.c.name == name)).scalar_one_or_none()


def create_group(connection: Connection, name: str) -> int:
    """Create a group and return its id."""
    result = connection.execute(groups.insert().values(name=name))
    return int(cast(Sequence[Any], result.inserted_primary_key)[0])


def ensure_host_group(connection: Connection, host_id: int, group_id: int) -> None:
    """Ensure host/group association exists."""
    exists = connection.execute(
        select(groups_hosts.c.id).where(
            groups_hosts.c.host_id == host_id, groups_hosts.c.group_id == group_id
        )
    ).scalar_one_or_none()
    if exists is None:
        connection.execute(groups_hosts.insert().values(host_id=host_id, group_id=group_id))


def delete_host(connection: Connection, host_id: int) -> None:
    """Delete host and dependent rows."""
    connection.execute(delete(groups_hosts).where(groups_hosts.c.host_id == host_id))
    connection.execute(delete(hostvars).where(hostvars.c.host_id == host_id))
    connection.execute(delete(hosts).where(hosts.c.id == host_id))


def query_hosts(
    connection: Connection,
    *,
    names: tuple[str, ...] = (),
    filters: Mapping[str, tuple[str, ...] | dict[str, str]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return host inventory data."""
    selected_hosts = connection.execute(
        select(hosts.c.id, hosts.c.name).order_by(hosts.c.name)
    ).all()
    if names:
        name_set = set(names)
        selected_hosts = [row for row in selected_hosts if row.name in name_set]

    data: dict[str, dict[str, Any]] = {}
    for row in selected_hosts:
        host_data = host_payload(connection, int(row.id))
        if filters is not None and not host_matches_filters(host_data, filters):
            continue
        data[str(row.name)] = host_data
    return data


def host_payload(connection: Connection, host_id: int) -> dict[str, Any]:
    """Build host payload."""
    group_names = connection.execute(
        select(groups.c.name)
        .select_from(groups_hosts.join(groups, groups_hosts.c.group_id == groups.c.id))
        .where(groups_hosts.c.host_id == host_id)
        .order_by(groups.c.name)
    ).scalars().all()
    variables = connection.execute(
        select(hostvars.c.name, hostvars.c.value)
        .where(hostvars.c.host_id == host_id)
        .order_by(hostvars.c.name)
    ).all()
    payload: dict[str, Any] = {"groups": list(group_names)}
    if variables:
        payload["hostvars"] = {str(row.name): row.value for row in variables}
    return payload


def host_matches_filters(
    host_data: dict[str, Any], filters: Mapping[str, tuple[str, ...] | dict[str, str]]
) -> bool:
    """Return whether host data matches list filters."""
    groups_filter = set(filters.get("groups", ()))
    if groups_filter and not groups_filter.issubset(set(host_data.get("groups", []))):
        return False
    variables_filter = filters.get("variables", {})
    if isinstance(variables_filter, Mapping):
        host_variables = host_data.get("hostvars", {})
        for key, value in variables_filter.items():
            if host_variables.get(key) != value:
                return False
    return True


def dump_data(data: dict[str, Any], output_format: str) -> None:
    """Dump inventory data in Ruby-compatible formats."""
    fmt = output_format.lower()
    if fmt in {"json", "j"}:
        print(json.dumps(data, separators=(",", ":")))
    elif fmt in {"prettyjson", "pjson", "p"}:
        print(json.dumps(data, indent=2))
    elif fmt in {"yaml", "y"}:
        print(yaml.safe_dump(data, sort_keys=False), end="")
    else:
        raise HostCommandError(f"Output format '{output_format}' is not yet supported.")
