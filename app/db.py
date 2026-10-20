"""The app's SQLite database: engine, sessions and the exact-money column type."""

from decimal import Decimal
from pathlib import Path

from sqlalchemy import String, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.types import TypeDecorator


class Money(TypeDecorator):
    """A Decimal stored as text such as "550.00", so SQLite never rounds it."""

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(Decimal(value).quantize(Decimal("0.01")))

    def process_result_value(self, value, dialect):
        return None if value is None else Decimal(value)


def make_engine(db_path: Path) -> Engine:
    """An engine for the SQLite file, in write-ahead logging mode with foreign keys on."""
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(engine, expire_on_commit=False)
