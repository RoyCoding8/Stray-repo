"""The conversion must be lossless, not merely valid.

A URL that parses but drops the password connects as an anonymous local
user, so it reads the wrong store without raising.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, make_url

from settlement import db


def test_database_url_keeps_every_field_a_conninfo_carries():
    dsn = ("host=db.example.com port=5433 user=alice "
           "password='p@ss/w:rd' dbname=settle sslmode=verify-full "
           "connect_timeout=11 application_name=lane")
    url = make_url(db.database_url(dsn))
    assert url.drivername == "postgresql+psycopg"
    assert url.host == "db.example.com"
    assert url.port == 5433
    assert url.username == "alice"
    assert url.password == "p@ss/w:rd"
    assert url.database == "settle"
    assert url.query["sslmode"] == "verify-full"
    assert url.query["connect_timeout"] == "11"
    assert url.query["application_name"] == "lane"


def test_database_url_keeps_a_unix_socket_directory_out_of_the_authority():
    dsn = "host=/var/run/postgresql user=ubuntu dbname=settle"
    url = make_url(db.database_url(dsn))
    assert url.host is None
    assert url.query["host"] == "/var/run/postgresql"


def test_database_url_keeps_every_field_without_a_host():
    dsn = "user=ubuntu dbname=settle sslmode=require"
    url = make_url(db.database_url(dsn))
    assert url.host is None
    assert url.username == "ubuntu"
    assert url.database == "settle"
    assert url.query["sslmode"] == "require"


def test_database_url_refuses_a_conninfo_with_no_dbname():
    with pytest.raises(ValueError, match="names no database"):
        db.database_url("host=/var/run/postgresql user=ubuntu")


def test_database_url_connects_to_the_database_the_conninfo_names(migrated_db):
    from conftest_isolation import dbname_of

    engine = create_engine(db.database_url(migrated_db))
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT current_database()").scalar() \
            == dbname_of(migrated_db)
    engine.dispose()
