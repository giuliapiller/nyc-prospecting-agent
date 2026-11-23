"""Phase 1: job-posting signals."""
import csv
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .boards import Posting, discover_board
from .classify import is_engineering, is_nyc, likely_hiring_manager
from .companies import Company, load_companies
from .customers import fetch_case_studies, match_customer
from .keywords import categories_for, evidence, match_keywords

log = logging.getLogger(__name__)

POSTING_FIELDS = ["company", "provider", "job_title", "team", "location", "nyc", "matched_keywords",
                  "keyword_categories", "evidence", "link", "likely_hiring_manager_title_inferred"]
COMPANY_FIELDS = ["company", "website", "sector", "board_status", "board_provider", "board_slug", "ats_detected",
                  "total_postings", "engineering_postings", "nyc_engineering_postings", "flagged_postings",
                  "flagged_nyc_postings", "flagged_unique_roles", "flagged_by_category", "existing_customer_public"]


def strip_boilerplate(postings: list[Posting], min_share: float = 0.25, min_count: int = 3) -> dict[str, str]:
    """Drop text blocks repeated across many of a company's postings (About us, EEO, benefits).

    Otherwise a phrase in company boilerplate (e.g. a product called "Relational Migrator") would flag every posting.
    Returns {posting id: description without boilerplate}.
    """
    blocks = {p.id: [b.strip() for b in p.description.split("\n") if b.strip()] for p in postings}
    counts = Counter(b for bs in blocks.values() for b in set(bs))
    threshold = max(min_count, min_share * len(postings))
    return {pid: "\n".join(b for b in bs if counts[b] < threshold or len(b) < 40) for pid, bs in blocks.items()}


def analyze_postings(postings: list[Posting]) -> tuple[list[dict], dict]:
    eng = [p for p in postings if is_engineering(p.title, p.team)]
    cleaned = strip_boilerplate(postings) if postings else {}
    rows, stats, roles = [], Counter(), set()
    stats["total_postings"] = len(postings)
    stats["engineering_postings"] = len(eng)
    for p in eng:
        nyc = is_nyc(*p.locations)
        stats["nyc_engineering_postings"] += nyc
        text = f"{p.title}\n{cleaned.get(p.id, p.description)}"
        matched = match_keywords(text)
        if not matched:
            continue
        cats = categories_for(matched)
        stats["flagged_postings"] += 1
        roles.add(p.job_key or (p.title.strip().lower(), p.team.strip().lower()))
        stats["flagged_nyc_postings"] += nyc
        for c in cats:
            stats[f"cat:{c}"] += 1
        rows.append({
            "company": p.company, "provider": p.provider, "job_title": p.title, "team": p.team,
            "location": "; ".join(dict.fromkeys(p.locations)), "nyc": "yes" if nyc else "no",
            "matched_keywords": "; ".join(matched), "keyword_categories": "; ".join(cats),
            "evidence": evidence(text, matched), "link": p.url,
            "likely_hiring_manager_title_inferred": likely_hiring_manager(p.title, p.team),
        })
    # One requisition re-posted per city counts once for "unique roles".
    stats["flagged_unique_roles"] = len(roles)
    return rows, stats


def _load_overrides(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["company"].strip(): r for r in csv.DictReader(f) if r.get("company", "").strip()}


def _process(company: Company, overrides: dict, case_studies: dict) -> tuple[dict, list[dict]]:
    board, info = discover_board(company, overrides.get(company.name))
    row = {"company": company.name, "website": company.website, "sector": company.sector,
           "ats_detected": info["ats_detected"], "existing_customer_public": match_customer(company, case_studies)}
    if board is None:
        log.warning("%s: no public Greenhouse/Lever/Ashby board found (ATS detected: %s); skipping postings",
                    company.name, info["ats_detected"] or "unknown")
        row.update({"board_status": "not_found", "board_provider": "", "board_slug": ""})
        return row, []
    postings, stats = analyze_postings(board.postings)
    log.info("%s: %s:%s, %d postings, %d engineering, %d flagged", company.name, board.provider, board.slug,
             stats["total_postings"], stats["engineering_postings"], stats["flagged_postings"])
    cats = sorted((k[4:], v) for k, v in stats.items() if k.startswith("cat:"))
    row.update({"board_status": "found", "board_provider": board.provider, "board_slug": board.slug,
                "flagged_by_category": "; ".join(f"{k}={v}" for k, v in cats),
                **{k: stats[k] for k in ("total_postings", "engineering_postings", "nyc_engineering_postings",
                                         "flagged_postings", "flagged_nyc_postings", "flagged_unique_roles")}})
    return row, postings


def csv_safe(value):
    """Neutralize spreadsheet formulas in untrusted text (job titles come from third-party boards)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _write(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows({k: csv_safe(v) for k, v in r.items()} for r in rows)


def run(companies_csv: Path, out_dir: Path, overrides_csv: Path, workers: int = 6) -> list[dict]:
    companies = load_companies(companies_csv)
    overrides = _load_overrides(overrides_csv)
    case_studies = fetch_case_studies()
    log.info("Loaded %d companies, %d board overrides, %d public case-study names",
             len(companies), len(overrides), len(case_studies))
    with ThreadPoolExecutor(workers) as ex:
        results = list(ex.map(lambda c: _process(c, overrides, case_studies), companies))
    company_rows = [r for r, _ in results]
    posting_rows = [p for _, ps in results for p in ps]
    _write(out_dir / "phase1_companies.csv", COMPANY_FIELDS, company_rows)
    _write(out_dir / "phase1_postings.csv", POSTING_FIELDS, posting_rows)
    _write(out_dir / "no_public_board.csv", ["company", "website", "ats_detected"],
           [r for r in company_rows if r["board_status"] == "not_found"])
    log.info("Phase 1 done: %d/%d companies with a public board, %d flagged postings",
             sum(r["board_status"] == "found" for r in company_rows), len(company_rows), len(posting_rows))
    return company_rows
