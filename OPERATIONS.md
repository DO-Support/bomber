# Operations & Handover Guide

This is the "run it a year from now / hand it to the next person" document. For
first-time deployment see `README.md`; this covers day-to-day operation, the
things that look broken but aren't, and where the bodies are buried.

---

## Mental model (read this first)

Three layers, each replaceable without touching the others:

```
Browser ──TLS──> nginx (container) ──HTTP──> FastAPI app (container) ──read-only──> Azure SQL (iSync)
                  edge / TLS / proxy         routing + variance math               3 Reporting.* views
```

- **nginx** is the only container exposed to the LAN/VPN. Terminates the
  self-signed TLS, gates nothing itself, just proxies to the app.
- **app** (gunicorn + 3 uvicorn workers) does login/session, runs the variance
  query on demand, returns JSON. Never writes to the database.
- **Azure SQL** is read-only (`ApplicationIntent=ReadOnly`). Three views only:
  `vProductStockMovements`, `vStockMovements`, `v_RMA_CurrentRequired_NoFilter`.

Data flows one direction. The app can never modify iSync.

**Where a problem lives, by symptom:**
- TLS warning / redirect loop / port issue → **nginx**
- Page loads but "Error loading data" / won't authenticate → **app**
- Page works but the *numbers* look wrong → **SQL / views** (almost always one of
  the two caveats below, not a bug)

---

## The files that live ONLY on the VM (never in git)

These are gitignored by design and exist nowhere else. **If the VM dies, the repo
rebuilds in minutes but these must be recreated by hand.**

| Path | What it is | How to recreate |
|---|---|---|
| `.env` | DB connection (server, database, username) + tuning | `cp .env.example .env`, edit |
| `secrets/mssql_password.txt` | Azure SQL password | paste the real password |
| `secrets/session_secret.txt` | cookie signing key | `python3 -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `secrets/app_users.json` | `{username: bcrypt_hash}` | `python3 scripts/gen_password_hash.py --user NAME` |
| `certs/fullchain.pem`, `certs/privkey.pem` | self-signed TLS | `./scripts/gen_selfsigned_cert.sh <hostname>` |

> **BACK THESE UP.** Keep an encrypted copy of `.env`, `secrets/`, and `certs/`
> somewhere safe (password manager or encrypted archive). Losing the VM without
> this backup means regenerating every secret and re-entering every password.

---

## Common tasks

### Add or change a user

Users are loaded from `APP_USERS` **once at process start** — not a database.
Editing the file does nothing until the app restarts.

```bash
cd ~/bomber
# list EVERY user you want to keep — this rewrites the whole file
python3 scripts/gen_password_hash.py --user alice --user bob --user newperson > secrets/app_users.json
sudo docker compose up -d app          # restart app only; ~2s, nginx untouched
```

Pitfall: only listing the new user overwrites the file and locks everyone else
out. Regenerate with the full list, or hand-append one `"name": "$2b$..."` entry
(generate a bare hash with `gen_password_hash.py` and no `--user`).

`up -d app` is a *restart*, not a rebuild — don't add `--build` (no code changed).
Existing logged-in sessions on other machines stay valid.

### Change the code (edit a template, tweak the app)

Code is baked into the image at build time (`COPY jobvariance/ ...`), so:

```bash
sudo docker compose up -d --build      # rebuild; ODBC + pip layers are cached, so fast
```

Then hard-refresh the browser (Ctrl-Shift-R) to bypass the cached page.

### Regenerate the TLS cert (expiry or hostname change)

```bash
./scripts/gen_selfsigned_cert.sh <hostname-or-ip>
sudo docker compose restart nginx
```

The cert is valid ~825 days. There is **no auto-reminder** — when it lapses,
browsers hard-block until regenerated. Put a calendar note now.

### Restart / stop / start

```bash
sudo docker compose restart            # both containers
sudo docker compose up -d app          # just the app
sudo docker compose down               # stop everything (data is in Azure, nothing lost)
sudo docker compose up -d              # start
```

---

## Health & diagnostics

```bash
sudo docker compose ps                 # both should be running/healthy
curl -k https://localhost/healthz            # liveness only — app is up?
curl -k https://localhost/healthz?deep=1     # also pings Azure SQL
sudo docker compose logs app --tail=50       # app logs (requests, errors)
sudo docker compose logs nginx --tail=50     # proxy/TLS logs
```

- `/healthz` → `{"status":"ok"}` — app process alive (no DB touched).
- `/healthz?deep=1` → `{"status":"ok","db":"ok"}` — reached the database.
  `degraded` + a 503 means the DB is unreachable: usually the VM's outbound IP
  isn't allowed through the Azure SQL firewall, or `MSSQL_SERVER` in `.env` is
  wrong. The error text is in the JSON and the app log.

The compose healthcheck polls plain `/healthz` every 30s (no DB), so routine
health checks do **not** hammer Azure. Don't point an external uptime monitor at
`?deep=1` on a tight interval — that runs a DB round-trip each time.

---

## The two things that make numbers look wrong (but aren't bugs)

Whoever maintains this **must** know these, or they'll chase phantom bugs:

1. **The date range selects jobs, not movements.** A job is in scope if its first
   production receipt falls in the window; both standard and actual are then the
   job's *full* totals across all dates, never clipped to the window. This is
   deliberate — fabric is cut weeks before the garment is received into finished
   goods, so windowing each side independently would compare a partial standard
   against a full actual and report enormous fake variances. (See the docstring
   in `jobvariance/build.py`.)

2. **Fabric issued under a holding/cutting job number shows as under-issued.**
   When material is issued against a cutting job rather than the DO, the DO's
   "actual" looks low and the variance flags under-issued. That is a real signal
   about how the job was booked, not a data error. Trims usually reconcile within
   a few percent; large fabric under-issues on a single job are worth confirming
   with whoever booked it before anyone acts on the rand figure.

Tolerance for On-track vs Over/Under-issued is **2%** (`TOLERANCE_PCT` in
`build.py`). The `/data` query window is capped at **400 days** (`app.py`) to
avoid pathological full-history scans.

---

## Config knobs (`.env`)

| Variable | Default | Effect |
|---|---|---|
| `CACHE_TTL` | 300 | Seconds to cache a date-range result. 0 disables. Blunts the 20-30s query under repeat views. |
| `SESSION_MAX_AGE` | 43200 | Session lifetime (12h). On expiry the page redirects to `/login`. |
| `SESSION_HTTPS_ONLY` | true | Cookie only sent over HTTPS. Keep true in production. |
| `MSSQL_SERVER` / `MSSQL_DATABASE` / `MSSQL_USERNAME` | — | Azure SQL target. |
| `WEB_CONCURRENCY` | 3 | gunicorn worker count. Each holds a DB pool; don't inflate needlessly. |

After changing `.env`: `sudo docker compose up -d app`.

---

## Performance note

Each new date range runs a job-set scan over production history — **~20-30s** on
Azure SQL. The page shows a loading state meanwhile; this is expected, not a hang.
Repeat views of the same range are served from cache instantly (until `CACHE_TTL`
expires). If snappier interaction is ever needed, the query can be optimised with
a temp-table job set — noted in the README, not yet done.

---

## Recommended maintenance (not yet in place)

- **Cap Docker logs** so they can't fill the disk over months. Add to each service
  in `docker-compose.yml`:
  ```yaml
  logging:
    driver: json-file
    options: { max-size: "10m", max-file: "3" }
  ```
- **Verify boot recovery:** `systemctl is-enabled docker` should say `enabled`, and
  a deliberate VM reboot should bring the dashboard back on its own
  (`restart: unless-stopped` is already set).
- **Back up the VM-only secrets/certs** (see the table above).

---

## Two working copies — keep them in sync

The repo is cloned on both a Windows machine and this VM. The rule that prevents
divergence: **commit + push wherever you made the edit, then `git pull` on the
other machine before touching it.** Edits made on the VM must be committed from
the VM (auth is set up there via `gh`); pushing from Windows won't include them.
