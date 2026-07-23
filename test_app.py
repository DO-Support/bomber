"""Endpoint + auth tests against the real FastAPI app (DB layer patched)."""

from __future__ import annotations


def test_healthz_open(app_client):
    r = app_client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_index_redirects_when_anonymous(app_client):
    r = app_client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_data_requires_auth(app_client):
    r = app_client.get("/data?from=2026-05-01&to=2026-06-01")
    assert r.status_code == 401
    assert r.json()["login"] == "/login"


def test_login_bad_credentials(app_client):
    r = app_client.post("/login", data={"username": "alice", "password": "wrong"},
                        follow_redirects=False)
    assert r.status_code == 401
    assert "Invalid username or password" in r.text


def test_login_then_access(app_client, monkeypatch):
    # Patch the expensive DB/query path so /data returns a canned payload.
    from jobvariance import app as app_module

    monkeypatch.setattr(
        "jobvariance.cache.get_variance_payload",
        lambda engine, d_from, d_to: [{"JobNumber": "DO-1", "Variance": 0.0}],
    )
    # Avoid building a real engine.
    monkeypatch.setattr(app_module, "get_engine", lambda: object())

    r = app_client.post("/login", data={"username": "alice", "password": "s3cret"},
                        follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"

    # Session cookie now set on the client; protected routes work.
    r = app_client.get("/", follow_redirects=False)
    assert r.status_code == 200
    assert "Job Material Variance" in r.text

    r = app_client.get("/data?from=2026-05-01&to=2026-06-01")
    assert r.status_code == 200
    assert r.json()[0]["JobNumber"] == "DO-1"


def test_data_validation(app_client, monkeypatch):
    app_client.post("/login", data={"username": "alice", "password": "s3cret"})
    # Missing params.
    assert app_client.get("/data").status_code == 400
    # Inverted range.
    assert app_client.get("/data?from=2026-06-01&to=2026-05-01").status_code == 400
    # Oversized range.
    assert app_client.get("/data?from=2020-01-01&to=2026-01-01").status_code == 400


def test_logout_clears_session(app_client):
    app_client.post("/login", data={"username": "alice", "password": "s3cret"})
    app_client.get("/logout", follow_redirects=False)
    # Back to anonymous.
    r = app_client.get("/", follow_redirects=False)
    assert r.status_code == 303
