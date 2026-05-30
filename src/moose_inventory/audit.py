"""Append-only audit recording and listing."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select

from moose_inventory.db import Database, audit_events


def infer_audit_metadata(argv: tuple[str, ...]) -> dict[str, str] | None:
    """Infer audit metadata for successful mutating CLI commands."""
    if not argv or "--dry-run" in argv:
        return None
    command = argv[0]
    if command == "import":
        return {
            "command": "import",
            "action": "import",
            "entity_type": "inventory",
            "entity_name": first_non_option(argv[1:]) or "",
        }
    if command not in {"host", "group"} or len(argv) < 3:
        return None
    action = argv[1]
    if action in {"list", "get", "listvar", "listvars", "listtags"}:
        return None
    action_map = {
        "add": "add",
        "rm": "remove",
        "addgroup": "associate",
        "rmgroup": "dissociate",
        "addhost": "associate",
        "rmhost": "dissociate",
        "addchild": "associate_child",
        "rmchild": "dissociate_child",
        "addvar": "add_variable",
        "rmvar": "remove_variable",
        "addtag": "add_tag",
        "rmtag": "remove_tag",
    }
    audit_action = action_map.get(action)
    if audit_action is None:
        return None
    entity_name = first_non_option(argv[2:]) or ""
    return {
        "command": f"{command} {action}",
        "action": audit_action,
        "entity_type": command,
        "entity_name": entity_name,
    }


def first_non_option(args: tuple[str, ...]) -> str | None:
    """Return first positional-ish token."""
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in {"--groups", "--hosts", "--format", "--preview-format", "--plan-format"}:
            skip_next = True
            continue
        if arg.startswith("--"):
            continue
        return arg
    return None


def record_audit_event(database: Database, metadata: dict[str, str]) -> None:
    """Append an audit event."""
    details = json.dumps({"warning_count": 0, "events": []}, separators=(",", ":"))
    with database.engine.begin() as connection:
        connection.execute(
            audit_events.insert().values(
                created_at=datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
                actor=os.environ.get("USER"),
                command=metadata["command"],
                action=metadata["action"],
                entity_type=metadata["entity_type"],
                entity_name=metadata["entity_name"],
                details=details,
            )
        )


def list_audit_events(database: Database, limit: int = 20) -> list[dict[str, Any]]:
    """List recent audit events newest-first."""
    with database.connect() as connection:
        rows = connection.execute(
            select(audit_events).order_by(desc(audit_events.c.id)).limit(limit)
        ).all()
    return [
        {
            "id": row.id,
            "created_at": row.created_at,
            "actor": row.actor,
            "command": row.command,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_name": row.entity_name,
            "details": parse_details(row.details),
        }
        for row in rows
    ]


def parse_details(details: object) -> object:
    """Parse JSON details when possible."""
    if details is None or details == "":
        return None
    try:
        return json.loads(str(details))
    except json.JSONDecodeError:
        return details
