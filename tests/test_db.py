from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select, text

from moose_inventory.db import (
    INDEX_DEFINITIONS,
    SCHEMA_VERSION,
    TABLES,
    DatabaseError,
    backup_sqlite,
    database_from_settings,
    groupvars,
    migrate_schema,
    schema_info,
    schema_version,
)


def sqlite_settings(path: Path) -> dict[str, str]:
    return {"adapter": "sqlite3", "file": str(path)}


def test_database_from_settings_creates_sqlite_parent_directory(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "inventory.db"

    database = database_from_settings(sqlite_settings(db_path))

    assert database.adapter == "sqlite3"
    assert database.sqlite_file == db_path.resolve()
    assert db_path.parent.exists()


def test_migrate_creates_ruby_schema_version_tables_and_indexes(tmp_path: Path) -> None:
    database = database_from_settings(sqlite_settings(tmp_path / "inventory.db"))

    status = database.migrate()

    assert status["schema_version"] == SCHEMA_VERSION
    assert status["expected_schema_version"] == SCHEMA_VERSION
    assert all(status["tables"].values())
    with database.connect() as connection:
        inspector = inspect(connection)
        assert set(inspector.get_table_names()) == set(TABLES)
        for index_name, table_name, _columns, _unique in INDEX_DEFINITIONS:
            assert any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    database = database_from_settings(sqlite_settings(tmp_path / "inventory.db"))

    first = database.migrate()
    second = database.migrate()

    assert first == second


def test_schema_version_returns_none_before_schema_info_exists(tmp_path: Path) -> None:
    database = database_from_settings(sqlite_settings(tmp_path / "inventory.db"))

    with database.connect() as connection:
        assert schema_version(connection) is None


def test_future_schema_is_rejected(tmp_path: Path) -> None:
    database = database_from_settings(sqlite_settings(tmp_path / "inventory.db"))
    with database.engine.begin() as connection:
        schema_info.create(bind=connection)
        connection.execute(schema_info.insert().values(version=SCHEMA_VERSION + 1))

    with pytest.raises(DatabaseError, match="newer than supported version"):
        database.migrate()


def test_missing_required_sqlite_file_key_fails() -> None:
    with pytest.raises(DatabaseError, match="Expected key file missing in sqlite3 configuration"):
        database_from_settings({"adapter": "sqlite3"})


def test_empty_sqlite_file_fails() -> None:
    with pytest.raises(DatabaseError, match="SQLite3 DB 'file' cannot be empty"):
        database_from_settings({"adapter": "sqlite3", "file": ""})


def test_unsupported_adapter_fails() -> None:
    with pytest.raises(DatabaseError, match="database adapter oracle is not yet supported"):
        database_from_settings({"adapter": "oracle"})


def test_duplicate_relation_rows_are_collapsed_before_unique_indexes(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}", future=True)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE hosts (id INTEGER PRIMARY KEY, name TEXT UNIQUE)"))
        connection.execute(text("CREATE TABLE groups (id INTEGER PRIMARY KEY, name TEXT UNIQUE)"))
        connection.execute(
            text(
                "CREATE TABLE groups_hosts "
                "(id INTEGER PRIMARY KEY, host_id INTEGER, group_id INTEGER)"
            )
        )
        connection.execute(
            text("CREATE TABLE schema_info (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)")
        )
        connection.execute(text("INSERT INTO hosts (id, name) VALUES (1, 'web01')"))
        connection.execute(text("INSERT INTO groups (id, name) VALUES (1, 'web')"))
        connection.execute(
            text("INSERT INTO groups_hosts (host_id, group_id) VALUES (1, 1), (1, 1)")
        )
        connection.execute(schema_info.insert().values(version=3))

        migrate_schema(connection)
        count = connection.execute(text("SELECT COUNT(*) FROM groups_hosts")).scalar_one()

    assert count == 1


def test_conflicting_duplicate_variable_rows_reject_migration(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}", future=True)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE hosts (id INTEGER PRIMARY KEY, name TEXT UNIQUE)"))
        connection.execute(
            text(
                "CREATE TABLE hostvars "
                "(id INTEGER PRIMARY KEY, host_id INTEGER, name TEXT, value TEXT)"
            )
        )
        connection.execute(
            text("CREATE TABLE schema_info (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)")
        )
        connection.execute(text("INSERT INTO hosts (id, name) VALUES (1, 'web01')"))
        connection.execute(
            text(
                "INSERT INTO hostvars (host_id, name, value) "
                "VALUES (1, 'env', 'prod'), (1, 'env', 'dev')"
            )
        )
        connection.execute(schema_info.insert().values(version=3))

        with pytest.raises(DatabaseError, match="conflicting duplicates"):
            migrate_schema(connection)


def test_exact_duplicate_variable_rows_are_collapsed(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}", future=True)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE groups (id INTEGER PRIMARY KEY, name TEXT UNIQUE)"))
        connection.execute(
            text(
                "CREATE TABLE groupvars "
                "(id INTEGER PRIMARY KEY, group_id INTEGER, name TEXT, value TEXT)"
            )
        )
        connection.execute(
            text("CREATE TABLE schema_info (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)")
        )
        connection.execute(text("INSERT INTO groups (id, name) VALUES (1, 'web')"))
        connection.execute(
            text(
                "INSERT INTO groupvars (group_id, name, value) "
                "VALUES (1, 'role', 'frontend'), (1, 'role', 'frontend')"
            )
        )
        connection.execute(schema_info.insert().values(version=3))

        migrate_schema(connection)
        values = connection.execute(select(groupvars.c.value)).scalars().all()

    assert values == ["frontend"]


def test_sqlite_backup_copies_database_file(tmp_path: Path) -> None:
    source = tmp_path / "inventory.db"
    destination = tmp_path / "backup" / "inventory.db"
    database = database_from_settings(sqlite_settings(source))
    database.migrate()

    copied = backup_sqlite(database, destination)

    assert copied == destination.resolve()
    assert copied.read_bytes() == source.read_bytes()


def test_non_sqlite_backup_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOOSE_PASSWORD", "secret")
    database = database_from_settings(
        {
            "adapter": "postgresql",
            "host": "localhost",
            "database": "inventory",
            "user": "moose",
            "password_env": "MOOSE_PASSWORD",
        }
    )

    with pytest.raises(DatabaseError, match="supported for sqlite3 only"):
        backup_sqlite(database, tmp_path / "backup.db")
