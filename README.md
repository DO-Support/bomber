# Job Material Variance — live dashboard

Standard cost content vs actual raw-material issued, per job, pulled live from iSync
(Azure SQL). FastAPI app under gunicorn/uvicorn, behind nginx (self-signed TLS over
VPN), app-level session login. nginx is the only published container.

> **Running this in production or inherited it?** See [`OPERATIONS.md`](OPERATIONS.md)
> for day-to-day operation: adding users, regenerating the cert, diagnostics, backups,
> and the two "numbers look wrong but aren't" caveats. This README covers setup; that
> one covers keeping it alive.

## Deploy (Docker)

```bash
# 1. TLS cert (self-signed; set the hostname users will type)
./scripts/gen_selfsigned_cert.sh jmv.internal.lan     # → ./certs/{fullchain,privkey}.pem

# 2. Secrets (never committed — see .gitignore)
mkdir -p secrets
printf '%s' 'YOUR_AZURE_SQL_PASSWORD'                       > secrets/mssql_password.txt
python3 -c "import secrets;print(secrets.token_urlsafe(48))" > secrets/session_secret.txt
python3 scripts/gen_password_hash.py --user user1 --user user2 > secrets/app_users.json

# 3. Non-secret env (server, db, database, username, tuning)
cp .env.example .env        # edit MSSQL_SERVER / MSSQL_DATABASE / MSSQL_USERNAME etc.

# 4. Up
sudo docker compose up -d --build
```

Then browse to `https://jmv.internal.lan/` (accept the self-signed cert once). Plain
HTTP is redirected to HTTPS.

`secrets/` and `certs/` are gitignored and exist only on the host — **back them up**
(see OPERATIONS.md); losing them means regenerating every secret and re-entering
passwords.

## What runs where

| Piece            | Detail                                                               |
|------------------|----------------------------------------------------------------------|
| `nginx`          | Publishes 80/443. TLS terminate, HTTP→HTTPS, proxy to `app:8000`.    |
| `app`            | gunicorn + UvicornWorker, internal-only. Queries Azure SQL on demand.|
| Auth             | Session cookie (signed, Secure, HttpOnly, SameSite=Lax). bcrypt users.|
| DB               | `Encrypt=yes`, `TrustServerCertificate=no`, read-only intent.         |
| Cache            | Per date-range TTL (`CACHE_TTL`, default 300s) — blunts the 20-30s scan.|
| Health           | `GET /healthz` (liveness); `GET /healthz?deep=1` also pings the DB.   |

The app image is built on `python:3.12-slim-bookworm` and installs Microsoft's
`msodbcsql18` via `packages-microsoft-prod.deb` (Debian 12). The base image is pinned
to bookworm on purpose — the Microsoft ODBC repo is published per named release, so a
rolling `slim` tag that moves to a newer Debian breaks the driver install.

## Repository layout

```
jobvariance/
  app.py          FastAPI routes: /login /logout / /data /healthz
  build.py        the variance SQL + pandas math (the core logic)
  db.py           read-only SQLAlchemy engine to Azure SQL
  config.py       env-driven settings (pydantic-settings)
  auth.py         bcrypt credential check + session gate
  cache.py        per-date-range TTL cache
  mock.py         bundled fake data for --mock (no DB)
  templates/      job_variance.html (dashboard) + login.html
nginx/            nginx.conf + conf.d/dashboard.conf (TLS + proxy)
scripts/          gen_selfsigned_cert.sh, gen_password_hash.py
sql/              standalone reference copy of the variance query
tests/            variance math + auth/session/endpoint tests
Dockerfile, docker-compose.yml, gunicorn_conf.py
OPERATIONS.md     run-it / hand-it-over runbook
```

Config that lives **only on the host, never in git:** `.env`, `secrets/`, `certs/`.

## Local dev (no Docker)

```bash
pip install -r requirements-dev.txt          # needs unixODBC + msodbcsql18 for a real DB
cp .env.example .env                          # set SESSION_HTTPS_ONLY=false for http
uvicorn jobvariance.app:app --reload --port 8765
```

Static (offline) build for a point-in-time snapshot — no server, no login:

```bash
python -m jobvariance.build --from 2026-05-01 --to 2026-07-16 --out dashboard.html
python -m jobvariance.build --mock --out demo.html        # bundled fake data
```

## Tests & CI

```bash
ruff check .
pytest                    # 11 tests: variance math + auth/session/endpoint gates
```

CI (`.github/workflows/ci.yml`) runs lint, tests, and a Docker build on push/PR.
The DB layer is monkeypatched in tests, so no live Azure SQL is needed.

## Operational notes

- **Add/rotate a user:** regenerate `secrets/app_users.json` (list *all* users you
  want to keep — it rewrites the file) and restart the app: `sudo docker compose up -d app`.
  Users load from `APP_USERS` at process start, so the restart is required. Passwords
  are bcrypt-hashed; plaintext never leaves your shell. Full steps in OPERATIONS.md.
- **Sessions** last `SESSION_MAX_AGE` (default 12h). On expiry the dashboard's `/data`
  call gets a 401 and the page redirects to `/login`.
- **Query window** is capped at 400 days server-side to avoid pathological scans.
- `build.py` selects jobs by first production receipt, then compares each side's FULL
  job totals (never windowed per movement) — see its module docstring for why, and
  OPERATIONS.md for the fabric-holding-job caveat that makes some jobs read under-issued.
