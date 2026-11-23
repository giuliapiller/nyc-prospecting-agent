"""Discover and fetch public job boards on Greenhouse, Lever and Ashby (public JSON endpoints only)."""
import html
import logging
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from . import http
from .companies import Company, normalize_name

log = logging.getLogger(__name__)

PROVIDERS = ("greenhouse", "lever", "ashby")
BOARD_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}
GREENHOUSE_META_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}"

# Best-effort ATS fingerprints on a company's careers page (used for logging skipped companies).
ATS_FINGERPRINTS = {
    "workday": r"myworkdayjobs\.com|workday\.com",
    "greenhouse": r"greenhouse\.io",
    "lever": r"jobs\.lever\.co",
    "ashby": r"jobs\.ashbyhq\.com",
    "eightfold": r"eightfold\.ai",
    "oracle": r"oraclecloud\.com/hcmUI",
    "successfactors": r"successfactors|sapsf\.",
    "taleo": r"taleo\.net",
    "icims": r"icims\.com",
    "avature": r"avature\.net",
    "smartrecruiters": r"smartrecruiters\.com",
    "phenom": r"phenompeople",
}
BOARD_LINK_PATTERNS = {
    "greenhouse": r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)",
    "lever": r"jobs\.lever\.co/([A-Za-z0-9_-]+)",
    "ashby": r"jobs\.ashbyhq\.com/([A-Za-z0-9_.-]+)",
}
_IGNORED_SLUGS = {"embed", "js", "api", "v1", "jobs", "job_board"}


@dataclass
class Posting:
    company: str
    provider: str
    id: str
    title: str
    team: str
    locations: list[str]
    url: str
    description: str
    # Groups re-posts of one requisition (e.g. one Greenhouse job posted per city); falls back to title+team.
    job_key: str = ""


@dataclass
class Board:
    provider: str
    slug: str
    postings: list[Posting] = field(default_factory=list)


def html_to_text(raw: str) -> str:
    if not raw:
        return ""
    soup = BeautifulSoup(html.unescape(raw), "html.parser")
    return soup.get_text("\n", strip=True)


def candidate_slugs(company: Company) -> list[str]:
    base = normalize_name(company.name)
    full = re.sub(r"[^a-z0-9 ]", "", company.name.lower().replace("&", "and"))
    cands = [base.replace(" ", ""), base.replace(" ", "-"), full.replace(" ", ""), company.domain_stem,
             base.split(" ")[0] if base else ""]
    return [c for c in dict.fromkeys(cands) if c]


def careers_page_hints(company: Company) -> tuple[list[str], dict[str, list[str]]]:
    """Scan public careers pages for ATS fingerprints and job-board links. Returns (ats_detected, {provider: slugs})."""
    d = company.website.lower().removeprefix("www.")
    urls = [f"https://www.{d}/careers", f"https://careers.{d}", f"https://jobs.{d}"]
    ats, slugs = set(), {}
    for url in urls:
        status, body = http.get(url, as_json=False, timeout=15, retries=False, quiet=True,
                                headers={"User-Agent": "Mozilla/5.0 (compatible; nyc-prospecting-agent/0.1)"})
        if status != 200 or not body:
            continue
        for name, pat in ATS_FINGERPRINTS.items():
            if re.search(pat, body, re.IGNORECASE):
                ats.add(name)
        for provider, pat in BOARD_LINK_PATTERNS.items():
            for s in re.findall(pat, body):
                if s.lower() not in _IGNORED_SLUGS:
                    slugs.setdefault(provider, [])
                    if s not in slugs[provider]:
                        slugs[provider].append(s)
    return sorted(ats), slugs


def _parse(provider: str, company: Company, data) -> list[Posting]:
    out = []
    if provider == "greenhouse":
        for j in data.get("jobs", []):
            locs = [j.get("location", {}).get("name", "")] + [o.get("name", "") for o in j.get("offices", [])]
            team = ", ".join(d["name"] for d in j.get("departments", []) if d.get("name"))
            out.append(Posting(company.name, provider, str(j["id"]), j.get("title", ""), team,
                               [l for l in locs if l], j.get("absolute_url", ""), html_to_text(j.get("content", "")),
                               job_key=str(j.get("internal_job_id") or "")))
    elif provider == "lever":
        for j in data:
            cat = j.get("categories", {}) or {}
            locs = [cat.get("location", "")] + list(cat.get("allLocations", []) or [])
            team = " / ".join(x for x in (cat.get("department"), cat.get("team")) if x)
            desc = "\n".join(filter(None, [j.get("descriptionPlain", "")] +
                                    [f"{l.get('text', '')}\n{html_to_text(l.get('content', ''))}" for l in j.get("lists", [])] +
                                    [j.get("additionalPlain", "")]))
            out.append(Posting(company.name, provider, j["id"], j.get("text", ""), team,
                               [l for l in locs if l], j.get("hostedUrl", ""), desc))
    elif provider == "ashby":
        for j in data.get("jobs", []):
            if j.get("isListed") is False:
                continue
            locs = [j.get("location", "")] + [s.get("location", "") for s in j.get("secondaryLocations", []) or []]
            team = " / ".join(x for x in dict.fromkeys((j.get("department"), j.get("team"))) if x)
            out.append(Posting(company.name, provider, j["id"], j.get("title", ""), team,
                               [l for l in locs if l], j.get("jobUrl", ""),
                               j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml", ""))))
    return out


def fetch_board(provider: str, slug: str, company: Company) -> Board | None:
    status, data = http.get(BOARD_URLS[provider].format(slug=slug))
    if status != 200 or data is None:
        return None
    return Board(provider, slug, _parse(provider, company, data))


def _belongs_to(company: Company, provider: str, slug: str, board: Board) -> bool:
    """Guard against slug collisions (e.g. greenhouse 'fox' is a vet clinic, ashby 'jane' is a health app)."""
    target = normalize_name(company.name)
    if provider == "greenhouse":
        _, meta = http.get(GREENHOUSE_META_URL.format(slug=slug))
        if meta and normalize_name(meta.get("name", "")) == target:
            return True
    needles = [company.name.lower(), company.website.lower()]
    if len(target) > 3:
        needles.append(target)
    for p in board.postings:
        hay = f"{p.description} {p.url}".lower()
        if any(n in hay for n in needles):
            return True
    return False


def discover_board(company: Company, override: dict | None = None) -> tuple[Board | None, dict]:
    """Find the company's public board. Returns (board or None, discovery info for logging)."""
    info = {"ats_detected": "", "checked": ""}
    if override:
        provider, slug = override["provider"].strip().lower(), override["slug"].strip()
        if provider in ("", "none"):
            info["checked"] = "override: none"
            return None, info
        board = fetch_board(provider, slug, company)
        info["checked"] = f"override {provider}:{slug}"
        if board is None:
            log.warning("%s: override %s:%s returned no board", company.name, provider, slug)
        return board, info

    ats, linked = careers_page_hints(company)
    info["ats_detected"] = ";".join(ats)
    tried, found = [], []
    for provider in PROVIDERS:
        slugs = list(dict.fromkeys(linked.get(provider, []) + candidate_slugs(company)))
        for slug in slugs:
            tried.append(f"{provider}:{slug}")
            board = fetch_board(provider, slug, company)
            if board is None:
                continue
            if board.postings and _belongs_to(company, provider, slug, board):
                found.append(board)
            else:
                log.info("%s: rejected %s:%s (no evidence it belongs to the company)", company.name, provider, slug)
    info["checked"] = ";".join(tried)
    if not found:
        return None, info
    return max(found, key=lambda b: len(b.postings)), info
