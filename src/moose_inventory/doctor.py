"""Inventory doctor checks."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import Connection, select

from moose_inventory.config import RuntimeOptions, db_settings
from moose_inventory.db import (
    Database,
    groups,
    groups_groups,
    groups_hosts,
    groupvars,
    hosts,
    hostvars,
)

AUTOMATIC_GROUP = "ungrouped"


def inventory_doctor(database: Database, runtime: RuntimeOptions) -> dict[str, Any]:
    """Run read-only inventory health checks."""
    issues: list[dict[str, Any]] = []
    issues.extend(check_database_config(runtime))
    issues.extend(check_plaintext_password_config(runtime))
    with database.connect() as connection:
        issues.extend(check_hosts_only_in_automatic_group(connection))
        issues.extend(check_orphaned_groups(connection))
        issues.extend(check_empty_groups(connection))
        issues.extend(check_duplicateish_names(connection))
        issues.extend(check_invalid_variables(connection))
        issues.extend(check_group_cycles(connection))
    return {"ok": not issues, "issue_count": len(issues), "issues": issues}


def check_database_config(runtime: RuntimeOptions) -> list[dict[str, Any]]:
    """Check DB config is present enough to use."""
    try:
        settings = db_settings(runtime)
    except Exception as exc:  # noqa: BLE001 - doctor reports config problems, not crashes
        return [
            issue("missing_db_config", "error", f"Database configuration could not be read: {exc}")
        ]
    if not settings:
        return [issue("missing_db_config", "error", "Database configuration is missing.")]
    if str(settings.get("adapter", "")).strip() == "":
        return [
            issue("missing_db_adapter", "error", "Database adapter is missing from configuration.")
        ]
    return []


def check_plaintext_password_config(runtime: RuntimeOptions) -> list[dict[str, Any]]:
    """Warn when config carries a plaintext DB password."""
    try:
        settings = db_settings(runtime)
    except Exception:  # noqa: BLE001 - reported by check_database_config
        return []
    if "password" in settings:
        return [
            issue(
                "plaintext_password_config",
                "warning",
                "Database configuration uses plaintext password; prefer password_env.",
            )
        ]
    return []


def check_hosts_only_in_automatic_group(connection: Connection) -> list[dict[str, Any]]:
    """Warn for hosts only in ungrouped."""
    issues: list[dict[str, Any]] = []
    for host_id, name in connection.execute(
        select(hosts.c.id, hosts.c.name).order_by(hosts.c.name)
    ):
        group_names = list(
            connection.execute(
                select(groups.c.name)
                .select_from(groups_hosts.join(groups, groups_hosts.c.group_id == groups.c.id))
                .where(groups_hosts.c.host_id == host_id)
                .order_by(groups.c.name)
            ).scalars()
        )
        if group_names == [AUTOMATIC_GROUP]:
            issues.append(
                issue(
                    "host_only_in_ungrouped",
                    "warning",
                    f"Host '{name}' is only in automatic group 'ungrouped'.",
                    subject=name,
                )
            )
    return issues


def check_orphaned_groups(connection: Connection) -> list[dict[str, Any]]:
    """Warn for groups with no parents and no hosts."""
    issues: list[dict[str, Any]] = []
    for group_id, name in connection.execute(
        select(groups.c.id, groups.c.name).order_by(groups.c.name)
    ):
        if name == AUTOMATIC_GROUP:
            continue
        has_parent = connection.execute(
            select(groups_groups.c.id).where(groups_groups.c.child_id == group_id)
        ).first()
        has_host = connection.execute(
            select(groups_hosts.c.id).where(groups_hosts.c.group_id == group_id)
        ).first()
        if has_parent is None and has_host is None:
            issues.append(
                issue(
                    "orphaned_group",
                    "warning",
                    f"Group '{name}' has no parents and no hosts.",
                    subject=name,
                )
            )
    return issues


def check_empty_groups(connection: Connection) -> list[dict[str, Any]]:
    """Warn for empty groups."""
    issues: list[dict[str, Any]] = []
    for group_id, name in connection.execute(
        select(groups.c.id, groups.c.name).order_by(groups.c.name)
    ):
        if name == AUTOMATIC_GROUP:
            continue
        has_host = connection.execute(
            select(groups_hosts.c.id).where(groups_hosts.c.group_id == group_id)
        ).first()
        has_child = connection.execute(
            select(groups_groups.c.id).where(groups_groups.c.parent_id == group_id)
        ).first()
        has_var = connection.execute(
            select(groupvars.c.id).where(groupvars.c.group_id == group_id)
        ).first()
        if has_host is None and has_child is None and has_var is None:
            issues.append(
                issue("empty_group", "warning", f"Group '{name}' is empty.", subject=name)
            )
    return issues


def check_duplicateish_names(connection: Connection) -> list[dict[str, Any]]:
    """Warn for names that normalize to the same alphanumeric value."""
    host_names = list(connection.execute(select(hosts.c.name)).scalars())
    group_names = list(connection.execute(select(groups.c.name)).scalars())
    return duplicateish_issues(host_names, "host") + duplicateish_issues(group_names, "group")


def duplicateish_issues(names: list[str], label: str) -> list[dict[str, Any]]:
    """Build duplicate-ish name issues."""
    grouped: dict[str, list[str]] = {}
    for name in names:
        grouped.setdefault(re.sub(r"[^a-z0-9]", "", str(name).lower()), []).append(str(name))
    issues: list[dict[str, Any]] = []
    for normalized, originals in grouped.items():
        unique = sorted(set(originals))
        if normalized and len(unique) >= 2:
            issues.append(
                issue(
                    f"duplicateish_{label}_names",
                    "warning",
                    f"{label.capitalize()} names look duplicate-ish: {', '.join(unique)}.",
                    subject=unique,
                )
            )
    return issues


def check_invalid_variables(connection: Connection) -> list[dict[str, Any]]:
    """Report empty-name/nil variable rows."""
    issues: list[dict[str, Any]] = []
    host_names = {
        int(row.id): str(row.name)
        for row in connection.execute(select(hosts.c.id, hosts.c.name)).all()
    }
    group_names = {
        int(row.id): str(row.name)
        for row in connection.execute(select(groups.c.id, groups.c.name)).all()
    }
    for row in connection.execute(select(hostvars.c.host_id, hostvars.c.name, hostvars.c.value)):
        if not str(row.name).strip() or row.value is None:
            owner = f"host '{host_names.get(row.host_id)}'"
            issues.append(
                issue(
                    "invalid_variable_shape",
                    "error",
                    f"Variable on {owner} has an empty name or nil value.",
                    subject=owner,
                )
            )
    for row in connection.execute(
        select(groupvars.c.group_id, groupvars.c.name, groupvars.c.value)
    ):
        if not str(row.name).strip() or row.value is None:
            owner = f"group '{group_names.get(row.group_id)}'"
            issues.append(
                issue(
                    "invalid_variable_shape",
                    "error",
                    f"Variable on {owner} has an empty name or nil value.",
                    subject=owner,
                )
            )
    return issues


def check_group_cycles(connection: Connection) -> list[dict[str, Any]]:
    """Report cycles in group hierarchy."""
    children: dict[str, list[str]] = {}
    for group_id, name in connection.execute(select(groups.c.id, groups.c.name)):
        child_names = list(
            connection.execute(
                select(groups.c.name)
                .select_from(groups_groups.join(groups, groups_groups.c.child_id == groups.c.id))
                .where(groups_groups.c.parent_id == group_id)
            ).scalars()
        )
        children[str(name)] = [str(child) for child in child_names]
    visiting: set[str] = set()
    visited: set[str] = set()
    cycles: list[list[str]] = []

    def visit(name: str, path: list[str]) -> None:
        if name in visited:
            return
        if name in visiting:
            cycle_start = path.index(name) if name in path else 0
            cycles.append(path[cycle_start:] + [name])
            return
        visiting.add(name)
        for child in children.get(name, []):
            visit(child, path + [name])
        visiting.remove(name)
        visited.add(name)

    for name in children:
        visit(name, [])
    return [
        issue(
            "circular_group_relationship",
            "error",
            f"Group hierarchy contains a cycle: {' -> '.join(cycle)}.",
            subject=cycle,
        )
        for cycle in unique_cycles(cycles)
    ]


def unique_cycles(cycles: list[list[str]]) -> list[list[str]]:
    """Deduplicate cycle paths while keeping first-seen order."""
    seen: set[tuple[str, ...]] = set()
    unique: list[list[str]] = []
    for cycle in cycles:
        key = tuple(cycle)
        if key not in seen:
            seen.add(key)
            unique.append(cycle)
    return unique


def issue(
    issue_id: str, severity: str, message: str, *, subject: object | None = None
) -> dict[str, Any]:
    """Build a Ruby-shaped issue hash."""
    entry: dict[str, Any] = {"id": issue_id, "severity": severity, "message": message}
    if subject is not None:
        entry["subject"] = subject
    return entry
