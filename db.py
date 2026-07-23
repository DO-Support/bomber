"""MS SQL connectivity for the iSync database (read-only usage).

The engine is built from the typed `Settings`. Azure SQL uses an encrypted,
cert-validated connection (`Encrypt=yes`, `TrustServerCertificate=no`).
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote_plus

import pandas as pd
import sqlalchemy as sa

from .config import Settings, get_settings


def build_engine(settings: Settings | None = None) -> sa.Engine:
    settings = settings or get_settings()
    odbc = settings.odbc_connection_string()
    return sa.create_engine(
        f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc)}",
        pool_pre_ping=True,
        pool_recycle=1800,
    )


@lru_cache
def get_engine() -> sa.Engine:
    """Process-wide singleton engine (connection pool shared across workers'
    requests within a process)."""
    return build_engine()


def read_sql(engine: sa.Engine, sql: str, params: dict | None = None) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(sa.text(sql), conn, params=params)
