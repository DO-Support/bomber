"""Typed application configuration.

All settings come from environment variables (or a local `.env` in dev). In the
container, values are injected via env / Docker secrets — nothing is baked into
the image. Azure SQL defaults to encrypted transport with a validated cert.
"""

from __future__ import annotations

import json
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- MS SQL (Azure SQL: encrypt on, validated cert) ---
    mssql_server: str = Field(alias="MSSQL_SERVER")
    mssql_port: str = Field("1433", alias="MSSQL_PORT")
    mssql_database: str = Field(alias="MSSQL_DATABASE")
    mssql_username: str = Field(alias="MSSQL_USERNAME")
    mssql_password: str = Field(alias="MSSQL_PASSWORD")
    mssql_driver: str = Field("ODBC Driver 18 for SQL Server", alias="MSSQL_DRIVER")
    mssql_encrypt: str = Field("yes", alias="MSSQL_ENCRYPT")
    mssql_trust_server_certificate: str = Field(
        "no", alias="MSSQL_TRUST_SERVER_CERTIFICATE"
    )

    # --- Session / auth ---
    # Signing key for session cookies. MUST be set to a long random value in prod.
    session_secret: str = Field(alias="SESSION_SECRET")
    # Session lifetime in seconds (default 12h).
    session_max_age: int = Field(43_200, alias="SESSION_MAX_AGE")
    # Cookie marked Secure (HTTPS only). True in prod (nginx terminates TLS).
    session_https_only: bool = Field(True, alias="SESSION_HTTPS_ONLY")
    # JSON mapping {username: bcrypt_hash}. Generate hashes with
    # scripts/gen_password_hash.py.
    app_users: dict[str, str] = Field(default_factory=dict, alias="APP_USERS")

    # --- Query cache ---
    # Seconds to cache a (from, to) result. Blunts the 20-30s Azure query under
    # concurrent users. 0 disables.
    cache_ttl: int = Field(300, alias="CACHE_TTL")
    cache_maxsize: int = Field(64, alias="CACHE_MAXSIZE")

    @field_validator("app_users", mode="before")
    @classmethod
    def _parse_users(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return {}
            return json.loads(v)
        return v

    def odbc_connection_string(self) -> str:
        return (
            f"DRIVER={{{self.mssql_driver}}};"
            f"SERVER={self.mssql_server},{self.mssql_port};"
            f"DATABASE={self.mssql_database};"
            f"UID={self.mssql_username};PWD={self.mssql_password};"
            f"Encrypt={self.mssql_encrypt};"
            f"TrustServerCertificate={self.mssql_trust_server_certificate};"
            f"ApplicationIntent=ReadOnly"
        )


@lru_cache
def get_settings() -> Settings:
    """Cached singleton. Import and call at runtime, not import time, so tests can
    override env before the first access."""
    return Settings()  # type: ignore[call-arg]
