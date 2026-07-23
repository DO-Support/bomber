"""gunicorn configuration for the variance app.

The iSync date-range query can take 20-30s, so worker/timeouts are generous.
Keep workers low: each holds a SQLAlchemy pool to Azure SQL.
"""

import multiprocessing
import os

bind = os.environ.get("BIND", "0.0.0.0:8000")
worker_class = "uvicorn.workers.UvicornWorker"
# CPU-light, IO-bound (waiting on SQL). Modest worker count.
workers = int(os.environ.get("WEB_CONCURRENCY", min(4, multiprocessing.cpu_count() * 2 + 1)))
# Must exceed the slowest query comfortably (query ~20-30s + overhead).
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")
forwarded_allow_ips = "*"  # behind nginx on the internal compose network
