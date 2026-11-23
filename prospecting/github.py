"""Phase 2: public AI coding-tool signals in each company's GitHub org(s).

Only public org and repo metadata and file paths are read. No members, commit authors or other personal data.
"""
import csv
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

from . import http
from .companies import Company, load_companies, normalize_name

log = logging.getLogger(__name__)

API = "https://api.github.com"
MAX_ORGS_PER_COMPANY = 5

# Each check is one code-search query per org; `match` filters the returned paths (search is fuzzy on paths).
@dataclass(frozen=True)
class FileCheck:
    tool: str
    label: str
    query: str
    match: re.Pattern


CHECKS = [
    FileCheck("cursor", ".cursorrules", "filename:.cursorrules", re.compile(r"(?:^|/)\.cursorrules$")),
    FileCheck("cursor", ".cursor/", "path:.cursor", re.compile(r"(?:^|/)\.cursor/")),
    FileCheck("claude_code", "CLAUDE.md", "filename:CLAUDE.md", re.compile(r"(?:^|/)CLAUDE\.md$")),
    FileCheck("agents_md", "AGENTS.md", "filename:AGENTS.md", re.compile(r"(?:^|/)AGENTS\.md$")),
    FileCheck("copilot", ".github/copilot-instructions.md", "filename:copilot-instructions.md",
              re.compile(r"(?:^|/)\.github/copilot-instructions\.md$")),
    FileCheck("copilot", ".github/instructions/", "path:.github/instructions",
              re.compile(r"(?:^|/)\.github/instructions/.+\.instructions\.md$")),
]
KEYBOARD_TOOLS = {"cursor": "Uses Cursor", "claude_code": "Uses Claude Code", "copilot": "Uses Copilot"}
AGENTS_ONLY = "AGENTS.md only"
NO_SIGNAL = "No public signal"


def tool_stack_label(tools: set[str]) -> str:
    keyboard = [t for t in KEYBOARD_TOOLS if t in tools]
    if len(keyboard) > 1:
        return "Mixed"
    if keyboard:
        return KEYBOARD_TOOLS[keyboard[0]]
    return AGENTS_ONLY if "agents_md" in tools else NO_SIGNAL


def _host(url: str) -> str:
    url = (url or "").strip().lower()
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    return (urlparse(url).hostname or "").removeprefix("www.")


def domain_matches(company: Company, org: dict) -> tuple[str, bool]:
    """('blog: x' / 'email: x', exact) if the org's website or email is on the company's domain (exact=True)
    or on a sibling domain named after the company, like americanexpress.io or techatbloomberg.com (exact=False)."""
    domain = company.website.lower().removeprefix("www.")
    stem = company.domain_stem
    sibling = ("", False)
    for field, host in (("blog", _host(org.get("blog"))), ("email", (org.get("email") or "").lower().partition("@")[2])):
        if not host:
            continue
        if host == domain or host.endswith("." + domain):
            return f"{field}: {host}", True
        sld = host.rsplit(".", 2)[-2] if "." in host else host
        if len(stem) >= 4 and sld.endswith(stem) and not sibling[0]:
            sibling = (f"{field}: {host}", False)
    return sibling


def is_company_org(company: Company, org: dict) -> str:
    """Anyone can type any website into an org profile, so the domain alone isn't enough.

    Exact domain: the org must be GitHub-verified or have a login containing the company name/domain stem.
    Sibling domain (alexslemonade.org, lemonade.social): the login must *be* the company name/domain stem.
    """
    ev, exact = domain_matches(company, org)
    if not ev or not org.get("public_repos"):
        return ""
    login = re.sub(r"[^a-z0-9]", "", org["login"].lower())
    keys = {company.domain_stem, normalize_name(company.name).replace(" ", "")}
    ok = (org.get("is_verified") or any(k and k in login for k in keys)) if exact else login in keys
    return ev + (", verified" if org.get("is_verified") else "") if ok else ""


class GitHub:
    """Tiny GitHub REST client: auth, per-bucket pacing, rate-limit backoff, and the shared on-disk cache."""
    INTERVALS = {"core": 0.1, "search": 2.2, "code_search": 6.5}  # 30 search/min, 10 code-search/min

    def __init__(self, token: str | None):
        self.s = requests.Session()
        self.s.headers.update({"Accept": "application/vnd.github+json", "User-Agent": http.USER_AGENT,
                               "X-GitHub-Api-Version": "2022-11-28"})
        if token:
            self.s.headers["Authorization"] = f"Bearer {token}"
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def _pace(self, bucket: str) -> None:
        with self._lock:
            wait = self._last.get(bucket, 0) + self.INTERVALS[bucket] - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last[bucket] = time.monotonic()

    def get(self, path: str, bucket: str = "core"):
        url = API + path
        cache = http._cache_path(url)
        if cache.exists() and time.time() - cache.stat().st_mtime < http.CACHE_TTL_SECONDS:
            c = json.loads(cache.read_text())
            return c["status"], c["body"]
        for attempt in range(5):
            self._pace(bucket)
            try:
                r = self.s.get(url, timeout=30)
            except requests.RequestException as exc:
                log.warning("GitHub %s failed: %s", path, exc)
                time.sleep(2 ** attempt)
                continue
            if r.status_code in (403, 429) and ("retry-after" in r.headers or r.headers.get("x-ratelimit-remaining") == "0"):
                wait = int(r.headers.get("retry-after") or max(1, int(r.headers.get("x-ratelimit-reset", 0)) - time.time())) + 1
                log.info("GitHub rate limit (%s); sleeping %ss", bucket, wait)
                time.sleep(min(wait, 3700))
                continue
            if r.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            body = r.json() if r.status_code == 200 else None
            if r.status_code in (200, 404, 422):
                http.CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps({"status": r.status_code, "body": body}))
            else:
                log.warning("GitHub %s -> %s", path, r.status_code)
            return r.status_code, body
        return None, None

    def org(self, login: str) -> dict | None:
        status, body = self.get(f"/orgs/{quote(login)}")
        return body if status == 200 and body and body.get("type", "Organization") == "Organization" else None

    def search_orgs(self, text: str) -> list[str]:
        status, body = self.get(f"/search/users?q={quote(text + ' type:org')}&per_page=10", "search")
        return [i["login"] for i in (body or {}).get("items", [])] if status == 200 else []

    def search_code(self, query: str, org: str) -> tuple[int, list[dict]] | None:
        status, body = self.get(f"/search/code?q={quote(query + ' org:' + org)}&per_page=100", "code_search")
        if status != 200 or body is None:
            return None
        return body.get("total_count", 0), body.get("items", [])


def find_orgs(gh: GitHub, company: Company) -> list[tuple[dict, str]]:
    """Candidate orgs from org search + login guesses, kept only if their website/email is on the company domain."""
    name = normalize_name(company.name)
    candidates = list(dict.fromkeys(
        [name.replace(" ", ""), name.replace(" ", "-"), company.domain_stem]
        + gh.search_orgs(company.name) + gh.search_orgs(company.domain_stem)))
    found = []
    for login in candidates:
        org = gh.org(login)
        if org and (ev := is_company_org(company, org)) and org["login"] not in {o["login"] for o, _ in found}:
            found.append((org, ev))
    found.sort(key=lambda x: -x[0].get("public_repos", 0))
    return found[:MAX_ORGS_PER_COMPANY]


def scan_org(gh: GitHub, org: str) -> tuple[list[dict], bool]:
    """Return matched AI-config files in the org's public (non-fork) repos and whether every query succeeded."""
    files, complete = [], True
    for check in CHECKS:
        res = gh.search_code(check.query, org)
        if res is None:
            complete = False
            continue
        total, items = res
        if total > len(items):
            log.debug("%s %s: %d results, first %d inspected", org, check.label, total, len(items))
        for it in items:
            if check.match.search(it["path"]):
                files.append({"org": org, "repo": it["repository"]["full_name"], "tool": check.tool,
                              "file_type": check.label, "path": it["path"], "url": it["html_url"]})
    return files, complete


def _load_overrides(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["company"].strip(): [o.strip() for o in r["orgs"].split(";") if o.strip()]
                for r in csv.DictReader(f) if r.get("company")}


def summarize(files: list[dict]) -> dict:
    repos = {t: sorted({f["repo"] for f in files if f["tool"] == t}) for t in [*KEYBOARD_TOOLS, "agents_md"]}
    by_type: dict[str, set] = {}
    for f in files:
        by_type.setdefault(f["file_type"], set()).add(f["repo"])
    return {
        "tool_stack_label": tool_stack_label({t for t, r in repos.items() if r}),
        "cursor_repos": len(repos["cursor"]),
        "claude_code_repos": len(repos["claude_code"]),
        "copilot_repos": len(repos["copilot"]),
        "agents_md_repos": len(repos["agents_md"]),
        "ai_files_found": "; ".join(f"{t} ({len(r)} repo{'s' * (len(r) != 1)})" for t, r in sorted(by_type.items())),
        "example_repos": "; ".join(sorted({f["repo"] for f in files})[:3]),
    }


COMPANY_FIELDS = ["company", "website", "github_orgs", "org_match", "tool_stack_label", "cursor_repos",
                  "claude_code_repos", "copilot_repos", "agents_md_repos", "ai_files_found", "example_repos",
                  "scan_complete"]
FILE_FIELDS = ["company", "org", "repo", "tool", "file_type", "path", "url"]


def run(companies_csv: Path, out_dir: Path, overrides_csv: Path) -> list[dict]:
    from .phase1 import _write
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        log.warning("GITHUB_TOKEN not set: code search needs auth, so every company will show '%s'", NO_SIGNAL)
    gh = GitHub(token)
    overrides = _load_overrides(overrides_csv)
    rows, all_files = [], []
    for company in load_companies(companies_csv):
        if company.name in overrides:
            orgs = [(o, "override") for login in overrides[company.name] if (o := gh.org(login))]
        else:
            orgs = find_orgs(gh, company)
        files, complete = [], True
        for org, _ in orgs:
            f, ok = scan_org(gh, org["login"]) if token else ([], False)
            files += f
            complete &= ok
        for f in files:
            f["company"] = company.name
        all_files += files
        row = {"company": company.name, "website": company.website,
               "github_orgs": "; ".join(o["login"] for o, _ in orgs),
               "org_match": "; ".join(f"{o['login']} ({ev})" for o, ev in orgs) or "no org found",
               "scan_complete": "yes" if complete and token else "no", **summarize(files)}
        rows.append(row)
        log.info("%-20s orgs=%-30s %s", company.name, row["github_orgs"] or "-", row["tool_stack_label"])
    _write(out_dir / "phase2_github.csv", COMPANY_FIELDS, rows)
    _write(out_dir / "phase2_ai_files.csv", FILE_FIELDS, all_files)
    log.info("Phase 2 done: %d/%d companies with a GitHub org; labels: %s", sum(bool(r["github_orgs"]) for r in rows),
             len(rows), {l: sum(r["tool_stack_label"] == l for r in rows) for l in {r["tool_stack_label"] for r in rows}})
    return rows
