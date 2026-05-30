"""Read-only interactive inventory console."""

from __future__ import annotations

import shlex
import sys
from collections.abc import Callable
from typing import TextIO

from sqlalchemy import Connection, select

from moose_inventory.audit import list_audit_events
from moose_inventory.db import (
    Database,
    groups,
    groups_hosts,
    groups_tags,
    hosts,
    hosts_tags,
    tags,
)

COMMANDS = (
    "help",
    "hosts",
    "groups",
    "host NAME",
    "group NAME",
    "tags host NAME",
    "tags group NAME",
    "audit [LIMIT]",
    "quit",
)


def run_console(
    database: Database, input_stream: TextIO | None = None, output: TextIO | None = None
) -> int:
    """Run the small read-only inventory console."""
    input_stream = input_stream or sys.stdin
    output = output or sys.stdout
    output.write("Moose Inventory console (read-only). Type help or quit.\n")
    for line in input_stream:
        parts = parse_command(line, output)
        if parts is None or not parts:
            continue
        if len(parts) == 1 and parts[0] in {"quit", "exit"}:
            break
        dispatch(database, parts, output)
    output.write("Goodbye.\n")
    return 0


def parse_command(line: str, output: TextIO) -> list[str] | None:
    """Parse a console command using shell-style quotes."""
    command = line.strip()
    if not command:
        return []
    try:
        return shlex.split(command)
    except ValueError as exc:
        output.write(f"Invalid command syntax: {exc}\n")
        return None


def dispatch(database: Database, parts: list[str], output: TextIO) -> None:
    """Dispatch one console command."""
    command = parts[0]
    if command == "help":
        render_exact(parts, "help", output, lambda: render_help(output))
    elif command == "hosts":
        render_exact(parts, "hosts", output, lambda: render_hosts(database, output))
    elif command == "groups":
        render_exact(parts, "groups", output, lambda: render_groups(database, output))
    elif command == "host":
        render_entity(database, "host", parts, output)
    elif command == "group":
        render_entity(database, "group", parts, output)
    elif command == "tags":
        render_tags(database, parts, output)
    elif command == "audit":
        render_audit(database, parts, output)
    else:
        output.write(f"Unknown command: {' '.join(parts)}\n")


def render_exact(
    parts: list[str], usage: str, output: TextIO, renderer: Callable[[], None]
) -> None:
    """Render only when no extra args are present."""
    if len(parts) != 1:
        output.write(f"Usage: {usage}\n")
        return
    renderer()


def render_help(output: TextIO) -> None:
    """Render help."""
    for line in ("Commands:", *(f"- {command}" for command in COMMANDS)):
        output.write(f"{line}\n")


def render_hosts(database: Database, output: TextIO) -> None:
    """Render all host names."""
    with database.connect() as connection:
        names = list(connection.execute(select(hosts.c.name).order_by(hosts.c.name)).scalars())
    output.write("No hosts.\n" if not names else f"Hosts: {', '.join(names)}\n")


def render_groups(database: Database, output: TextIO) -> None:
    """Render all group names."""
    with database.connect() as connection:
        names = list(connection.execute(select(groups.c.name).order_by(groups.c.name)).scalars())
    output.write("No groups.\n" if not names else f"Groups: {', '.join(names)}\n")


def render_entity(database: Database, entity_type: str, parts: list[str], output: TextIO) -> None:
    """Render one host or group summary."""
    if len(parts) != 2:
        output.write(f"Usage: {entity_type} NAME\n")
        return
    name = parts[1]
    with database.connect() as connection:
        if entity_type == "host":
            entity_id = connection.execute(
                select(hosts.c.id).where(hosts.c.name == name)
            ).scalar_one_or_none()
            if entity_id is None:
                output.write(f"Host '{name}' not found.\n")
                return
            group_names = list(
                connection.execute(
                    select(groups.c.name)
                    .select_from(groups_hosts.join(groups, groups_hosts.c.group_id == groups.c.id))
                    .where(groups_hosts.c.host_id == int(entity_id))
                    .order_by(groups.c.name)
                ).scalars()
            )
            tag_names = list_host_tags(connection, int(entity_id))
            output.write(f"Host: {name}\n")
            output.write(f"Groups: {', '.join(group_names)}\n")
            output.write(f"Tags: {', '.join(tag_names)}\n")
        else:
            entity_id = connection.execute(
                select(groups.c.id).where(groups.c.name == name)
            ).scalar_one_or_none()
            if entity_id is None:
                output.write(f"Group '{name}' not found.\n")
                return
            host_names = list(
                connection.execute(
                    select(hosts.c.name)
                    .select_from(groups_hosts.join(hosts, groups_hosts.c.host_id == hosts.c.id))
                    .where(groups_hosts.c.group_id == int(entity_id))
                    .order_by(hosts.c.name)
                ).scalars()
            )
            tag_names = list_group_tags(connection, int(entity_id))
            output.write(f"Group: {name}\n")
            output.write(f"Hosts: {', '.join(host_names)}\n")
            output.write(f"Tags: {', '.join(tag_names)}\n")


def render_tags(database: Database, parts: list[str], output: TextIO) -> None:
    """Render tags for a host or group."""
    if len(parts) != 3 or parts[1] not in {"host", "group"}:
        output.write("Usage: tags host|group NAME\n")
        return
    entity_type, name = parts[1], parts[2]
    with database.connect() as connection:
        if entity_type == "host":
            entity_id = connection.execute(
                select(hosts.c.id).where(hosts.c.name == name)
            ).scalar_one_or_none()
            if entity_id is None:
                output.write(f"Host '{name}' not found.\n")
                return
            tag_names = list_host_tags(connection, int(entity_id))
        else:
            entity_id = connection.execute(
                select(groups.c.id).where(groups.c.name == name)
            ).scalar_one_or_none()
            if entity_id is None:
                output.write(f"Group '{name}' not found.\n")
                return
            tag_names = list_group_tags(connection, int(entity_id))
    if tag_names:
        output.write(f"{', '.join(tag_names)}\n")
    else:
        output.write(f"{entity_type.capitalize()} '{name}' has no tags.\n")


def render_audit(database: Database, parts: list[str], output: TextIO) -> None:
    """Render recent audit events."""
    limit = audit_limit(parts[1]) if len(parts) <= 2 else None
    if limit is None:
        output.write("Usage: audit [LIMIT]\n")
        return
    events = list_audit_events(database, limit=limit)
    if not events:
        output.write("No audit events recorded.\n")
        return
    for event in events:
        output.write(
            f"{event['id']} {event['created_at']} {event['command']} "
            f"{event['entity_type']}={event['entity_name']}\n"
        )


def audit_limit(value: str | None) -> int | None:
    """Parse audit limit."""
    if value is None:
        return 10
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def list_host_tags(connection: Connection, host_id: int) -> list[str]:
    """Return sorted host tag names."""
    rows = connection.execute(
        select(tags.c.name)
        .select_from(hosts_tags.join(tags, hosts_tags.c.tag_id == tags.c.id))
        .where(hosts_tags.c.host_id == host_id)
        .order_by(tags.c.name)
    ).scalars()
    return [str(name) for name in rows]


def list_group_tags(connection: Connection, group_id: int) -> list[str]:
    """Return sorted group tag names."""
    rows = connection.execute(
        select(tags.c.name)
        .select_from(groups_tags.join(tags, groups_tags.c.tag_id == tags.c.id))
        .where(groups_tags.c.group_id == group_id)
        .order_by(tags.c.name)
    ).scalars()
    return [str(name) for name in rows]
