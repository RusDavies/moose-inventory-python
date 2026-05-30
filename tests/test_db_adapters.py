from __future__ import annotations

import os
from typing import Any

import pytest

from moose_inventory.db import DatabaseError, database_from_settings, network_database_url


def test_mysql_adapter_builds_pymysql_url_from_plaintext_password() -> None:
    url = network_database_url(
        {
            "adapter": "mysql",
            "host": "db.example.internal",
            "database": "moose_inventory",
            "user": "moose",
            "password": "secret",
        },
        adapter="mysql",
        drivername="mysql+pymysql",
    )

    assert url.drivername == "mysql+pymysql"
    assert url.host == "db.example.internal"
    assert url.database == "moose_inventory"
    assert url.username == "moose"
    assert url.password == "secret"


def test_postgresql_adapter_builds_psycopg_url_from_password_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MOOSE_TEST_DB_PASSWORD", "secret")

    url = network_database_url(
        {
            "adapter": "postgresql",
            "host": "db.example.internal",
            "database": "moose_inventory",
            "user": "moose",
            "password_env": "MOOSE_TEST_DB_PASSWORD",
        },
        adapter="postgresql",
        drivername="postgresql+psycopg",
    )

    assert url.drivername == "postgresql+psycopg"
    assert url.host == "db.example.internal"
    assert url.database == "moose_inventory"
    assert url.username == "moose"
    assert url.password == "secret"


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"adapter": "mysql", "host": "h", "database": "d"}, "Expected key user missing"),
        ({"adapter": "postgresql", "host": "h", "user": "u"}, "Expected key database missing"),
        (
            {"adapter": "mysql", "host": "h", "database": "d", "user": "u"},
            "Expected key password or password_env missing",
        ),
        (
            {
                "adapter": "postgresql",
                "host": "h",
                "database": "d",
                "user": "u",
                "password_env": "MOOSE_MISSING_PASSWORD",
            },
            "Environment variable MOOSE_MISSING_PASSWORD is not set",
        ),
    ],
)
def test_network_adapter_config_validation(settings: dict[str, Any], message: str) -> None:
    os.environ.pop("MOOSE_MISSING_PASSWORD", None)

    with pytest.raises(DatabaseError, match=message):
        database_from_settings(settings)
