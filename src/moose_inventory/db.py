"""Database connection and schema migration support for moose-inventory."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    func,
    inspect,
    select,
)
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import NoSuchTableError

from moose_inventory.config import ConfigError, RuntimeOptions, db_settings

SCHEMA_VERSION = 4

SchemaTableName = Literal[
    "hosts",
    "hostvars",
    "groups",
    "groups_groups",
    "groupvars",
    "groups_hosts",
    "schema_info",
    "audit_events",
    "tags",
    "hosts_tags",
    "groups_tags",
]

SCHEMA_MIGRATIONS: dict[int, tuple[SchemaTableName, ...]] = {
    1: ("hosts", "hostvars", "groups", "groups_groups", "groupvars", "groups_hosts", "schema_info"),
    2: ("audit_events",),
    3: ("tags", "hosts_tags", "groups_tags"),
    4: (),
}

INDEX_DEFINITIONS: tuple[tuple[str, str, tuple[str, ...], bool], ...] = (
    ("idx_hostvars_host_id_name", "hostvars", ("host_id", "name"), True),
    ("idx_groupvars_group_id_name", "groupvars", ("group_id", "name"), True),
    ("idx_groups_hosts_host_id_group_id", "groups_hosts", ("host_id", "group_id"), True),
    ("idx_groups_groups_parent_id_child_id", "groups_groups", ("parent_id", "child_id"), True),
    ("idx_hosts_tags_host_id_tag_id", "hosts_tags", ("host_id", "tag_id"), True),
    ("idx_groups_tags_group_id_tag_id", "groups_tags", ("group_id", "tag_id"), True),
    ("idx_groups_hosts_group_id_host_id", "groups_hosts", ("group_id", "host_id"), False),
    ("idx_groups_groups_child_id_parent_id", "groups_groups", ("child_id", "parent_id"), False),
    ("idx_hosts_tags_tag_id_host_id", "hosts_tags", ("tag_id", "host_id"), False),
    ("idx_groups_tags_tag_id_group_id", "groups_tags", ("tag_id", "group_id"), False),
)


class DatabaseError(RuntimeError):
    """Raised when database configuration or schema work fails."""


metadata = MetaData()

hosts = Table(
    "hosts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", Text, unique=True),
)

hostvars = Table(
    "hostvars",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("host_id", Integer, ForeignKey("hosts.id")),
    Column("name", Text),
    Column("value", Text),
)

groups = Table(
    "groups",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", Text, unique=True),
)

groups_groups = Table(
    "groups_groups",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("parent_id", Integer, ForeignKey("groups.id")),
    Column("child_id", Integer, ForeignKey("groups.id")),
)

groupvars = Table(
    "groupvars",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("group_id", Integer, ForeignKey("groups.id")),
    Column("name", Text),
    Column("value", Text),
)

groups_hosts = Table(
    "groups_hosts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("host_id", Integer, ForeignKey("hosts.id")),
    Column("group_id", Integer, ForeignKey("groups.id")),
)

schema_info = Table(
    "schema_info",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("version", Integer, nullable=False),
)

audit_events = Table(
    "audit_events",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("created_at", Text, nullable=False),
    Column("actor", Text),
    Column("command", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("entity_type", Text),
    Column("entity_name", Text),
    Column("details", Text),
)

tags = Table(
    "tags",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", Text, unique=True, nullable=False),
)

hosts_tags = Table(
    "hosts_tags",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("host_id", Integer, ForeignKey("hosts.id")),
    Column("tag_id", Integer, ForeignKey("tags.id")),
)

groups_tags = Table(
    "groups_tags",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("group_id", Integer, ForeignKey("groups.id")),
    Column("tag_id", Integer, ForeignKey("tags.id")),
)

TABLES: dict[SchemaTableName, Table] = {
    "hosts": hosts,
    "hostvars": hostvars,
    "groups": groups,
    "groups_groups": groups_groups,
    "groupvars": groupvars,
    "groups_hosts": groups_hosts,
    "schema_info": schema_info,
    "audit_events": audit_events,
    "tags": tags,
    "hosts_tags": hosts_tags,
    "groups_tags": groups_tags,
}


@dataclass(frozen=True)
class Database:
    """Database handle for schema and future inventory operations."""

    engine: Engine
    adapter: str
    sqlite_file: Path | None = None

    def connect(self) -> Connection:
        """Open a SQLAlchemy connection."""
        return self.engine.connect()

    def status(self) -> dict[str, Any]:
        """Return Ruby-compatible database lifecycle status."""
        with self.connect() as connection:
            return {
                "adapter": self.adapter,
                "schema_version": schema_version(connection),
                "expected_schema_version": SCHEMA_VERSION,
                "tables": {name: table_exists(connection, name) for name in TABLES},
                "sqlite_file": str(self.sqlite_file) if self.sqlite_file is not None else None,
            }

    def migrate(self) -> dict[str, Any]:
        """Run schema migrations and return current status."""
        with self.engine.begin() as connection:
            migrate_schema(connection)
        return self.status()


def database_from_runtime(runtime: RuntimeOptions) -> Database:
    """Create a Database from resolved runtime options."""
    return database_from_settings(db_settings(runtime))


def database_from_settings(settings: dict[str, Any] | Any) -> Database:
    """Create a Database from a config `db` mapping."""
    if not isinstance(settings, dict):
        settings = dict(settings)
    adapter = normalized_adapter(settings)

    if adapter == "sqlite3":
        return init_sqlite(settings)
    if adapter == "mysql":
        return init_mysql(settings)
    if adapter == "postgresql":
        return init_postgresql(settings)

    raise DatabaseError(f"database adapter {adapter} is not yet supported.")


def normalized_adapter(settings: dict[str, Any]) -> str:
    """Return lowercase adapter name after config validation."""
    adapter = settings.get("adapter")
    if adapter is None:
        raise DatabaseError("Expected key adapter missing in database configuration")
    return str(adapter).lower()


def init_sqlite(settings: dict[str, Any]) -> Database:
    """Create a SQLite database handle."""
    ensure_required_config_keys(settings, ("file",), "sqlite3")
    raw_file = str(settings["file"])
    if raw_file == "":
        raise DatabaseError("SQLite3 DB 'file' cannot be empty")

    db_file = Path(raw_file).expanduser().resolve()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_file}", future=True)
    return Database(engine=engine, adapter="sqlite3", sqlite_file=db_file)


def init_mysql(settings: dict[str, Any]) -> Database:
    """Create a MySQL/MariaDB database handle."""
    ensure_required_config_keys(settings, ("host", "database", "user"), "mysql")
    password = database_password(settings, "mysql")
    url = f"mysql+pymysql://{settings['user']}:{password}@{settings['host']}/{settings['database']}"
    return Database(engine=create_engine(url, future=True), adapter="mysql")


def init_postgresql(settings: dict[str, Any]) -> Database:
    """Create a PostgreSQL database handle."""
    ensure_required_config_keys(settings, ("host", "database", "user"), "postgresql")
    password = database_password(settings, "postgresql")
    url = f"postgresql+psycopg://{settings['user']}:{password}@{settings['host']}/{settings['database']}"
    return Database(engine=create_engine(url, future=True), adapter="postgresql")


def ensure_required_config_keys(
    settings: dict[str, Any], keys: tuple[str, ...], adapter: str
) -> None:
    """Raise when adapter-required config keys are missing."""
    for key in keys:
        if settings.get(key) is None:
            raise DatabaseError(f"Expected key {key} missing in {adapter} configuration")


def database_password(settings: dict[str, Any], adapter: str) -> str:
    """Resolve database password using Ruby-compatible password/password_env rules."""
    if settings.get("password") is not None:
        return str(settings["password"])

    password_env = settings.get("password_env")
    if password_env is None:
        raise DatabaseError(
            f"Expected key password or password_env missing in {adapter} configuration"
        )

    import os

    password = os.environ.get(str(password_env))
    if password is None or password == "":
        raise DatabaseError(
            f"Environment variable {password_env} is not set for {adapter} password"
        )
    return password


def migrate_schema(connection: Connection) -> None:
    """Run ordered schema migrations."""
    reject_future_schema(connection)
    for version in sorted(SCHEMA_MIGRATIONS):
        current = schema_version(connection) or 0
        if current >= version and not schema_migration_artifacts_missing(connection, version):
            continue
        apply_schema_migration(connection, version)


def schema_version(connection: Connection) -> int | None:
    """Return the current schema version, if schema_info exists."""
    if not table_exists(connection, "schema_info"):
        return None
    value = connection.execute(
        select(schema_info.c.version).order_by(schema_info.c.id.desc()).limit(1)
    ).scalar_one_or_none()
    return cast(int | None, value)


def reject_future_schema(connection: Connection) -> None:
    """Reject databases newer than this implementation supports."""
    current = schema_version(connection)
    if current is not None and current > SCHEMA_VERSION:
        raise DatabaseError(
            f"Database schema version {current} is newer than supported version "
            f"{SCHEMA_VERSION}. Upgrade moose-inventory before using this database."
        )


def schema_migration_artifacts_missing(connection: Connection, version: int) -> bool:
    """Return whether migration artifacts for version are missing."""
    return schema_migration_tables_missing(connection, version) or (
        version == 4 and schema_indexes_missing(connection)
    )


def schema_migration_tables_missing(connection: Connection, version: int) -> bool:
    """Return whether any migration tables are missing."""
    return any(
        not table_exists(connection, table_name) for table_name in SCHEMA_MIGRATIONS[version]
    )


def schema_indexes_missing(connection: Connection) -> bool:
    """Return whether any schema index is missing."""
    return any(
        not index_exists(connection, table_name, name)
        for name, table_name, _, _ in INDEX_DEFINITIONS
    )


def apply_schema_migration(connection: Connection, version: int) -> None:
    """Apply one migration version."""
    for table_name in SCHEMA_MIGRATIONS[version]:
        create_table(connection, table_name)
    if version == 4:
        apply_schema_indexes(connection)
    record_schema_version(connection, version)


def apply_schema_indexes(connection: Connection) -> None:
    """Create all schema indexes after duplicate cleanup."""
    clean_duplicate_index_rows(connection)
    for name, table_name, column_names, unique in INDEX_DEFINITIONS:
        if index_exists(connection, table_name, name):
            continue
        create_index(connection, name, table_name, column_names, unique)


def create_index(
    connection: Connection, name: str, table_name: str, column_names: tuple[str, ...], unique: bool
) -> None:
    """Create an index without attaching it to SQLAlchemy global table metadata."""
    unique_sql = "UNIQUE " if unique else ""
    columns_sql = ", ".join(column_names)
    connection.exec_driver_sql(
        f"CREATE {unique_sql}INDEX {name} ON {table_name} ({columns_sql})"
    )


def clean_duplicate_index_rows(connection: Connection) -> None:
    """Clean duplicates before adding Ruby-compatible unique indexes."""
    dedupe_duplicate_rows(connection, hostvars, ("host_id", "name"), value_columns=("value",))
    dedupe_duplicate_rows(connection, groupvars, ("group_id", "name"), value_columns=("value",))
    dedupe_duplicate_rows(connection, groups_hosts, ("host_id", "group_id"))
    dedupe_duplicate_rows(connection, groups_groups, ("parent_id", "child_id"))
    dedupe_duplicate_rows(connection, hosts_tags, ("host_id", "tag_id"))
    dedupe_duplicate_rows(connection, groups_tags, ("group_id", "tag_id"))


def dedupe_duplicate_rows(
    connection: Connection,
    table: Table,
    column_names: tuple[str, ...],
    *,
    value_columns: tuple[str, ...] = (),
) -> None:
    """Collapse exact duplicate rows and reject conflicting variable duplicates."""
    columns = [table.c[name] for name in column_names]
    duplicates = connection.execute(
        select(*columns).group_by(*columns).having(func.count(table.c.id) > 1)
    ).all()

    for duplicate in duplicates:
        key = dict(zip(column_names, duplicate, strict=True))
        rows = connection.execute(
            select(table).filter_by(**key).order_by(table.c.id)
        ).mappings().all()
        reject_conflicting_duplicates(table.name, key, rows, value_columns)
        ids_to_delete = [cast(int, row["id"]) for row in rows[1:]]
        if ids_to_delete:
            connection.execute(table.delete().where(table.c.id.in_(ids_to_delete)))


def reject_conflicting_duplicates(
    table_name: str,
    key: dict[str, Any],
    rows: Sequence[Any],
    value_columns: tuple[str, ...],
) -> None:
    """Reject duplicate variable rows with conflicting values."""
    for column in value_columns:
        values = {row[column] for row in rows}
        if len(values) > 1:
            raise DatabaseError(
                f"Cannot add unique indexes because {table_name} has conflicting duplicates "
                f"for {key}. Resolve duplicate values before migrating."
            )


def record_schema_version(connection: Connection, version: int) -> None:
    """Insert or update schema_info with the current version."""
    if not table_exists(connection, "schema_info"):
        raise DatabaseError("Cannot record schema version before schema_info exists.")

    if connection.execute(select(schema_info.c.id).limit(1)).first() is None:
        connection.execute(schema_info.insert().values(version=version))
    else:
        connection.execute(schema_info.update().values(version=version))


def create_table(connection: Connection, table_name: SchemaTableName) -> None:
    """Create a schema table if it is missing."""
    table = TABLES[table_name]
    table.create(bind=connection, checkfirst=True)


def table_exists(connection: Connection, table_name: str) -> bool:
    """Return whether a table exists."""
    return inspect(connection).has_table(table_name)


def index_exists(connection: Connection, table_name: str, index_name: str) -> bool:
    """Return whether an index exists on a table."""
    try:
        return any(
            index["name"] == index_name for index in inspect(connection).get_indexes(table_name)
        )
    except NoSuchTableError:
        return False


def backup_sqlite(database: Database, destination: Path) -> Path:
    """Copy a configured SQLite database file to destination."""
    if database.adapter != "sqlite3" or database.sqlite_file is None:
        raise DatabaseError("Database backup is currently supported for sqlite3 only.")
    if not database.sqlite_file.exists():
        raise DatabaseError(f"SQLite database file {database.sqlite_file} does not exist.")
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(database.sqlite_file.read_bytes())
    return destination


def config_error_from_database_error(exc: DatabaseError) -> ConfigError:
    """Convert DB configuration failures into CLI config-style errors when useful."""
    return ConfigError(str(exc))
