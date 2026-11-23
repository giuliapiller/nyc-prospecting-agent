"""Small HTTP helper: one shared session, retries, polite delays and an on-disk cache."""
import hashlib
import json
import logging
import os
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

CACHE_DIR = Path(os.environ.get("PROSPECTING_CACHE_DIR", ".cache"))
CACHE_TTL_SECONDS = int(os.environ.get("PROSPECTING_CACHE_TTL", 20 * 3600))
USER_AGENT = "nyc-prospecting-agent/0.1 (+https://github.com/giuliapiller/nyc-prospecting-agent)"

_sessions: dict[bool, requests.Session] = {}


def session(retries: bool = True) -> requests.Session:
    if retries not in _sessions:
        s = requests.Session()
        retry = Retry(total=3, backoff_factor=1.0, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET",), respect_retry_after_header=True) if retries else Retry(0, redirect=5)
        s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=16))
        s.headers["User-Agent"] = USER_AGENT
        _sessions[retries] = s
    return _sessions[retries]


def _cache_path(url: str) -> Path:
    return CACHE_DIR / (hashlib.sha256(url.encode()).hexdigest() + ".json")


def get(url: str, *, as_json: bool = True, use_cache: bool = True, timeout: int = 30, headers=None,
        retries: bool = True, quiet: bool = False):
    """GET a URL. Returns (status_code, body) where body is parsed JSON or text. Cached on success and 404."""
    path = _cache_path(url)
    if use_cache and path.exists() and time.time() - path.stat().st_mtime < CACHE_TTL_SECONDS:
        cached = json.loads(path.read_text())
        return cached["status"], cached["body"]
    try:
        resp = session(retries).get(url, timeout=timeout, headers=headers)
    except requests.RequestException as exc:
        (log.debug if quiet else log.warning)("GET %s failed: %s", url, exc)
        return None, None
    body = None
    if resp.status_code == 200:
        try:
            body = resp.json() if as_json else resp.text
        except ValueError:
            body = None
    if use_cache and resp.status_code in (200, 404):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"status": resp.status_code, "body": body}))
    return resp.status_code, body
