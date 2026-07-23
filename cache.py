"""Thread-safe TTL cache for variance results, keyed on the date range.

Each (from, to) query is a ~20-30s scan over production history on Azure SQL.
Caching the built payload keeps concurrent users off the same expensive scan.
"""

from __future__ import annotations

import threading
from datetime import date

from cachetools import TTLCache

from .build import build_payload, fetch_job_variance
from .config import get_settings

_lock = threading.Lock()
_cache: TTLCache | None = None


def _get_cache() -> TTLCache:
    global _cache
    if _cache is None:
        s = get_settings()
        _cache = TTLCache(maxsize=s.cache_maxsize, ttl=max(s.cache_ttl, 1))
    return _cache


def get_variance_payload(engine, d_from: date, d_to: date) -> list[dict]:
    """Return cached payload for the range, computing + caching on a miss.

    Caching is skipped entirely when CACHE_TTL <= 0.
    """
    s = get_settings()
    key = (d_from.isoformat(), d_to.isoformat())

    if s.cache_ttl <= 0:
        df = fetch_job_variance(engine, d_from, d_to)
        return build_payload(df)

    cache = _get_cache()
    with _lock:
        hit = cache.get(key)
    if hit is not None:
        return hit

    df = fetch_job_variance(engine, d_from, d_to)
    payload = build_payload(df)
    with _lock:
        cache[key] = payload
    return payload


def clear() -> None:
    with _lock:
        if _cache is not None:
            _cache.clear()
