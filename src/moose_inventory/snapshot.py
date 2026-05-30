"""Inventory snapshot export/import support."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import Connection, select

from moose_inventory.db import (
    Database,
    groups,
    groups_groups,
    groups_hosts,
    groups_tags,
    groupvars,
    hosts,
    hosts_tags,
    hostvars,
    tags,
)
from moose_inventory.group_commands import ensure_group_child
from moose_inventory.host_commands import (
    ensure_host_group,
    find_group_id,
    find_host_id,
    find_or_create_tag,
)

SNAPSHOT_VERSION = 1


class SnapshotError(RuntimeError):
    """Raised when an inventory snapshot is invalid."""


@dataclass(frozen=True)
class ImportResult:
    """Snapshot import counters."""

    created_hosts: int = 0
    created_groups: int = 0
    updated_variables: int = 0
    associations: int = 0


def export_snapshot(database: Database) -> dict[str, Any]:
    """Export the current inventory snapshot."""
    with database.connect() as connection:
        return {
            "version": SNAPSHOT_VERSION,
            "hosts": export_hosts(connection),
            "groups": export_groups(connection),
        }


def import_snapshot(database: Database, snapshot: object) -> ImportResult:
    """Validate and apply a snapshot additively."""
    normalized = validate_snapshot(snapshot)
    with database.engine.begin() as connection:
        return apply_snapshot(connection, normalized)


def preview_snapshot(database: Database, snapshot: object) -> dict[str, Any]:
    """Validate and preview an additive snapshot import."""
    normalized = validate_snapshot(snapshot)
    with database.connect() as connection:
        return build_preview(connection, normalized)


def export_hosts(connection: Connection) -> dict[str, dict[str, Any]]:
    """Export hosts by name."""
    rows = connection.execute(select(hosts.c.id, hosts.c.name).order_by(hosts.c.name)).all()
    return {str(row.name): host_payload(connection, int(row.id)) for row in rows}


def host_payload(connection: Connection, host_id: int) -> dict[str, Any]:
    """Build a host snapshot payload."""
    return {
        "groups": list_host_groups(connection, host_id),
        "tags": list_entity_tags(connection, hosts_tags, "host_id", host_id),
        "vars": list_variables(connection, hostvars, "host_id", host_id),
    }


def export_groups(connection: Connection) -> dict[str, dict[str, Any]]:
    """Export groups by name."""
    rows = connection.execute(select(groups.c.id, groups.c.name).order_by(groups.c.name)).all()
    return {str(row.name): group_payload(connection, int(row.id)) for row in rows}


def group_payload(connection: Connection, group_id: int) -> dict[str, Any]:
    """Build a group snapshot payload."""
    return {
        "children": list_group_children(connection, group_id),
        "tags": list_entity_tags(connection, groups_tags, "group_id", group_id),
        "vars": list_variables(connection, groupvars, "group_id", group_id),
    }


def list_host_groups(connection: Connection, host_id: int) -> list[str]:
    """List group names for a host."""
    return list(
        connection.execute(
            select(groups.c.name)
            .select_from(groups_hosts.join(groups, groups_hosts.c.group_id == groups.c.id))
            .where(groups_hosts.c.host_id == host_id)
            .order_by(groups.c.name)
        ).scalars()
    )


def list_group_children(connection: Connection, group_id: int) -> list[str]:
    """List child group names for a group."""
    return list(
        connection.execute(
            select(groups.c.name)
            .select_from(groups_groups.join(groups, groups_groups.c.child_id == groups.c.id))
            .where(groups_groups.c.parent_id == group_id)
            .order_by(groups.c.name)
        ).scalars()
    )


def list_entity_tags(
    connection: Connection, association_table: Any, entity_column: str, entity_id: int
) -> list[str]:
    """List tag names for a host or group."""
    return list(
        connection.execute(
            select(tags.c.name)
            .select_from(association_table.join(tags, association_table.c.tag_id == tags.c.id))
            .where(association_table.c[entity_column] == entity_id)
            .order_by(tags.c.name)
        ).scalars()
    )


def list_variables(
    connection: Connection, variable_table: Any, entity_column: str, entity_id: int
) -> dict[str, str]:
    """List variables for a host or group."""
    rows = connection.execute(
        select(variable_table.c.name, variable_table.c.value)
        .where(variable_table.c[entity_column] == entity_id)
        .order_by(variable_table.c.name)
    ).all()
    return {str(row.name): str(row.value) for row in rows}


def validate_snapshot(snapshot: object) -> dict[str, Any]:
    """Validate and normalize a snapshot mapping."""
    normalized = stringify_keys(snapshot)
    if not isinstance(normalized, dict):
        invalid("snapshot must be a mapping")
    typed = cast(dict[str, Any], normalized)
    if int(typed.get("version", 0)) != SNAPSHOT_VERSION:
        invalid("version must be 1")
    if not isinstance(typed.get("hosts"), dict):
        invalid("hosts must be a mapping")
    if not isinstance(typed.get("groups"), dict):
        invalid("groups must be a mapping")
    validate_hosts(typed)
    validate_groups(typed)
    validate_group_cycles(cast(dict[str, Any], typed["groups"]))
    return typed


def validate_hosts(snapshot: dict[str, Any]) -> None:
    """Validate host payloads."""
    groups_map = cast(dict[str, Any], snapshot["groups"])
    for name, payload in cast(dict[str, Any], snapshot["hosts"]).items():
        validate_entity_payload(name, payload, "host", {"groups", "tags", "vars"})
        for group_name in array_value(payload, "groups", f"host '{name}' groups"):
            if group_name not in groups_map:
                invalid(f"host '{name}' references unknown group '{group_name}'")


def validate_groups(snapshot: dict[str, Any]) -> None:
    """Validate group payloads."""
    groups_map = cast(dict[str, Any], snapshot["groups"])
    for name, payload in groups_map.items():
        validate_entity_payload(name, payload, "group", {"children", "tags", "vars"})
        for child_name in array_value(payload, "children", f"group '{name}' children"):
            if child_name not in groups_map:
                invalid(f"group '{name}' references unknown child group '{child_name}'")


def validate_entity_payload(name: str, payload: object, label: str, allowed_keys: set[str]) -> None:
    """Validate common host/group payload shape."""
    if not str(name).strip():
        invalid(f"{label} name cannot be empty")
    if not isinstance(payload, dict):
        invalid(f"{label} '{name}' must be a mapping")
    payload_map = cast(dict[str, Any], payload)
    unsupported = set(payload_map) - allowed_keys
    if unsupported:
        invalid(f"{label} '{name}' has unsupported fields: {', '.join(sorted(unsupported))}")
    variables = payload_map.get("vars", {})
    if not isinstance(variables, dict):
        invalid(f"{label} '{name}' vars must be a mapping")
    for variable_name in variables:
        if not str(variable_name).strip():
            invalid(f"{label} '{name}' variable name cannot be empty")
    payload_map["tags"] = normalize_tags(array_value(payload_map, "tags", f"{label} '{name}' tags"))


def validate_group_cycles(groups_map: dict[str, Any]) -> None:
    """Reject cyclic group hierarchy in snapshot input, matching Ruby import validation."""
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in visiting:
            invalid(f"group hierarchy contains a cycle at '{name}'")
        visiting.add(name)
        for child_name in array_value(groups_map[name], "children", f"group '{name}' children"):
            visit(child_name)
        visiting.remove(name)
        visited.add(name)

    for group_name in groups_map:
        visit(group_name)


def stringify_keys(value: object) -> object:
    """Deep-stringify mapping keys while rejecting normalized duplicates."""
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, entry in value.items():
            normalized_key = str(key)
            if normalized_key in result:
                invalid(f"duplicate normalized key '{normalized_key}'")
            result[normalized_key] = stringify_keys(entry)
        return result
    if isinstance(value, list):
        return [stringify_keys(entry) for entry in value]
    return value


def array_value(payload: object, key: str, label: str) -> list[str]:
    """Return a string array from a payload."""
    if not isinstance(payload, dict):
        invalid(f"{label} must be a list")
    payload_map = cast(dict[str, Any], payload)
    value = payload_map.get(key, [])
    if not isinstance(value, list):
        invalid(f"{label} must be a list")
    return [str(entry) for entry in value]


def normalize_tags(values: list[str]) -> list[str]:
    """Normalize tag names like Ruby import validation."""
    normalized: list[str] = []
    for value in values:
        tag = value.strip().lower()
        if tag and tag not in normalized:
            normalized.append(tag)
    return normalized


def apply_snapshot(connection: Connection, snapshot: dict[str, Any]) -> ImportResult:
    """Apply a validated snapshot."""
    created_groups = sum(1 for name in snapshot["groups"] if ensure_group(connection, name) is None)
    created_hosts = sum(1 for name in snapshot["hosts"] if ensure_host(connection, name) is None)
    updated_variables = 0
    associations = 0
    for name, payload in snapshot["groups"].items():
        group_id = cast(int, find_group_id(connection, name))
        updated_variables += apply_variables(
            connection, groupvars, "group_id", group_id, payload.get("vars", {})
        )
        associations += apply_tags(
            connection, groups_tags, "group_id", group_id, payload.get("tags", [])
        )
        for child_name in array_value(payload, "children", f"group '{name}' children"):
            child_id = cast(int, find_group_id(connection, child_name))
            before = group_child_exists(connection, group_id, child_id)
            ensure_group_child(connection, group_id, child_id)
            associations += 0 if before else 1
    for name, payload in snapshot["hosts"].items():
        host_id = cast(int, find_host_id(connection, name))
        updated_variables += apply_variables(
            connection, hostvars, "host_id", host_id, payload.get("vars", {})
        )
        associations += apply_tags(
            connection, hosts_tags, "host_id", host_id, payload.get("tags", [])
        )
        for group_name in array_value(payload, "groups", f"host '{name}' groups"):
            group_id = cast(int, find_group_id(connection, group_name))
            before = host_group_exists(connection, host_id, group_id)
            ensure_host_group(connection, host_id, group_id)
            associations += 0 if before else 1
    return ImportResult(created_hosts, created_groups, updated_variables, associations)


def ensure_group(connection: Connection, name: str) -> int | None:
    """Ensure a group exists; return existing id or None when created."""
    group_id = find_group_id(connection, name)
    if group_id is not None:
        return group_id
    connection.execute(groups.insert().values(name=name))
    return None


def ensure_host(connection: Connection, name: str) -> int | None:
    """Ensure a host exists; return existing id or None when created."""
    host_id = find_host_id(connection, name)
    if host_id is not None:
        return host_id
    connection.execute(hosts.insert().values(name=name))
    return None


def apply_variables(
    connection: Connection,
    variable_table: Any,
    entity_column: str,
    entity_id: int,
    variables: object,
) -> int:
    """Insert/update variables and return changed count."""
    changed = 0
    if not isinstance(variables, dict):
        return changed
    for name, value in variables.items():
        existing = connection.execute(
            select(variable_table.c.id, variable_table.c.value).where(
                variable_table.c[entity_column] == entity_id, variable_table.c.name == name
            )
        ).first()
        if existing is None:
            connection.execute(
                variable_table.insert().values(
                    **{entity_column: entity_id, "name": name, "value": str(value)}
                )
            )
            changed += 1
        elif str(existing.value) != str(value):
            connection.execute(
                variable_table.update()
                .where(variable_table.c.id == int(existing.id))
                .values(value=str(value))
            )
            changed += 1
    return changed


def apply_tags(
    connection: Connection,
    association_table: Any,
    entity_column: str,
    entity_id: int,
    tag_names: list[str],
) -> int:
    """Apply tag associations and return newly added count."""
    added = 0
    for tag_name in normalize_tags([str(value) for value in tag_names]):
        tag_id = find_or_create_tag(connection, tag_name)
        exists = connection.execute(
            select(association_table.c.id).where(
                association_table.c[entity_column] == entity_id,
                association_table.c.tag_id == tag_id,
            )
        ).scalar_one_or_none()
        if exists is None:
            connection.execute(
                association_table.insert().values(**{entity_column: entity_id, "tag_id": tag_id})
            )
            added += 1
    return added


def host_group_exists(connection: Connection, host_id: int, group_id: int) -> bool:
    """Return whether a host/group association exists."""
    return (
        connection.execute(
            select(groups_hosts.c.id).where(
                groups_hosts.c.host_id == host_id, groups_hosts.c.group_id == group_id
            )
        ).scalar_one_or_none()
        is not None
    )


def group_child_exists(connection: Connection, parent_id: int, child_id: int) -> bool:
    """Return whether a group child association exists."""
    return (
        connection.execute(
            select(groups_groups.c.id).where(
                groups_groups.c.parent_id == parent_id, groups_groups.c.child_id == child_id
            )
        ).scalar_one_or_none()
        is not None
    )


def build_preview(connection: Connection, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build a Ruby-shaped import preview."""
    preview = empty_preview()
    for name, payload in snapshot["groups"].items():
        group_id = find_group_id(connection, name)
        add_create_or_unchanged(preview, "groups", name, group_id is None, "groups_created")
        preview_variables(
            preview,
            connection,
            groupvars,
            "group_id",
            group_id,
            "group",
            name,
            payload.get("vars", {}),
        )
        preview_tags(
            preview,
            connection,
            groups_tags,
            "group_id",
            group_id,
            "group",
            name,
            payload.get("tags", []),
        )
        for child_name in array_value(payload, "children", f"group '{name}' children"):
            child_id = find_group_id(connection, child_name)
            changed = (
                group_id is None
                or child_id is None
                or not group_child_exists(connection, group_id, child_id)
            )
            add_association_preview(
                preview, "group_children", {"source": name, "target": child_name}, changed
            )
    for name, payload in snapshot["hosts"].items():
        host_id = find_host_id(connection, name)
        add_create_or_unchanged(preview, "hosts", name, host_id is None, "hosts_created")
        preview_variables(
            preview, connection, hostvars, "host_id", host_id, "host", name, payload.get("vars", {})
        )
        preview_tags(
            preview,
            connection,
            hosts_tags,
            "host_id",
            host_id,
            "host",
            name,
            payload.get("tags", []),
        )
        for group_name in array_value(payload, "groups", f"host '{name}' groups"):
            group_id = find_group_id(connection, group_name)
            changed = (
                host_id is None
                or group_id is None
                or not host_group_exists(connection, host_id, group_id)
            )
            add_association_preview(
                preview, "host_groups", {"source": name, "target": group_name}, changed
            )
    preview_ignored(connection, snapshot, preview)
    return preview


def empty_preview() -> dict[str, Any]:
    """Return a Ruby-shaped empty preview document."""
    return {
        "schema_version": "snapshot-import-preview-v1",
        "changes_applied": False,
        "summary": {
            "hosts_created": 0,
            "groups_created": 0,
            "variables_changed": 0,
            "associations_added": 0,
            "unchanged": 0,
            "ignored_existing_hosts": 0,
            "ignored_existing_groups": 0,
            "destructive_changes": 0,
        },
        "creates": {"hosts": [], "groups": []},
        "updates": {"host_vars": [], "group_vars": []},
        "associations": {"host_groups": [], "group_children": [], "tags": []},
        "unchanged": {
            "hosts": [],
            "groups": [],
            "host_vars": [],
            "group_vars": [],
            "associations": [],
        },
        "ignored": {"existing_hosts_not_in_snapshot": [], "existing_groups_not_in_snapshot": []},
        "unsupported_destructive_implications": [],
    }


def add_create_or_unchanged(
    preview: dict[str, Any], key: str, name: str, created: bool, counter: str
) -> None:
    """Add an entity create/unchanged preview entry."""
    if created:
        preview["creates"][key].append(name)
        preview["summary"][counter] += 1
    else:
        preview["unchanged"][key].append(name)
        preview["summary"]["unchanged"] += 1


def preview_variables(
    preview: dict[str, Any],
    connection: Connection,
    variable_table: Any,
    entity_column: str,
    entity_id: int | None,
    entity_type: str,
    entity_name: str,
    variables: object,
) -> None:
    """Preview variable changes."""
    if not isinstance(variables, dict):
        return
    key = f"{entity_type}_vars"
    for name, value in variables.items():
        entry = {"entity": entity_name, "name": name, "to": str(value)}
        existing = None
        if entity_id is not None:
            existing = connection.execute(
                select(variable_table.c.value).where(
                    variable_table.c[entity_column] == entity_id, variable_table.c.name == name
                )
            ).scalar_one_or_none()
        if existing is None:
            preview["updates"][key].append(entry)
            preview["summary"]["variables_changed"] += 1
        elif str(existing) != str(value):
            preview["updates"][key].append(entry | {"from": str(existing)})
            preview["summary"]["variables_changed"] += 1
        else:
            preview["unchanged"][key].append(entry)
            preview["summary"]["unchanged"] += 1


def preview_tags(
    preview: dict[str, Any],
    connection: Connection,
    association_table: Any,
    entity_column: str,
    entity_id: int | None,
    entity_type: str,
    entity_name: str,
    tag_names: list[str],
) -> None:
    """Preview tag association changes."""
    for tag_name in normalize_tags([str(value) for value in tag_names]):
        entry = {"entity_type": entity_type, "entity": entity_name, "tag": tag_name}
        changed = True
        if entity_id is not None:
            tag_id = connection.execute(
                select(tags.c.id).where(tags.c.name == tag_name)
            ).scalar_one_or_none()
            changed = (
                tag_id is None
                or connection.execute(
                    select(association_table.c.id).where(
                        association_table.c[entity_column] == entity_id,
                        association_table.c.tag_id == tag_id,
                    )
                ).scalar_one_or_none()
                is None
            )
        add_association_preview(preview, "tags", entry, changed)


def add_association_preview(
    preview: dict[str, Any], key: str, entry: dict[str, str], changed: bool
) -> None:
    """Add association preview entry."""
    if changed:
        preview["associations"][key].append(entry)
        preview["summary"]["associations_added"] += 1
    else:
        unchanged = entry if key == "tags" else entry | {"type": key}
        preview["unchanged"]["associations"].append(unchanged)
        preview["summary"]["unchanged"] += 1


def preview_ignored(
    connection: Connection, snapshot: dict[str, Any], preview: dict[str, Any]
) -> None:
    """Record existing entities absent from snapshot."""
    snapshot_hosts = set(snapshot["hosts"])
    snapshot_groups = set(snapshot["groups"])
    for name in connection.execute(select(hosts.c.name).order_by(hosts.c.name)).scalars():
        if name not in snapshot_hosts:
            preview["ignored"]["existing_hosts_not_in_snapshot"].append(name)
            preview["summary"]["ignored_existing_hosts"] += 1
    for name in connection.execute(select(groups.c.name).order_by(groups.c.name)).scalars():
        if name not in snapshot_groups:
            preview["ignored"]["existing_groups_not_in_snapshot"].append(name)
            preview["summary"]["ignored_existing_groups"] += 1


def invalid(message: str) -> None:
    """Raise a Ruby-compatible invalid snapshot error."""
    raise SnapshotError(f"Invalid inventory snapshot: {message}.")
