"""Host command operations and renderers."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping, Sequence
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from typing import Any, cast

import yaml
from sqlalchemy import Connection, delete, select

from moose_inventory.config import RuntimeOptions
from moose_inventory.db import Database, groups, groups_hosts, hosts, hosts_tags, hostvars, tags

AUTOMATIC_GROUP = "ungrouped"


@dataclass(frozen=True)
class HostCommandOptions:
    """Parsed host command options."""

    names: tuple[str, ...]
    groups: tuple[str, ...] = ()
    dry_run: bool = False
    yes: bool = False
    output_format: str | None = None
    plan_format: str | None = None


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
            if "--plan-format" in args[1:] and action != "add":
                return render_dry_run_plan(
                    f"host {action}", args[1:], lambda stripped: self._run_action(action, stripped)
                )
            return self._run_action(action, args[1:])
        except HostCommandError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    def _run_action(self, action: str, raw_args: Sequence[str]) -> int:
        """Run a host action without top-level plan interception."""
        if action == "add":
            return self.add(raw_args)
        if action == "list":
            return self.list_hosts(raw_args)
        if action == "get":
            return self.get(raw_args)
        if action == "rm":
            return self.rm(raw_args)
        if action == "addgroup":
            return self.addgroup(raw_args)
        if action == "rmgroup":
            return self.rmgroup(raw_args)
        if action == "addvar":
            return self.addvar(raw_args)
        if action == "rmvar":
            return self.rmvar(raw_args)
        if action in {"listvar", "listvars"}:
            return self.listvars(raw_args)
        if action == "addtag":
            return self.addtag(raw_args)
        if action == "rmtag":
            return self.rmtag(raw_args)
        if action == "listtags":
            return self.listtags(raw_args)

        print(f"ERROR: host action '{action}' is not implemented.", file=sys.stderr)
        return 1

    def add(self, raw_args: Sequence[str]) -> int:
        """Add one or more hosts."""
        options = parse_host_add_options(raw_args)
        if not options.names:
            print("ERROR: Wrong number of arguments, 0 for 1 or more.", file=sys.stderr)
            return 1
        if options.plan_format:
            return self.add_plan(options)

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

    def add_plan(self, options: HostCommandOptions) -> int:
        """Render a machine-readable dry-run plan for host add."""
        events: list[dict[str, Any]] = []
        with self.database.connect() as connection:
            for name in options.names:
                events.append({"type": "host_started", "payload": {"name": name}})
                if find_host_id(connection, name) is None:
                    events.append({"type": "creating_host", "payload": {"name": name}})
                else:
                    events.append({"type": "host_exists", "payload": {"name": name}})
                events.append({"type": "ok", "payload": {"indent": 4}})
                target_groups = options.groups or (AUTOMATIC_GROUP,)
                for group_name in target_groups:
                    automatic = group_name == AUTOMATIC_GROUP and not options.groups
                    event_type = "adding_automatic_group" if automatic else "adding_group"
                    events.append(
                        {"type": event_type, "payload": {"host": name, "group": group_name}}
                    )
                    events.append({"type": "ok", "payload": {"indent": 4}})
                events.append({"type": "host_complete", "payload": {}})
        events.append({"type": "dry_run_summary", "payload": {}})
        plan = {
            "command": "host add",
            "dry_run": True,
            "changes_applied": False,
            "events": events,
        }
        dump_data(plan, options.plan_format or "json")
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

    def addgroup(self, raw_args: Sequence[str]) -> int:
        """Associate a host with one or more groups."""
        options = parse_relation_options(raw_args, destructive=False)
        if len(options.names) < 2:
            print(
                f"ERROR: Wrong number of arguments, {len(options.names)} for 2 or more.",
                file=sys.stderr,
            )
            return 1
        host_name = options.names[0].lower()
        group_names = tuple(name.lower() for name in options.names[1:])
        if AUTOMATIC_GROUP in group_names:
            print(
                "ERROR: Cannot manually manipulate the automatic group 'ungrouped'.",
                file=sys.stderr,
            )
            return 1

        with self.database.engine.begin() as connection:
            print(f"Associate host '{host_name}' with groups '{','.join(group_names)}':")
            print(f"  - Retrieve host '{host_name}'...")
            host_id = find_host_id(connection, host_name)
            if host_id is None:
                print(
                    "An error occurred during a transaction, any changes have been rolled back.",
                    file=sys.stderr,
                )
                print(
                    f"ERROR: The host '{host_name}' was not found in the database.",
                    file=sys.stderr,
                )
                return 1
            print("    - OK")
            for group_name in group_names:
                print(f"  - Add association {{host:{host_name} <-> group:{group_name}}}...")
                group_id = find_group_id(connection, group_name)
                if group_id is None:
                    print(
                        f"WARNING: Group '{group_name}' does not exist and will be created.",
                        end="",
                        file=sys.stderr,
                    )
                    print("    - Group does not exist, creating now...")
                    if not options.dry_run:
                        group_id = create_group(connection, group_name)
                    print("      - OK")
                if group_id is not None and host_group_exists(connection, host_id, group_id):
                    print(
                        f"WARNING: Association {{host:{host_name} <-> group:{group_name}}} "
                        "already exists, skipping.",
                        end="",
                        file=sys.stderr,
                    )
                    print("    - Already exists, skipping.")
                elif not options.dry_run and group_id is not None:
                    ensure_host_group(connection, host_id, group_id)
                print("    - OK")
            if not options.dry_run and host_has_nonautomatic_group(connection, host_id):
                automatic_id = find_group_id(connection, AUTOMATIC_GROUP)
                if (
                    automatic_id is not None
                    and host_group_exists(connection, host_id, automatic_id)
                ):
                    print(
                        f"  - Remove automatic association "
                        f"{{host:{host_name} <-> group:ungrouped}}..."
                    )
                    remove_host_group(connection, host_id, automatic_id)
                    print("    - OK")
            elif options.dry_run:
                print("Dry run complete. No changes applied.")
            print("  - All OK")
        print("Succeeded")
        return 0

    def addvar(self, raw_args: Sequence[str]) -> int:
        """Add or update host variables."""
        options = parse_relation_options(raw_args, destructive=False)
        if len(options.names) < 2:
            print(
                f"ERROR: Wrong number of arguments, {len(options.names)} for 2 or more.",
                file=sys.stderr,
            )
            return 1
        host_name = options.names[0].lower()
        variables = tuple(dict.fromkeys(options.names[1:]))
        return self._change_vars(
            entity_label="host",
            entity_name=host_name,
            variables=variables,
            remove=False,
            dry_run=options.dry_run,
        )

    def rmvar(self, raw_args: Sequence[str]) -> int:
        """Remove host variables."""
        options = parse_relation_options(raw_args, destructive=True)
        if len(options.names) < 2:
            print(
                f"ERROR: Wrong number of arguments, {len(options.names)} for 2 or more.",
                file=sys.stderr,
            )
            return 1
        host_name = options.names[0].lower()
        variables = tuple(dict.fromkeys(options.names[1:]))
        if not options.yes and not options.dry_run:
            print(
                f"ERROR: host rmvar {host_name} {','.join(variables)} is destructive. "
                "Re-run with --yes to confirm, or use --dry-run to preview.",
                file=sys.stderr,
            )
            return 1
        return self._change_vars(
            entity_label="host",
            entity_name=host_name,
            variables=variables,
            remove=True,
            dry_run=options.dry_run,
        )

    def listvars(self, raw_args: Sequence[str]) -> int:
        """List variables for one or more hosts."""
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
            data = query_host_vars(connection, names)
        if self.runtime.ansible:
            if names[0] not in data:
                print(f"WARNING: The host {names[0]} does not exist.", file=sys.stderr)
                dump_data({"_meta": {"hostvars": {}}}, self.runtime.output_format)
            else:
                payload: dict[str, Any] = dict(data[names[0]])
                payload["_meta"] = {"hostvars": data}
                dump_data(payload, self.runtime.output_format)
        else:
            dump_data(data, self.runtime.output_format)
        return 0

    def _change_vars(
        self,
        *,
        entity_label: str,
        entity_name: str,
        variables: tuple[str, ...],
        remove: bool,
        dry_run: bool,
    ) -> int:
        action = "Remove variable(s)" if remove else "Add variables"
        preposition = "from" if remove else "to"
        verb = "remove" if remove else "add"
        print(f"{action} '{','.join(variables)}' {preposition} {entity_label} '{entity_name}':")
        print(f"  - retrieve {entity_label} '{entity_name}'...")
        with self.database.engine.begin() as connection:
            host_id = find_host_id(connection, entity_name)
            if host_id is None:
                print(
                    "An error occurred during a transaction, any changes have been rolled back.",
                    file=sys.stderr,
                )
                print(f"ERROR: The host '{entity_name}' does not exist.", file=sys.stderr)
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
                        remove_host_variable(connection, host_id, key)
                else:
                    existing = find_host_variable_id(connection, host_id, key)
                    if existing is not None and not dry_run:
                        print("    - already exists, applying as an update...")
                        update_host_variable(connection, int(existing), value)
                    elif existing is not None:
                        print("    - already exists, applying as an update...")
                    elif not dry_run:
                        create_host_variable(connection, host_id, key, value)
                print("    - OK")
            print("  - all OK")
        if dry_run:
            print("Dry run complete. No changes applied.")
        print("Succeeded.")
        return 0

    def addtag(self, raw_args: Sequence[str]) -> int:
        """Add metadata tags to a host."""
        options = parse_tag_options(raw_args, destructive=False)
        if len(options.names) < 2:
            print(
                f"ERROR: Wrong number of arguments, {len(options.names)} for 2 or more.",
                file=sys.stderr,
            )
            return 1
        host_name = options.names[0].lower()
        tag_names = normalize_tags(options.names[1:])
        with self.database.engine.begin() as connection:
            host_id = find_host_id(connection, host_name)
            if host_id is None:
                print(f"ERROR: The host '{host_name}' does not exist.", file=sys.stderr)
                return 1
            changed = (
                tag_names if options.dry_run else add_host_tags(connection, host_id, tag_names)
            )
        if options.dry_run:
            print("Dry run complete. No changes applied.")
        print(f"Added host tag(s) to '{host_name}': {', '.join(changed)}.")
        return 0

    def rmtag(self, raw_args: Sequence[str]) -> int:
        """Remove metadata tags from a host."""
        options = parse_tag_options(raw_args, destructive=True)
        if len(options.names) < 2:
            print(
                f"ERROR: Wrong number of arguments, {len(options.names)} for 2 or more.",
                file=sys.stderr,
            )
            return 1
        host_name = options.names[0].lower()
        tag_names = normalize_tags(options.names[1:])
        if not options.yes and not options.dry_run:
            print(
                f"ERROR: host rmtag {host_name} {','.join(tag_names)} is destructive. "
                "Re-run with --yes to confirm, or use --dry-run to preview.",
                file=sys.stderr,
            )
            return 1
        with self.database.engine.begin() as connection:
            host_id = find_host_id(connection, host_name)
            if host_id is None:
                print(f"ERROR: The host '{host_name}' does not exist.", file=sys.stderr)
                return 1
            changed = (
                tag_names if options.dry_run else remove_host_tags(connection, host_id, tag_names)
            )
        if options.dry_run:
            print("Dry run complete. No changes applied.")
        print(f"Removed host tag(s) from '{host_name}': {', '.join(changed)}.")
        return 0

    def listtags(self, raw_args: Sequence[str]) -> int:
        """List metadata tags for a host."""
        options = parse_tag_options(raw_args, destructive=False, allow_format=True)
        if len(options.names) != 1:
            print(
                f"ERROR: Wrong number of arguments, {len(options.names)} for 1.",
                file=sys.stderr,
            )
            return 1
        host_name = options.names[0].lower()
        with self.database.connect() as connection:
            host_id = find_host_id(connection, host_name)
            if host_id is None:
                print(f"ERROR: The host '{host_name}' does not exist.", file=sys.stderr)
                return 1
            tag_names = list_host_tags(connection, host_id)
        fmt = options.output_format or self.runtime.output_format
        if options.output_format:
            dump_data({"host": host_name, "tags": tag_names}, fmt)
        elif tag_names:
            print(f"Host '{host_name}' tags: {', '.join(tag_names)}")
        else:
            print(f"Host '{host_name}' has no tags.")
        return 0

    def rmgroup(self, raw_args: Sequence[str]) -> int:
        """Dissociate a host from one or more groups."""
        options = parse_relation_options(raw_args, destructive=True)
        if len(options.names) < 2:
            print(
                f"ERROR: Wrong number of arguments, {len(options.names)} for 2 or more.",
                file=sys.stderr,
            )
            return 1
        host_name = options.names[0].lower()
        group_names = tuple(name.lower() for name in options.names[1:])
        if AUTOMATIC_GROUP in group_names:
            print(
                "ERROR: Cannot manually manipulate the automatic group 'ungrouped'.",
                file=sys.stderr,
            )
            return 1
        if not options.yes and not options.dry_run:
            print(
                f"ERROR: host rmgroup {host_name} {','.join(group_names)} is destructive. "
                "Re-run with --yes to confirm, or use --dry-run to preview.",
                file=sys.stderr,
            )
            return 1

        with self.database.engine.begin() as connection:
            print(f"Dissociate host '{host_name}' from groups '{','.join(group_names)}':")
            print(f"  - Retrieve host '{host_name}'...")
            host_id = find_host_id(connection, host_name)
            if host_id is None:
                print(
                    "An error occurred during a transaction, any changes have been rolled back.",
                    file=sys.stderr,
                )
                print(
                    f"ERROR: The host '{host_name}' was not found in the database.",
                    file=sys.stderr,
                )
                return 1
            print("    - OK")
            for group_name in group_names:
                print(f"  - Remove association {{host:{host_name} <-> group:{group_name}}}...")
                group_id = find_group_id(connection, group_name)
                if group_id is None or not host_group_exists(connection, host_id, group_id):
                    print(
                        f"WARNING: Association {{host:{host_name} <-> group:{group_name}}} "
                        "doesn't exist, skipping.",
                        file=sys.stderr,
                    )
                    print("    - Doesn't exist, skipping.")
                elif not options.dry_run:
                    remove_host_group(connection, host_id, group_id)
                print("    - OK")
            if not options.dry_run and not host_has_any_group(connection, host_id):
                automatic_id = find_group_id(connection, AUTOMATIC_GROUP)
                if automatic_id is None:
                    automatic_id = create_group(connection, AUTOMATIC_GROUP)
                print(
                    f"  - Add automatic association {{host:{host_name} <-> group:ungrouped}}..."
                )
                ensure_host_group(connection, host_id, automatic_id)
                print("    - OK")
            if options.dry_run:
                print("Dry run complete. No changes applied.")
            print("  - All OK")
        print("Succeeded")
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
    plan_format: str | None = None
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
            if index + 1 >= len(raw_args):
                raise HostCommandError("Expected a value after --plan-format")
            plan_format = raw_args[index + 1]
            index += 2
        else:
            names.append(arg)
            index += 1
    if plan_format is not None:
        if not dry_run:
            raise HostCommandError("--plan-format requires --dry-run.")
        validate_plan_format(plan_format)
    return HostCommandOptions(
        tuple(names), tuple(requested_groups), dry_run=dry_run, plan_format=plan_format
    )


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


def parse_relation_options(raw_args: Sequence[str], *, destructive: bool) -> HostCommandOptions:
    """Parse host/group relation command args."""
    names: list[str] = []
    dry_run = False
    yes = False
    index = 0
    while index < len(raw_args):
        arg = raw_args[index]
        if arg == "--dry-run":
            dry_run = True
        elif destructive and arg == "--yes":
            yes = True
        elif arg == "--plan-format":
            if not dry_run:
                raise HostCommandError("--plan-format requires --dry-run.")
            index += 1
        else:
            names.append(arg)
        index += 1
    return HostCommandOptions(tuple(names), dry_run=dry_run, yes=yes)


def parse_tag_options(
    raw_args: Sequence[str], *, destructive: bool, allow_format: bool = False
) -> HostCommandOptions:
    """Parse host tag command args."""
    names: list[str] = []
    yes = False
    dry_run = False
    output_format: str | None = None
    index = 0
    while index < len(raw_args):
        arg = raw_args[index]
        if arg == "--dry-run":
            dry_run = True
        elif destructive and arg == "--yes":
            yes = True
        elif arg == "--plan-format":
            if not dry_run:
                raise HostCommandError("--plan-format requires --dry-run.")
            if index + 1 >= len(raw_args):
                raise HostCommandError("Expected a value after --plan-format")
            index += 1
        elif allow_format and arg == "--format":
            if index + 1 >= len(raw_args):
                raise HostCommandError("Expected a value after --format")
            output_format = raw_args[index + 1]
            index += 1
        else:
            names.append(arg)
        index += 1
    return HostCommandOptions(tuple(names), dry_run=dry_run, yes=yes, output_format=output_format)


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


def host_group_exists(connection: Connection, host_id: int, group_id: int) -> bool:
    """Return whether host/group association exists."""
    return (
        connection.execute(
            select(groups_hosts.c.id).where(
                groups_hosts.c.host_id == host_id, groups_hosts.c.group_id == group_id
            )
        ).scalar_one_or_none()
        is not None
    )


def remove_host_group(connection: Connection, host_id: int, group_id: int) -> None:
    """Remove host/group association."""
    connection.execute(
        delete(groups_hosts).where(
            groups_hosts.c.host_id == host_id, groups_hosts.c.group_id == group_id
        )
    )


def host_has_nonautomatic_group(connection: Connection, host_id: int) -> bool:
    """Return whether host has any non-automatic group."""
    return (
        connection.execute(
            select(groups_hosts.c.id)
            .select_from(groups_hosts.join(groups, groups_hosts.c.group_id == groups.c.id))
            .where(groups_hosts.c.host_id == host_id, groups.c.name != AUTOMATIC_GROUP)
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )


def host_has_any_group(connection: Connection, host_id: int) -> bool:
    """Return whether host has any group."""
    return (
        connection.execute(
            select(groups_hosts.c.id).where(groups_hosts.c.host_id == host_id).limit(1)
        ).scalar_one_or_none()
        is not None
    )


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
    tag_names = list_host_tags(connection, host_id)
    payload: dict[str, Any] = {"groups": list(group_names)}
    if tag_names:
        payload["tags"] = tag_names
    if variables:
        payload["hostvars"] = {str(row.name): row.value for row in variables}
    return payload


def parse_variable(variable: str) -> tuple[str, str]:
    """Parse a Ruby-compatible key=value variable."""
    parts = variable.split("=")
    if variable.startswith("=") or variable.endswith("=") or len(parts) != 2:
        raise HostCommandError(f"Incorrect format in '{{{variable}}}'. Expected 'key=value'.")
    return parts[0], parts[1]


def parse_variable_for_remove(variable: str) -> tuple[str, str]:
    """Parse a Ruby-compatible variable removal token."""
    if variable.startswith("=") or variable.count("=") > 1:
        raise HostCommandError(
            f"Incorrect format in {{{variable}}}. Expected 'key' or 'key=value'."
        )
    key, _, value = variable.partition("=")
    return key, value


def find_host_variable_id(connection: Connection, host_id: int, name: str) -> int | None:
    """Find a host variable id by host and name."""
    value = connection.execute(
        select(hostvars.c.id).where(hostvars.c.host_id == host_id, hostvars.c.name == name)
    ).scalar_one_or_none()
    return cast(int | None, value)


def create_host_variable(connection: Connection, host_id: int, name: str, value: str) -> None:
    """Create a host variable."""
    connection.execute(hostvars.insert().values(host_id=host_id, name=name, value=value))


def update_host_variable(connection: Connection, variable_id: int, value: str) -> None:
    """Update a host variable."""
    connection.execute(hostvars.update().where(hostvars.c.id == variable_id).values(value=value))


def remove_host_variable(connection: Connection, host_id: int, name: str) -> None:
    """Remove a host variable by name."""
    connection.execute(
        delete(hostvars).where(hostvars.c.host_id == host_id, hostvars.c.name == name)
    )


def query_host_vars(connection: Connection, names: tuple[str, ...]) -> dict[str, dict[str, str]]:
    """Return host variables grouped by host."""
    selected_hosts = connection.execute(
        select(hosts.c.id, hosts.c.name).order_by(hosts.c.name)
    ).all()
    name_set = set(names)
    data: dict[str, dict[str, str]] = {}
    for row in selected_hosts:
        if row.name not in name_set:
            continue
        variables = connection.execute(
            select(hostvars.c.name, hostvars.c.value)
            .where(hostvars.c.host_id == row.id)
            .order_by(hostvars.c.name)
        ).all()
        data[str(row.name)] = {str(var.name): str(var.value) for var in variables}
    return data


def normalize_tags(values: Sequence[str]) -> tuple[str, ...]:
    """Normalize and dedupe tag names using Ruby-compatible rules."""
    normalized: list[str] = []
    for value in values:
        tag = value.strip().lower()
        if tag and tag not in normalized:
            normalized.append(tag)
    return tuple(normalized)


def find_or_create_tag(connection: Connection, name: str) -> int:
    """Find or create a tag and return its id."""
    tag_id = connection.execute(select(tags.c.id).where(tags.c.name == name)).scalar_one_or_none()
    if tag_id is not None:
        return int(tag_id)
    result = connection.execute(tags.insert().values(name=name))
    return int(cast(Sequence[Any], result.inserted_primary_key)[0])


def add_host_tags(connection: Connection, host_id: int, tag_names: Sequence[str]) -> list[str]:
    """Add tags to a host and return changed tag names."""
    changed: list[str] = []
    for tag_name in tag_names:
        tag_id = find_or_create_tag(connection, tag_name)
        exists = connection.execute(
            select(hosts_tags.c.id).where(
                hosts_tags.c.host_id == host_id, hosts_tags.c.tag_id == tag_id
            )
        ).scalar_one_or_none()
        if exists is None:
            connection.execute(hosts_tags.insert().values(host_id=host_id, tag_id=tag_id))
            changed.append(tag_name)
    return changed


def remove_host_tags(connection: Connection, host_id: int, tag_names: Sequence[str]) -> list[str]:
    """Remove tags from a host and return changed tag names."""
    changed: list[str] = []
    for tag_name in tag_names:
        tag_id = connection.execute(
            select(tags.c.id).where(tags.c.name == tag_name)
        ).scalar_one_or_none()
        if tag_id is None:
            continue
        result = connection.execute(
            delete(hosts_tags).where(
                hosts_tags.c.host_id == host_id, hosts_tags.c.tag_id == int(tag_id)
            )
        )
        if result.rowcount:
            changed.append(tag_name)
    return changed


def list_host_tags(connection: Connection, host_id: int) -> list[str]:
    """List host tag names sorted by name."""
    return list(
        connection.execute(
            select(tags.c.name)
            .select_from(hosts_tags.join(tags, hosts_tags.c.tag_id == tags.c.id))
            .where(hosts_tags.c.host_id == host_id)
            .order_by(tags.c.name)
        ).scalars()
    )


def host_matches_filters(
    host_data: dict[str, Any], filters: Mapping[str, tuple[str, ...] | dict[str, str]]
) -> bool:
    """Return whether host data matches list filters."""
    groups_filter = set(filters.get("groups", ()))
    if groups_filter and not groups_filter.issubset(set(host_data.get("groups", []))):
        return False
    tags_filter = set(filters.get("tags", ()))
    if tags_filter and not tags_filter.issubset(set(host_data.get("tags", []))):
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


def render_dry_run_plan(
    command: str,
    raw_args: Sequence[str],
    runner: Callable[[Sequence[str]], int],
) -> int:
    """Render machine-readable dry-run output for mutating commands.

    Most Ruby-compatible mutators already have human-readable ``--dry-run`` output. The
    plan form wraps that preview in a stable structural envelope without applying changes.
    """
    stripped_args, plan_format = extract_plan_format(raw_args)
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = runner(stripped_args)
    stdout_lines = stdout.getvalue().splitlines()
    stderr_lines = stderr.getvalue().splitlines()
    events: list[dict[str, Any]] = []
    for line in stdout_lines:
        event_type = (
            "dry_run_summary" if line == "Dry run complete. No changes applied." else "stdout"
        )
        events.append({"type": event_type, "payload": {"line": line}})
    for line in stderr_lines:
        events.append({"type": "stderr", "payload": {"line": line}})
    dump_data(
        {
            "command": command,
            "dry_run": True,
            "changes_applied": False,
            "exit_code": exit_code,
            "stdout": stdout_lines,
            "stderr": stderr_lines,
            "events": events,
        },
        plan_format,
    )
    return exit_code


def extract_plan_format(raw_args: Sequence[str]) -> tuple[tuple[str, ...], str]:
    """Remove --plan-format from args and return its requested output format."""
    if "--dry-run" not in raw_args:
        raise HostCommandError("--plan-format requires --dry-run.")
    stripped: list[str] = []
    plan_format: str | None = None
    index = 0
    while index < len(raw_args):
        arg = raw_args[index]
        if arg == "--plan-format":
            if index + 1 >= len(raw_args):
                raise HostCommandError("Expected a value after --plan-format")
            if plan_format is not None:
                raise HostCommandError("--plan-format may only be specified once.")
            plan_format = raw_args[index + 1]
            index += 2
            continue
        stripped.append(arg)
        index += 1
    if plan_format is None:
        raise HostCommandError("Expected --plan-format.")
    validate_plan_format(plan_format)
    return tuple(stripped), plan_format


def validate_plan_format(plan_format: str) -> None:
    """Validate machine-readable plan formats early for clearer errors."""
    if plan_format.lower() not in {"json", "j", "prettyjson", "pjson", "p", "yaml", "y"}:
        raise HostCommandError(f"Output format '{plan_format}' is not yet supported.")
