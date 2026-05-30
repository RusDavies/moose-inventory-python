"""Group command operations and renderers."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import Connection, delete, select

from moose_inventory.config import RuntimeOptions
from moose_inventory.db import Database, groups, groups_groups, groups_hosts, groupvars, hosts
from moose_inventory.host_commands import (
    AUTOMATIC_GROUP,
    HostCommandError,
    create_host,
    dump_data,
    ensure_host_group,
    find_group_id,
    find_host_id,
    split_csv,
)


@dataclass(frozen=True)
class GroupCommandOptions:
    """Parsed group command options."""

    names: tuple[str, ...]
    hosts: tuple[str, ...] = ()
    dry_run: bool = False
    yes: bool = False
    recursive: bool = False


class GroupCommands:
    """Implementation of core group CLI commands."""

    def __init__(self, database: Database, runtime: RuntimeOptions) -> None:
        self.database = database
        self.runtime = runtime

    def run(self) -> int:
        """Dispatch the selected group subcommand."""
        args = list(self.runtime.argv[1:])
        if not args or args[0] in {"help", "--help", "-h"}:
            print_group_usage()
            return 0

        action = args[0]
        try:
            if action == "add":
                return self.add(args[1:])
            if action == "list":
                return self.list_groups(args[1:])
            if action == "get":
                return self.get(args[1:])
            if action == "rm":
                return self.rm(args[1:])
        except HostCommandError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        print(f"ERROR: group action '{action}' is not implemented.", file=sys.stderr)
        return 1

    def add(self, raw_args: Sequence[str]) -> int:
        """Add one or more groups."""
        options = parse_group_add_options(raw_args)
        if not options.names:
            print("ERROR: Wrong number of arguments, 0 for 1 or more.", file=sys.stderr)
            return 1
        if AUTOMATIC_GROUP in options.names:
            print(
                "ERROR: Cannot manually manipulate the automatic group 'ungrouped'",
                file=sys.stderr,
            )
            return 1

        warnings = False
        with self.database.engine.begin() as connection:
            for name in options.names:
                print(f"Add group '{name}':")
                print("  - create group...")
                group_id = find_group_id(connection, name)
                if group_id is None and not options.dry_run:
                    group_id = create_group(connection, name)
                    print("    - OK")
                elif group_id is None:
                    print("    - OK")
                else:
                    warnings = True
                    print(
                        f"WARNING: Group '{name}' already exists, skipping creation.",
                        file=sys.stderr,
                    )
                    print("    - already exists, skipping.")
                    print("    - OK")

                for host_name in options.hosts:
                    print(f"  - add association {{group:{name} <-> host:{host_name}}}...")
                    host_id = find_host_id(connection, host_name)
                    if host_id is None:
                        warnings = True
                        print(
                            f"WARNING: Host '{host_name}' doesn't exist, but will be created.",
                            file=sys.stderr,
                        )
                        print("    - host doesn't exist, creating now...")
                        if not options.dry_run:
                            host_id = create_host(connection, host_name)
                        print("      - OK")
                    if not options.dry_run and group_id is not None and host_id is not None:
                        ensure_host_group(connection, host_id, group_id)
                    print("    - OK")
                print("  - all OK")

        if options.dry_run:
            print("Dry run complete. No changes applied.")
        print("Succeeded, with warnings." if warnings else "Succeeded")
        return 0

    def list_groups(self, raw_args: Sequence[str]) -> int:
        """List groups."""
        if raw_args:
            raise HostCommandError(f"Unknown group list option '{raw_args[0]}'")
        with self.database.connect() as connection:
            data = query_groups(connection)
        dump_data(data, self.runtime.output_format)
        return 0

    def get(self, raw_args: Sequence[str]) -> int:
        """Get one or more groups."""
        names = tuple(arg for arg in raw_args if not arg.startswith("--"))
        if not names:
            print("ERROR: Wrong number of arguments, 0 for 1 or more", file=sys.stderr)
            return 1
        with self.database.connect() as connection:
            data = query_groups(connection, names=names)
        dump_data(data, self.runtime.output_format)
        return 0

    def rm(self, raw_args: Sequence[str]) -> int:
        """Remove one or more groups."""
        options = parse_group_rm_options(raw_args)
        if not options.names:
            print("ERROR: Wrong number of arguments, 0 for 1 or more.", file=sys.stderr)
            return 1
        if AUTOMATIC_GROUP in options.names:
            print(
                "ERROR: Cannot manually manipulate the automatic group 'ungrouped'",
                file=sys.stderr,
            )
            return 1
        if not options.yes and not options.dry_run:
            joined = ",".join(options.names)
            print(
                f"ERROR: group rm {joined} is destructive. Re-run with --yes to confirm, "
                "or use --dry-run to preview.",
                file=sys.stderr,
            )
            return 1

        warnings = False
        with self.database.engine.begin() as connection:
            for name in options.names:
                print(f"Remove group '{name}':")
                print(f"  - Retrieve group '{name}'...")
                group_id = find_group_id(connection, name)
                if group_id is None:
                    warnings = True
                    print(f"WARNING: Group '{name}' does not exist, skipping.", file=sys.stderr)
                    print("    - No such group, skipping.")
                    print("    - OK")
                    print("  - All OK")
                    continue
                print("    - OK")
                print(f"  - Destroy group '{name}'...")
                if not options.dry_run:
                    delete_group(connection, group_id)
                print("    - OK")
                print("  - All OK")

        if options.dry_run:
            print("Dry run complete. No changes applied.")
        print("Succeeded, with warnings." if warnings else "Succeeded.")
        return 0


def print_group_usage() -> None:
    """Print group command usage."""
    print(
        "Usage: moose-inventory group ACTION [ARGS]\n\n"
        "Group commands:\n"
        "  add GROUP...  Add groups\n"
        "  list          List groups\n"
        "  get GROUP...  Get groups\n"
        "  rm GROUP...   Remove groups\n",
        end="",
    )


def parse_group_add_options(raw_args: Sequence[str]) -> GroupCommandOptions:
    """Parse group add args."""
    names: list[str] = []
    requested_hosts: list[str] = []
    dry_run = False
    index = 0
    while index < len(raw_args):
        arg = raw_args[index]
        if arg == "--dry-run":
            dry_run = True
            index += 1
        elif arg == "--hosts":
            if index + 1 >= len(raw_args):
                raise HostCommandError("Expected a value after --hosts")
            requested_hosts.extend(split_csv(raw_args[index + 1]))
            index += 2
        elif arg == "--plan-format":
            if not dry_run:
                raise HostCommandError("--plan-format requires --dry-run.")
            index += 2
        else:
            names.append(arg)
            index += 1
    return GroupCommandOptions(tuple(names), tuple(requested_hosts), dry_run=dry_run)


def parse_group_rm_options(raw_args: Sequence[str]) -> GroupCommandOptions:
    """Parse group rm args."""
    names: list[str] = []
    dry_run = False
    yes = False
    recursive = False
    skip_next = False
    for index, arg in enumerate(raw_args):
        if skip_next:
            skip_next = False
            continue
        if arg == "--dry-run":
            dry_run = True
        elif arg == "--yes":
            yes = True
        elif arg == "--recursive":
            recursive = True
        elif arg == "--plan-format":
            if not dry_run:
                raise HostCommandError("--plan-format requires --dry-run.")
            skip_next = index + 1 < len(raw_args)
        else:
            names.append(arg)
    return GroupCommandOptions(tuple(names), dry_run=dry_run, yes=yes, recursive=recursive)


def create_group(connection: Connection, name: str) -> int:
    """Create a group and return its id."""
    result = connection.execute(groups.insert().values(name=name))
    return int(cast(Sequence[Any], result.inserted_primary_key)[0])


def delete_group(connection: Connection, group_id: int) -> None:
    """Delete a group and dependent rows."""
    host_ids = connection.execute(
        select(groups_hosts.c.host_id).where(groups_hosts.c.group_id == group_id)
    ).scalars().all()
    connection.execute(delete(groups_hosts).where(groups_hosts.c.group_id == group_id))
    connection.execute(delete(groups_groups).where(groups_groups.c.parent_id == group_id))
    connection.execute(delete(groups_groups).where(groups_groups.c.child_id == group_id))
    connection.execute(delete(groupvars).where(groupvars.c.group_id == group_id))
    connection.execute(delete(groups).where(groups.c.id == group_id))
    automatic_id = find_group_id(connection, AUTOMATIC_GROUP)
    if automatic_id is None:
        automatic_id = create_group(connection, AUTOMATIC_GROUP)
    for host_id in host_ids:
        remaining = connection.execute(
            select(groups_hosts.c.id).where(groups_hosts.c.host_id == host_id).limit(1)
        ).scalar_one_or_none()
        if remaining is None:
            ensure_host_group(connection, int(host_id), automatic_id)


def query_groups(
    connection: Connection, *, names: tuple[str, ...] = ()
) -> dict[str, dict[str, Any]]:
    """Return group inventory data."""
    selected_groups = connection.execute(
        select(groups.c.id, groups.c.name).order_by(groups.c.name)
    ).all()
    if names:
        name_set = set(names)
        selected_groups = [row for row in selected_groups if row.name in name_set]

    data: dict[str, dict[str, Any]] = {}
    for row in selected_groups:
        data[str(row.name)] = group_payload(connection, int(row.id))
    return data


def group_payload(connection: Connection, group_id: int) -> dict[str, Any]:
    """Build group payload."""
    host_names = connection.execute(
        select(hosts.c.name)
        .select_from(groups_hosts.join(hosts, groups_hosts.c.host_id == hosts.c.id))
        .where(groups_hosts.c.group_id == group_id)
        .order_by(hosts.c.name)
    ).scalars().all()
    variables = connection.execute(
        select(groupvars.c.name, groupvars.c.value)
        .where(groupvars.c.group_id == group_id)
        .order_by(groupvars.c.name)
    ).all()
    payload: dict[str, Any] = {}
    if host_names:
        payload["hosts"] = list(host_names)
    if variables:
        payload["groupvars"] = {str(row.name): row.value for row in variables}
    return payload
