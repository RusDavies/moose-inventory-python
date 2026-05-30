"""Command-line entry point for the Python moose-inventory port.

The implementation is intentionally skeletal for now. The Ruby parity baseline in
``docs/compatibility/ruby-parity-baseline.md`` is the behavior contract for future work.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import cast

import yaml

from moose_inventory.audit import infer_audit_metadata, list_audit_events, record_audit_event
from moose_inventory.config import ConfigError, RuntimeOptions, parse_runtime_options
from moose_inventory.db import Database, DatabaseError, backup_sqlite, database_from_runtime
from moose_inventory.doctor import inventory_doctor
from moose_inventory.group_commands import GroupCommands
from moose_inventory.host_commands import HostCommands
from moose_inventory.snapshot import (
    SnapshotError,
    export_snapshot,
    import_snapshot,
    preview_snapshot,
)
from moose_inventory.version import __version__

USAGE = """Usage: moose-inventory [GLOBAL FLAGS] COMMAND [ARGS]

Python port skeleton for the Ruby moose-inventory CLI.

Implemented commands:
  version       Get the code version
  help          Show this help
  database      Inspect and manage database lifecycle state
  db            Alias for database
  host          Manipulate hosts in the inventory
  group         Manipulate groups in the inventory
  export        Export a canonical inventory snapshot
  import        Import and validate an inventory snapshot
  doctor        Run read-only inventory health checks
  audit         Inspect append-only inventory change history

Compatibility target:
  See docs/compatibility/ruby-parity-baseline.md
"""


def main(argv: Sequence[str] | None = None) -> int:
    """Run the moose-inventory CLI."""
    raw_args = list(sys.argv[1:] if argv is None else argv)

    if not raw_args or raw_args[0] in {"help", "--help", "-h"}:
        print(USAGE, end="")
        return 0

    if raw_args[0] == "version":
        print(f"Version {__version__}")
        return 0

    try:
        runtime = parse_runtime_options(raw_args)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not runtime.argv:
        print(USAGE, end="")
        return 0

    try:
        database_from_runtime(runtime).migrate()
    except (ConfigError, DatabaseError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    command = runtime.argv[0]
    if command in {"database", "db"}:
        return run_database_command(runtime)
    if command == "host":
        database = database_from_runtime(runtime)
        return run_with_audit(runtime, database, HostCommands(database, runtime).run)
    if command == "group":
        database = database_from_runtime(runtime)
        return run_with_audit(runtime, database, GroupCommands(database, runtime).run)
    if command == "export":
        return run_export_command(runtime)
    if command == "import":
        return run_import_command(runtime)
    if command == "doctor":
        return run_doctor_command(runtime)
    if command == "audit":
        return run_audit_command(runtime)

    print(
        f"ERROR: command '{command}' is not implemented in the Python port skeleton yet.",
        file=sys.stderr,
    )
    return 1


def run_with_audit(runtime: RuntimeOptions, database: Database, action: Callable[[], int]) -> int:
    """Run a command and append audit metadata on successful mutations."""
    result = action()
    if result == 0:
        metadata = infer_audit_metadata(runtime.argv)
        if metadata is not None:
            record_audit_event(database, metadata)
    return result


def run_audit_command(runtime: RuntimeOptions) -> int:
    """Dispatch audit commands."""
    args = list(runtime.argv[1:])
    if not args or args[0] in {"help", "--help", "-h"}:
        print("Usage: moose-inventory audit list [--limit N] [--format yaml|json|pjson]")
        return 0
    if args[0] != "list":
        print(f"ERROR: audit action '{args[0]}' is not implemented.", file=sys.stderr)
        return 1
    limit = 20
    output_format: str | None = None
    index = 1
    while index < len(args):
        arg = args[index]
        if arg == "--limit":
            if index + 1 >= len(args):
                print("ERROR: Expected a value after --limit", file=sys.stderr)
                return 1
            limit = int(args[index + 1])
            index += 1
        elif arg == "--format":
            if index + 1 >= len(args):
                print("ERROR: Expected a value after --format", file=sys.stderr)
                return 1
            output_format = args[index + 1]
            index += 1
        else:
            print(f"ERROR: Unknown audit list option '{arg}'", file=sys.stderr)
            return 1
        index += 1
    events = list_audit_events(database_from_runtime(runtime), limit=limit)
    if output_format:
        print(serialize_data(events, output_format))
    elif not events:
        print("No audit events recorded.")
    else:
        for event in events:
            print(
                f"{event['id']} {event['created_at']} {event['command']} "
                f"{event['entity_type']}={event['entity_name']} action={event['action']}"
            )
    return 0


def run_doctor_command(runtime: RuntimeOptions) -> int:
    """Run inventory doctor checks."""
    args = list(runtime.argv[1:])
    output_format: str | None = None
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--format":
            if index + 1 >= len(args):
                print("ERROR: Expected a value after --format", file=sys.stderr)
                return 1
            output_format = args[index + 1]
            index += 1
        else:
            print(f"ERROR: Unknown doctor option '{arg}'", file=sys.stderr)
            return 1
        index += 1
    report = inventory_doctor(database_from_runtime(runtime), runtime)
    if output_format:
        print(serialize_data(report, output_format))
    elif report["ok"]:
        print("Inventory doctor found no issues.")
    else:
        print(f"Inventory doctor found {report['issue_count']} issue(s):")
        for entry in cast(list[Mapping[str, object]], report["issues"]):
            print(f"- [{entry['severity']}] {entry['id']}: {entry['message']}")
    return 0 if report["ok"] else 1


def run_export_command(runtime: RuntimeOptions) -> int:
    """Export an inventory snapshot to stdout or a file."""
    args = list(runtime.argv[1:])
    if len(args) > 1:
        print(f"ERROR: Wrong number of arguments, {len(args)} for 0..1.", file=sys.stderr)
        return 1
    snapshot = export_snapshot(database_from_runtime(runtime))
    output = serialize_data(snapshot, runtime.output_format)
    if args:
        Path(args[0]).write_text(output, encoding="utf-8")
        print(f"Exported inventory snapshot to {args[0]}.")
    else:
        print(output)
    return 0


def run_import_command(runtime: RuntimeOptions) -> int:
    """Import or preview an inventory snapshot."""
    args = list(runtime.argv[1:])
    preview = False
    preview_format: str | None = None
    names: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--preview":
            preview = True
        elif arg == "--preview-format":
            if index + 1 >= len(args):
                print("ERROR: Expected a value after --preview-format", file=sys.stderr)
                return 1
            preview_format = args[index + 1]
            index += 1
        else:
            names.append(arg)
        index += 1
    if len(names) != 1:
        print(f"ERROR: Wrong number of arguments, {len(names)} for 1.", file=sys.stderr)
        return 1
    if preview_format and not preview:
        print("ERROR: --preview-format requires --preview.", file=sys.stderr)
        return 1
    file_name = names[0]
    try:
        snapshot = yaml.safe_load(Path(file_name).read_text(encoding="utf-8"))
        if preview:
            render_import_preview(
                preview_snapshot(database_from_runtime(runtime), snapshot), preview_format
            )
            return 0
        database = database_from_runtime(runtime)
        result = import_snapshot(database, snapshot)
        metadata = infer_audit_metadata(runtime.argv)
        if metadata is not None:
            record_audit_event(database, metadata)
    except FileNotFoundError:
        print(f"ERROR: The inventory snapshot '{file_name}' does not exist.", file=sys.stderr)
        return 1
    except yaml.YAMLError as exc:
        print(f"ERROR: Could not load inventory snapshot '{file_name}': {exc}", file=sys.stderr)
        return 1
    except SnapshotError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Imported inventory snapshot from {file_name}.")
    print(f"Created hosts: {result.created_hosts}")
    print(f"Created groups: {result.created_groups}")
    print(f"Variables changed: {result.updated_variables}")
    print(f"Associations added: {result.associations}")
    return 0


def render_import_preview(preview: dict[str, object], preview_format: str | None) -> None:
    """Render a snapshot import preview."""
    if preview_format:
        print(serialize_data(preview, preview_format))
        return
    print("Snapshot import preview. No changes applied.")
    summary = cast(Mapping[str, object], preview["summary"])
    for key, value in summary.items():
        print(f"{key.replace('_', ' ').capitalize()}: {value}")


def serialize_data(data: object, output_format: str) -> str:
    """Serialize data using Ruby-compatible format aliases."""
    fmt = output_format.lower()
    if fmt in {"yaml", "y"}:
        return cast(str, yaml.safe_dump(data, sort_keys=False))
    if fmt in {"json", "j"}:
        return json.dumps(data, separators=(",", ":"))
    if fmt in {"prettyjson", "pjson", "p"}:
        return json.dumps(data, indent=2)
    raise SnapshotError(f"Output format '{output_format}' is not yet supported")


def run_database_command(runtime: RuntimeOptions) -> int:
    """Dispatch database lifecycle subcommands."""
    args = list(runtime.argv[1:])
    if not args or args[0] in {"help", "--help", "-h"}:
        print_database_usage()
        return 0

    action = args[0]
    try:
        database = database_from_runtime(runtime)
        if action == "status":
            render_database_status(database.status())
            return 0
        if action == "doctor":
            status = database.status()
            render_database_doctor(status)
            return 0 if database_status_ok(status) else 1
        if action == "migrate":
            status = database.migrate()
            print(f"Database schema is at version {status['schema_version']}.")
            return 0
        if action == "backup":
            if len(args) < 2:
                print("ERROR: Expected FILE after database backup", file=sys.stderr)
                return 1
            destination = backup_sqlite(database, Path(args[1]))
            print(f"Backed up database to {destination}.")
            return 0
    except (ConfigError, DatabaseError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"ERROR: database action '{action}' is not implemented.", file=sys.stderr)
    return 1


def print_database_usage() -> None:
    """Print database command usage."""
    print(
        "Usage: moose-inventory database ACTION [ARGS]\n\n"
        "Database lifecycle commands:\n"
        "  status       Show database lifecycle status\n"
        "  doctor       Check database schema state\n"
        "  migrate      Create missing schema tables and record current schema version\n"
        "  backup FILE  Back up the configured sqlite3 database file\n",
        end="",
    )


def render_database_status(status: dict[str, object]) -> None:
    """Render Ruby-compatible database status output."""
    print(f"Adapter: {status['adapter']}")
    print(f"Schema version: {status['schema_version'] or 'unknown'}")
    print(f"Expected schema version: {status['expected_schema_version']}")
    sqlite_file = status.get("sqlite_file")
    if sqlite_file is not None:
        print(f"SQLite file: {sqlite_file}")
    print("Tables:")
    for name, present in cast_tables(status["tables"]).items():
        state = "present" if present else "missing"
        print(f"- {name}: {state}")


def render_database_doctor(status: dict[str, object]) -> None:
    """Render Ruby-compatible database doctor output."""
    missing = [name for name, present in cast_tables(status["tables"]).items() if not present]
    if not missing and status["schema_version"] == status["expected_schema_version"]:
        print("Database doctor found no issues.")
        return

    print("Database doctor found issue(s):")
    if missing:
        print(f"- Missing tables: {', '.join(missing)}")
    if status["schema_version"] != status["expected_schema_version"]:
        print(
            f"- Schema version is {status['schema_version']!r}; "
            f"expected {status['expected_schema_version']}."
        )


def database_status_ok(status: dict[str, object]) -> bool:
    """Return whether database doctor should pass."""
    return (
        all(cast_tables(status["tables"]).values())
        and status["schema_version"] == status["expected_schema_version"]
    )


def cast_tables(value: object) -> Mapping[str, bool]:
    """Cast status table map for rendering helpers."""
    return cast(Mapping[str, bool], value)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
