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
    host_group_exists,
    host_has_any_group,
    parse_variable,
    parse_variable_for_remove,
    remove_host_group,
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
            if action == "addhost":
                return self.addhost(args[1:])
            if action == "rmhost":
                return self.rmhost(args[1:])
            if action == "addchild":
                return self.addchild(args[1:])
            if action == "rmchild":
                return self.rmchild(args[1:])
            if action == "addvar":
                return self.addvar(args[1:])
            if action == "rmvar":
                return self.rmvar(args[1:])
            if action in {"listvar", "listvars"}:
                return self.listvars(args[1:])
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

    def addchild(self, raw_args: Sequence[str]) -> int:
        """Associate a parent group with one or more child groups."""
        options = parse_group_relation_options(raw_args, destructive=False)
        if len(options.names) < 2:
            print(
                f"ERROR: Wrong number of arguments, {len(options.names)} for 2 or more.",
                file=sys.stderr,
            )
            return 1
        parent_name = options.names[0].lower()
        child_names = tuple(name.lower() for name in options.names[1:])
        if AUTOMATIC_GROUP in (parent_name, *child_names):
            print(
                "ERROR: Cannot manually manipulate the automatic group 'ungrouped'.",
                file=sys.stderr,
            )
            return 1

        warnings = False
        with self.database.engine.begin() as connection:
            print(
                f"Associate parent group '{parent_name}' with child group(s) "
                f"'{','.join(child_names)}':"
            )
            print(f"  - retrieve group '{parent_name}'...")
            parent_id = find_group_id(connection, parent_name)
            if parent_id is None:
                print(f"ERROR: The group '{parent_name}' does not exist.", file=sys.stderr)
                print(
                    "An error occurred during a transaction, any changes have been rolled back.",
                    file=sys.stderr,
                )
                return 1
            print("    - OK")
            for child_name in child_names:
                print(
                    f"  - add association {{group:{parent_name} <-> group:{child_name}}}..."
                )
                child_id = find_group_id(connection, child_name)
                if child_id is not None and group_child_exists(connection, parent_id, child_id):
                    warnings = True
                    print(
                        f"WARNING: Association {{group:{parent_name} <-> group:{child_name}}} "
                        "already exists, skipping.",
                        file=sys.stderr,
                    )
                    print("    - already exists, skipping.")
                    print("    - OK")
                    continue
                if child_id is not None and would_create_group_cycle(
                    connection, parent_id, child_id
                ):
                    print(
                        "An error occurred during a transaction, any changes have been "
                        "rolled back.",
                        file=sys.stderr,
                    )
                    print(
                        f"ERROR: circular group relationship rejected: {parent_name} -> "
                        f"{child_name}.",
                        file=sys.stderr,
                    )
                    return 1
                if child_id is None:
                    warnings = True
                    print(
                        f"WARNING: Group '{child_name}' does not exist and will be created.",
                        file=sys.stderr,
                    )
                    print("    - child group does not exist, creating now...")
                    if not options.dry_run:
                        child_id = create_group(connection, child_name)
                    print("      - OK")
                if not options.dry_run and child_id is not None:
                    ensure_group_child(connection, parent_id, child_id)
                print("    - OK")
            if options.dry_run:
                print("Dry run complete. No changes applied.")
            print("  - all OK")
        print("Succeeded, with warnings." if warnings else "Succeeded.")
        return 0

    def rmchild(self, raw_args: Sequence[str]) -> int:
        """Dissociate a parent group from one or more child groups."""
        options = parse_group_relation_options(raw_args, destructive=True)
        if len(options.names) < 2:
            print(
                f"ERROR: Wrong number of arguments, {len(options.names)} for 2 or more.",
                file=sys.stderr,
            )
            return 1
        parent_name = options.names[0].lower()
        child_names = tuple(name.lower() for name in options.names[1:])
        if AUTOMATIC_GROUP in (parent_name, *child_names):
            print(
                "ERROR: Cannot manually manipulate the automatic group 'ungrouped'.",
                file=sys.stderr,
            )
            return 1
        if not options.yes and not options.dry_run:
            print(
                f"ERROR: group rmchild {parent_name} {','.join(child_names)} is destructive. "
                "Re-run with --yes to confirm, or use --dry-run to preview.",
                file=sys.stderr,
            )
            return 1

        warnings = False
        with self.database.engine.begin() as connection:
            print(
                f"Dissociate parent group '{parent_name}' from child group(s) "
                f"'{','.join(child_names)}':"
            )
            print(f"  - retrieve group '{parent_name}'...")
            parent_id = find_group_id(connection, parent_name)
            if parent_id is None:
                print(f"ERROR: The group '{parent_name}' does not exist.", file=sys.stderr)
                print(
                    "An error occurred during a transaction, any changes have been rolled back.",
                    file=sys.stderr,
                )
                return 1
            print("    - OK")
            for child_name in child_names:
                print(
                    f"  - remove association {{group:{parent_name} <-> group:{child_name}}}..."
                )
                child_id = find_group_id(connection, child_name)
                if child_id is None or not group_child_exists(connection, parent_id, child_id):
                    warnings = True
                    print(
                        f"WARNING: Association {{group:{parent_name} <-> group:{child_name}}} "
                        "does not exist, skipping.",
                        file=sys.stderr,
                    )
                    print("    - doesn't exist, skipping.")
                    print("    - OK")
                    continue
                if not options.dry_run:
                    remove_group_child(connection, parent_id, child_id)
                print("    - OK")
                if options.recursive:
                    delete_orphaned_group(
                        connection,
                        child_id,
                        child_name,
                        dry_run=options.dry_run,
                        ignored_parent_id=parent_id,
                    )
            if options.dry_run:
                print("Dry run complete. No changes applied.")
            print("  - all OK")
        print("Succeeded, with warnings." if warnings else "Succeeded.")
        return 0

    def addvar(self, raw_args: Sequence[str]) -> int:
        """Add or update group variables."""
        options = parse_group_relation_options(raw_args, destructive=False)
        if len(options.names) < 2:
            print(
                f"ERROR: Wrong number of arguments, {len(options.names)} for 2 or more.",
                file=sys.stderr,
            )
            return 1
        group_name = options.names[0].lower()
        variables = tuple(dict.fromkeys(options.names[1:]))
        return self._change_vars(
            entity_name=group_name,
            variables=variables,
            remove=False,
            dry_run=options.dry_run,
        )

    def rmvar(self, raw_args: Sequence[str]) -> int:
        """Remove group variables."""
        options = parse_group_relation_options(raw_args, destructive=True)
        if len(options.names) < 2:
            print(
                f"ERROR: Wrong number of arguments, {len(options.names)} for 2 or more.",
                file=sys.stderr,
            )
            return 1
        group_name = options.names[0].lower()
        variables = tuple(dict.fromkeys(options.names[1:]))
        if not options.yes and not options.dry_run:
            print(
                f"ERROR: group rmvar {group_name} {','.join(variables)} is destructive. "
                "Re-run with --yes to confirm, or use --dry-run to preview.",
                file=sys.stderr,
            )
            return 1
        return self._change_vars(
            entity_name=group_name,
            variables=variables,
            remove=True,
            dry_run=options.dry_run,
        )

    def listvars(self, raw_args: Sequence[str]) -> int:
        """List variables for one or more groups."""
        names = tuple(arg.lower() for arg in raw_args if not arg.startswith("--"))
        if self.runtime.ansible and len(names) != 1:
            print(
                f"ERROR: Wrong number of arguments for Ansible mode, {len(names)} for 1.",
                file=sys.stderr,
            )
            return 1
        if not self.runtime.ansible and not names:
            print("ERROR: Wrong number of arguments, 0 for 1 or more.", file=sys.stderr)
            return 1
        with self.database.connect() as connection:
            data = query_group_vars(connection, names)
        if self.runtime.ansible:
            if names[0] not in data:
                print(f"WARNING: The Group {names[0]} does not exist.", end="", file=sys.stderr)
                dump_data({}, self.runtime.output_format)
            else:
                dump_data(data[names[0]], self.runtime.output_format)
        else:
            dump_data(data, self.runtime.output_format)
        return 0

    def _change_vars(
        self,
        *,
        entity_name: str,
        variables: tuple[str, ...],
        remove: bool,
        dry_run: bool,
    ) -> int:
        action = "Remove variable(s)" if remove else "Add variables"
        preposition = "from" if remove else "to"
        verb = "remove" if remove else "add"
        print(f"{action} '{','.join(variables)}' {preposition} group '{entity_name}':")
        print(f"  - retrieve group '{entity_name}'...")
        with self.database.engine.begin() as connection:
            group_id = find_group_id(connection, entity_name)
            if group_id is None:
                print(
                    "An error occurred during a transaction, any changes have been rolled back.",
                    file=sys.stderr,
                )
                print(f"ERROR: The group '{entity_name}' does not exist.", file=sys.stderr)
                return 1
            print("    - OK")
            for variable in variables:
                print(f"  - {verb} variable '{variable}'...")
                try:
                    if remove:
                        key, value = parse_variable_for_remove(variable)
                    else:
                        key, value = parse_variable(variable)
                except HostCommandError as exc:
                    print(
                        "An error occurred during a transaction, "
                        "any changes have been rolled back.",
                        file=sys.stderr,
                    )
                    print(f"ERROR: {exc}", file=sys.stderr)
                    return 1
                if remove:
                    if not dry_run:
                        remove_group_variable(connection, group_id, key)
                else:
                    existing = find_group_variable_id(connection, group_id, key)
                    if existing is not None:
                        print("    - already exists, applying as an update...")
                        if not dry_run:
                            update_group_variable(connection, int(existing), value)
                    elif not dry_run:
                        create_group_variable(connection, group_id, key, value)
                print("    - OK")
            print("  - all OK")
        if dry_run:
            print("Dry run complete. No changes applied.")
        print("Succeeded.")
        return 0

    def addhost(self, raw_args: Sequence[str]) -> int:
        """Associate a group with one or more hosts."""
        options = parse_group_relation_options(raw_args, destructive=False)
        if len(options.names) < 2:
            print(
                f"ERROR: Wrong number of arguments, {len(options.names)} for 2 or more.",
                file=sys.stderr,
            )
            return 1
        group_name = options.names[0].lower()
        host_names = tuple(name.lower() for name in options.names[1:])
        if group_name == AUTOMATIC_GROUP:
            print(
                "ERROR: Cannot manually manipulate the automatic group 'ungrouped'.",
                file=sys.stderr,
            )
            return 1

        warnings = False
        with self.database.engine.begin() as connection:
            print(f"Associate group '{group_name}' with host(s) '{','.join(host_names)}':")
            print(f"  - retrieve group '{group_name}'...")
            group_id = find_group_id(connection, group_name)
            if group_id is None:
                print(f"ERROR: The group '{group_name}' does not exist.", file=sys.stderr)
                print(
                    "An error occurred during a transaction, any changes have been rolled back.",
                    file=sys.stderr,
                )
                return 1
            print("    - OK")
            for host_name in host_names:
                print(f"  - add association {{group:{group_name} <-> host:{host_name}}}...")
                host_id = find_host_id(connection, host_name)
                if host_id is None:
                    warnings = True
                    print(
                        f"WARNING: Host '{host_name}' does not exist and will be created.",
                        file=sys.stderr,
                    )
                    print("    - host does not exist, creating now...")
                    if not options.dry_run:
                        host_id = create_host(connection, host_name)
                    print("      - OK")
                if host_id is not None and host_group_exists(connection, host_id, group_id):
                    warnings = True
                    print(
                        f"WARNING: Association {{group:{group_name} <-> host:{host_name}}} "
                        "already exists, skipping.",
                        file=sys.stderr,
                    )
                    print("    - already exists, skipping.")
                elif not options.dry_run and host_id is not None:
                    ensure_host_group(connection, host_id, group_id)
                print("    - OK")
                automatic_id = find_group_id(connection, AUTOMATIC_GROUP)
                if (
                    not options.dry_run
                    and host_id is not None
                    and automatic_id is not None
                    and host_group_exists(connection, host_id, automatic_id)
                ):
                    print(
                        f"  - remove automatic association "
                        f"{{group:ungrouped <-> host:{host_name}}}..."
                    )
                    remove_host_group(connection, host_id, automatic_id)
                    print("    - OK")
            if options.dry_run:
                print("Dry run complete. No changes applied.")
            print("  - all OK")
        print("Succeeded, with warnings." if warnings else "Succeeded.")
        return 0

    def rmhost(self, raw_args: Sequence[str]) -> int:
        """Dissociate a group from one or more hosts."""
        options = parse_group_relation_options(raw_args, destructive=True)
        if len(options.names) < 2:
            print(
                f"ERROR: Wrong number of arguments, {len(options.names)} for 2 or more.",
                file=sys.stderr,
            )
            return 1
        group_name = options.names[0].lower()
        host_names = tuple(name.lower() for name in options.names[1:])
        if group_name == AUTOMATIC_GROUP:
            print(
                "ERROR: Cannot manually manipulate the automatic group 'ungrouped'.",
                file=sys.stderr,
            )
            return 1
        if not options.yes and not options.dry_run:
            print(
                f"ERROR: group rmhost {group_name} {','.join(host_names)} is destructive. "
                "Re-run with --yes to confirm, or use --dry-run to preview.",
                file=sys.stderr,
            )
            return 1

        warnings = False
        with self.database.engine.begin() as connection:
            print(f"Dissociate group '{group_name}' from host(s) '{','.join(host_names)}':")
            print(f"  - retrieve group '{group_name}'...")
            group_id = find_group_id(connection, group_name)
            if group_id is None:
                print(f"ERROR: The group '{group_name}' does not exist.", file=sys.stderr)
                print(
                    "An error occurred during a transaction, any changes have been rolled back.",
                    file=sys.stderr,
                )
                return 1
            print("    - OK")
            for host_name in host_names:
                print(f"  - remove association {{group:{group_name} <-> host:{host_name}}}...")
                host_id = find_host_id(connection, host_name)
                if host_id is None or not host_group_exists(connection, host_id, group_id):
                    warnings = True
                    print(
                        f"WARNING: Association {{group:{group_name} <-> host:{host_name}}} "
                        "doesn't exist, skipping.",
                        file=sys.stderr,
                    )
                    print("    - doesn't exist, skipping.")
                elif not options.dry_run:
                    remove_host_group(connection, host_id, group_id)
                print("    - OK")
                if not options.dry_run and host_id is not None and not host_has_any_group(
                    connection, host_id
                ):
                    automatic_id = find_group_id(connection, AUTOMATIC_GROUP)
                    if automatic_id is None:
                        automatic_id = create_group(connection, AUTOMATIC_GROUP)
                    print(
                        f"  - add automatic association "
                        f"{{group:ungrouped <-> host:{host_name}}}..."
                    )
                    ensure_host_group(connection, host_id, automatic_id)
                    print("    - OK")
            if options.dry_run:
                print("Dry run complete. No changes applied.")
            print("  - all OK")
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


def parse_group_relation_options(
    raw_args: Sequence[str], *, destructive: bool
) -> GroupCommandOptions:
    """Parse group/host relation command args."""
    names: list[str] = []
    dry_run = False
    yes = False
    recursive = False
    index = 0
    while index < len(raw_args):
        arg = raw_args[index]
        if arg == "--dry-run":
            dry_run = True
        elif destructive and arg == "--yes":
            yes = True
        elif destructive and arg == "--delete-orphans":
            recursive = True
        elif arg == "--plan-format":
            if not dry_run:
                raise HostCommandError("--plan-format requires --dry-run.")
            index += 1
        else:
            names.append(arg)
        index += 1
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


def group_child_exists(connection: Connection, parent_id: int, child_id: int) -> bool:
    """Return whether a parent/child group association exists."""
    return (
        connection.execute(
            select(groups_groups.c.id).where(
                groups_groups.c.parent_id == parent_id,
                groups_groups.c.child_id == child_id,
            )
        ).scalar_one_or_none()
        is not None
    )


def ensure_group_child(connection: Connection, parent_id: int, child_id: int) -> None:
    """Create a parent/child group association if missing."""
    if not group_child_exists(connection, parent_id, child_id):
        connection.execute(groups_groups.insert().values(parent_id=parent_id, child_id=child_id))


def remove_group_child(connection: Connection, parent_id: int, child_id: int) -> None:
    """Remove a parent/child group association."""
    connection.execute(
        delete(groups_groups).where(
            groups_groups.c.parent_id == parent_id,
            groups_groups.c.child_id == child_id,
        )
    )


def would_create_group_cycle(connection: Connection, parent_id: int, child_id: int) -> bool:
    """Return whether adding parent -> child would create a cycle."""
    if parent_id == child_id:
        return True
    stack = [child_id]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if current == parent_id:
            return True
        if current in seen:
            continue
        seen.add(current)
        children = connection.execute(
            select(groups_groups.c.child_id).where(groups_groups.c.parent_id == current)
        ).scalars()
        stack.extend(int(child) for child in children)
    return False


def delete_orphaned_group(
    connection: Connection,
    group_id: int,
    group_name: str,
    *,
    dry_run: bool,
    ignored_parent_id: int | None = None,
) -> None:
    """Recursively delete orphaned child groups after planned dissociation."""
    if group_name == AUTOMATIC_GROUP:
        return
    remaining_parent = connection.execute(
        select(groups_groups.c.parent_id).where(groups_groups.c.child_id == group_id)
    ).scalars().all()
    if any(parent_id != ignored_parent_id for parent_id in remaining_parent):
        return

    print(f"  - Recursively delete orphaned group '{group_name}'...")
    child_rows = connection.execute(
        select(groups_groups.c.child_id, groups.c.name)
        .select_from(groups_groups.join(groups, groups_groups.c.child_id == groups.c.id))
        .where(groups_groups.c.parent_id == group_id)
        .order_by(groups.c.name)
    ).all()
    for child in child_rows:
        print(f"    - Remove association {{group:{group_name} <-> group:{child.name}}}...")
        if not dry_run:
            remove_group_child(connection, group_id, int(child.child_id))
        print("      - OK")
        delete_orphaned_group(
            connection,
            int(child.child_id),
            str(child.name),
            dry_run=dry_run,
            ignored_parent_id=group_id,
        )

    host_ids = connection.execute(
        select(groups_hosts.c.host_id).where(groups_hosts.c.group_id == group_id)
    ).scalars().all()
    automatic_id = find_group_id(connection, AUTOMATIC_GROUP)
    if automatic_id is None and not dry_run:
        automatic_id = create_group(connection, AUTOMATIC_GROUP)
    for host_id in host_ids:
        group_count = connection.execute(
            select(groups_hosts.c.id).where(groups_hosts.c.host_id == host_id)
        ).all()
        if len(group_count) == 1:
            host_name = connection.execute(
                select(hosts.c.name).where(hosts.c.id == host_id)
            ).scalar_one()
            print(f"    - Adding automatic association {{group:ungrouped <-> host:{host_name}}}...")
            if not dry_run and automatic_id is not None:
                ensure_host_group(connection, int(host_id), automatic_id)
            print("      - OK")
    print(f"    - Destroy group '{group_name}'...")
    if not dry_run:
        delete_group(connection, group_id)
    print("      - OK")


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
    child_names = connection.execute(
        select(groups.c.name)
        .select_from(groups_groups.join(groups, groups_groups.c.child_id == groups.c.id))
        .where(groups_groups.c.parent_id == group_id)
        .order_by(groups.c.name)
    ).scalars().all()
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
    if child_names:
        payload["children"] = list(child_names)
    if host_names:
        payload["hosts"] = list(host_names)
    if variables:
        payload["groupvars"] = {str(row.name): row.value for row in variables}
    return payload


def find_group_variable_id(connection: Connection, group_id: int, name: str) -> int | None:
    """Find a group variable id by group and name."""
    value = connection.execute(
        select(groupvars.c.id).where(groupvars.c.group_id == group_id, groupvars.c.name == name)
    ).scalar_one_or_none()
    return cast(int | None, value)


def create_group_variable(connection: Connection, group_id: int, name: str, value: str) -> None:
    """Create a group variable."""
    connection.execute(groupvars.insert().values(group_id=group_id, name=name, value=value))


def update_group_variable(connection: Connection, variable_id: int, value: str) -> None:
    """Update a group variable."""
    connection.execute(groupvars.update().where(groupvars.c.id == variable_id).values(value=value))


def remove_group_variable(connection: Connection, group_id: int, name: str) -> None:
    """Remove a group variable by name."""
    connection.execute(
        delete(groupvars).where(groupvars.c.group_id == group_id, groupvars.c.name == name)
    )


def query_group_vars(connection: Connection, names: tuple[str, ...]) -> dict[str, dict[str, str]]:
    """Return group variables grouped by group."""
    selected_groups = connection.execute(
        select(groups.c.id, groups.c.name).order_by(groups.c.name)
    ).all()
    name_set = set(names)
    data: dict[str, dict[str, str]] = {}
    for row in selected_groups:
        if row.name not in name_set:
            continue
        variables = connection.execute(
            select(groupvars.c.name, groupvars.c.value)
            .where(groupvars.c.group_id == row.id)
            .order_by(groupvars.c.name)
        ).all()
        data[str(row.name)] = {str(var.name): str(var.value) for var in variables}
    return data
