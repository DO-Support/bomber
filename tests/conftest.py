"""Test fixtures. No real DB is touched: DB-backed routes are monkeypatched.

Auth, session, request validation and the variance math are all exercised
against real code paths.
"""

from __future__ import annotations

import json

import pytest

# Minimal env so Settings() constructs without a real .env / Azure SQL.
_TEST_ENV = {
    "MSSQL_SERVER": "test.database.windows.net",
    "MSSQL_DATABASE": "TestDB",
    "MSSQL_USERNAME": "tester",
    "MSSQL_PASSWORD": "pw",
    "SESSION_SECRET": "test-secret-not-for-prod",
    "SESSION_HTTPS_ONLY": "false",   # TestClient uses http
    "CACHE_TTL": "0",                # disable caching in tests
}


@pytest.fixture
def app_client(monkeypatch):
    for k, v in _TEST_ENV.items():
        monkeypatch.setenv(k, v)

    from jobvariance.auth import hash_password

    monkeypatch.setenv("APP_USERS", json.dumps({"alice": hash_password("s3cret")}))

    # Rebuild the cached settings after env is in place.
    from jobvariance import config
    config.get_settings.cache_clear()

    from fastapi.testclient import TestClient

    from jobvariance.app import create_app

    app = create_app(config.get_settings())
    return TestClient(app)
