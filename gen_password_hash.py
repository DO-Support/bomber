#!/usr/bin/env python3
"""Generate bcrypt hashes for APP_USERS.

    python scripts/gen_password_hash.py                       # single bare hash
    python scripts/gen_password_hash.py --user alice --user bob   # → APP_USERS JSON

Password is read interactively (never via argv, so it won't hit shell history).
Pipe stdout into ./secrets/app_users.json for the compose secret.
"""

from __future__ import annotations

import argparse
import getpass
import json

import bcrypt


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8")[:72], bcrypt.gensalt()).decode("ascii")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", action="append", default=[],
                    help="Username (repeatable). Omit for a single bare hash.")
    args = ap.parse_args()

    if not args.user:
        print(_hash(getpass.getpass("Password: ")))
        return

    out = {u: _hash(getpass.getpass(f"Password for {u}: ")) for u in args.user}
    print(json.dumps(out))


if __name__ == "__main__":
    main()
