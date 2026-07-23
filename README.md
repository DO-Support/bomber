# Job Material Variance — live dashboard

Standard cost content vs actual raw-material issued, per job, pulled live from iSync
(Azure SQL). FastAPI app under gunicorn/uvicorn, behind nginx (self-signed TLS over
VPN), app-level session login. nginx is the only published container.

## Deploy (Docker)

```bash
# 1. TLS cert (self-signed; set the hostname users will type)
./gen_selfsigned_cert.sh jmv.internal.lan        # → ./certs/{fullchain,privkey}.pem

# 2. Secrets (never committed — see .gitignore)
mkdir -p secrets
printf '%s' 'YOUR_AZURE_SQL_PASSWORD'            > secrets/mssql_password.txt
python -c "import secrets;print(secrets.token_urlsafe(48))" > secrets/session_secret.txt
python gen_password_hash.py --user user1 --user user2 > secrets/app_users.json

# 3. Non-secret env (server, db, database, username, tuning)
cp .env.example .env        # edit MSSQL_SERVER / MSSQL_DATABASE / MSSQL_USERNAME etc.

# 4. Up
docker compose up -d --build
```

Then browse to `https://jmv.internal.lan/` (accept the self-signed cert once). Plain
HTTP is redirected to HTTPS.

## What runs where

| Piece            | Detail                                                               |
|------------------|----------------------------------------------------------------------|
| `nginx`          | Publishes 80/443. TLS terminate, HTTP→HTTPS, proxy to `app:8000`.    |
| `app`            | gunicorn + UvicornWorker, internal-only. Queries Azure SQL on demand.|
| Auth             | Session cookie (signed, Secure, HttpOnly, SameSite=Lax). bcrypt users.|
| DB               | `Encrypt=yes`, `TrustServerCertificate=no`, read-only intent.         |
| Cache            | Per date-range TTL (`CACHE_TTL`, default 300s) — blunts the 20-30s scan.|
| Health           | `GET /healthz` (liveness); `GET /healthz?deep=1` also pings the DB.   |

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

- **Sessions** last `SESSION_MAX_AGE` (default 12h). On expiry the dashboard's `/data`
  call gets a 401 and the page redirects to `/login`.
- **Rotate a user:** regenerate `secrets/app_users.json` and `docker compose up -d` the
  `app` service. Passwords are bcrypt-hashed; plaintext never leaves your shell.
- **Query window** is capped at 400 days server-side to avoid pathological scans.
- `build.py` selects jobs by first production receipt, then compares each side's FULL
  job totals (never windowed per movement) — see its module docstring for why.
