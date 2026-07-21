"""Local live server for the job material variance dashboard.

Serves the dashboard in LIVE mode: pick any start/end date in the browser and the
page queries iSync on demand (GET /data?from=YYYY-MM-DD&to=YYYY-MM-DD). Binds to
localhost only. Requires a populated .env (MSSQL_* credentials).

    python -m jobvariance.serve                 # opens http://127.0.0.1:8765/
    python -m jobvariance.serve --port 9000 --no-open
"""

from __future__ import annotations

import argparse
import json
import webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .build import build_payload, fetch_job_variance, render_html
from .db import get_engine

_SUBTITLE = "Standard vs actual issued (Rand + units) · iSync live · pick any date range"


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _make_handler(engine):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the console quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                html = render_html([], "Job Material Variance", _SUBTITLE, live=True)
                self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
                return
            if u.path == "/data":
                q = parse_qs(u.query)
                try:
                    d_from = _parse_date(q["from"][0])
                    d_to = _parse_date(q["to"][0])
                except (KeyError, IndexError, ValueError):
                    self._send(400, b'{"error":"from and to required as YYYY-MM-DD"}',
                               "application/json")
                    return
                try:
                    df = fetch_job_variance(engine, d_from, d_to)
                    body = json.dumps(build_payload(df)).encode("utf-8")
                    self._send(200, body, "application/json")
                except Exception as e:  # surface DB/query errors to the page
                    self._send(500, json.dumps({"error": str(e)}).encode("utf-8"),
                               "application/json")
                return
            self._send(404, b"not found", "text/plain")

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Serve the job material variance dashboard with live date selection."
    )
    ap.add_argument("--host", default="127.0.0.1", help="Bind address (default localhost).")
    ap.add_argument("--port", type=int, default=8765, help="Port (default 8765).")
    ap.add_argument("--no-open", action="store_true", help="Do not auto-open the browser.")
    args = ap.parse_args()

    engine = get_engine()  # fails fast if .env / credentials are missing
    httpd = ThreadingHTTPServer((args.host, args.port), _make_handler(engine))
    url = f"http://{args.host}:{args.port}/"
    print(f"Job material variance — live dashboard at {url}  (Ctrl+C to stop)")
    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        httpd.server_close()


if __name__ == "__main__":
    main()
