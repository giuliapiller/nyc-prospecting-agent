"""Phase 3: join Phase 1 + Phase 2 outputs, score, write the ranked CSV and the top-10 dashboard."""
import csv
import html
import logging
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from .companies import load_companies
from .phase1 import csv_safe
from .scoring import WEIGHTS, executive_persona, hq_area, outreach_angle, owner_persona, score

log = logging.getLogger(__name__)

RANKED_FIELDS = [
    "rank", "company", "sector", "why_now_score", "score_project_work", "score_hiring", "score_nyc",
    "score_tool_stack", "data_quality", "limited_data_reason", "why_now_signal", "board_provider", "ats_detected",
    "engineering_postings", "nyc_engineering_postings", "flagged_unique_roles", "flagged_postings",
    "top_keywords", "flagged_by_category", "tool_stack_label", "ai_files_found", "github_orgs",
    "evidence_link", "persona_executive_inferred", "persona_owner_inferred", "persona_owner_basis",
    "outreach_angle", "existing_customer_public",
]
TOOL_COUNT_COLS = {"cursor": "cursor_repos", "copilot": "copilot_repos", "claude_code": "claude_code_repos"}


def _read(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return [{k: (v[1:] if isinstance(v, str) and v.startswith("'") else v) for k, v in r.items()}
                for r in csv.DictReader(f)]


def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _keywords(posting: dict) -> set[str]:
    return {k.strip() for k in posting["matched_keywords"].split(";") if k.strip()}


def _best_posting(postings: list[dict], top_keywords: list[str]) -> dict | None:
    """Posting covering most of the company's top keywords, then NYC, then most keywords overall."""
    return max(postings, key=lambda p: (len(_keywords(p) & set(top_keywords)), p["nyc"] == "yes",
                                        len(_keywords(p))), default=None)


def build_rows(companies, p1_companies: list[dict], p1_postings: list[dict], p2: list[dict]) -> list[dict]:
    p1 = {r["company"]: r for r in p1_companies}
    gh = {r["company"]: r for r in p2}
    posts = defaultdict(list)
    for r in p1_postings:
        posts[r["company"]].append(r)
    rows = []
    for c in companies:
        j, g, ps = p1.get(c.name, {}), gh.get(c.name, {}), posts[c.name]
        has_board = j.get("board_status") == "found"
        has_org = bool(g.get("github_orgs"))
        roles, eng, nyc_eng = (_int(j.get(k)) for k in
                               ("flagged_unique_roles", "engineering_postings", "nyc_engineering_postings"))
        label = g.get("tool_stack_label") or "No public signal"
        s = score(flagged_unique_roles=roles, engineering_postings=eng, nyc_engineering_postings=nyc_eng,
                  hq=hq_area(c.why_on_list), tool_stack_label=label)

        kw = Counter(k.strip() for p in ps for k in p["matched_keywords"].split(";") if k.strip())
        cats = Counter(k.strip() for p in ps for k in p["keyword_categories"].split(";") if k.strip())
        tools = [t for t, col in TOOL_COUNT_COLS.items() if _int(g.get(col))]
        top_kw = [k for k, _ in kw.most_common(3)]
        best = _best_posting(ps, top_kw)
        repos = [r.strip() for r in (g.get("example_repos") or "").split(";") if r.strip()]
        evidence = best["link"] if best else (f"https://github.com/{repos[0]}" if repos else "")
        owner, basis = owner_persona([p["likely_hiring_manager_title_inferred"] for p in ps], c.sector)

        reasons = ([] if has_board else [f"no public job board (ATS: {j.get('ats_detected') or 'unknown'})"]) + \
                  ([] if has_org else ["no GitHub org found"])
        if g.get("scan_complete") == "no":
            reasons.append("GitHub scan incomplete")
        signal = []
        if roles:
            signal.append(f"{roles} project-shaped role{'s' * (roles != 1)} ({', '.join(k for k, _ in kw.most_common(3))})")
        if has_board:
            signal.append(f"{eng} eng postings, {nyc_eng} in NYC")
        signal.append(label + (f": {g['ai_files_found']}" if g.get("ai_files_found") else ""))

        rows.append({
            "company": c.name, "sector": c.sector, "why_now_score": s["total"],
            "score_project_work": s["project_work"], "score_hiring": s["hiring"], "score_nyc": s["nyc"],
            "score_tool_stack": s["tool_stack"],
            "data_quality": "limited data" if reasons and not (has_board and has_org) else "ok",
            "limited_data_reason": "; ".join(reasons), "why_now_signal": "; ".join(signal),
            "board_provider": j.get("board_provider", ""), "ats_detected": j.get("ats_detected", ""),
            "engineering_postings": eng, "nyc_engineering_postings": nyc_eng, "flagged_unique_roles": roles,
            "flagged_postings": _int(j.get("flagged_postings")),
            "top_keywords": "; ".join(k for k, _ in kw.most_common(5)),
            "flagged_by_category": j.get("flagged_by_category", ""), "tool_stack_label": label,
            "ai_files_found": g.get("ai_files_found", ""), "github_orgs": g.get("github_orgs", ""),
            "evidence_link": evidence,
            "persona_executive_inferred": executive_persona(c.sector, eng),
            "persona_owner_inferred": owner, "persona_owner_basis": basis,
            "outreach_angle": outreach_angle(
                company=c.name, roles=roles, keywords=top_kw, categories=cats,
                example_title=best["job_title"] if best else "",
                example_keywords=[k for k in top_kw if best and k in _keywords(best)],
                tool_stack_label=label, tools=tools,
                why_on_list=c.why_on_list),
            "existing_customer_public": j.get("existing_customer_public", "no"),
        })
    rows.sort(key=lambda r: (-r["why_now_score"], -r["flagged_unique_roles"], -r["engineering_postings"],
                             r["company"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def render_dashboard(rows: list[dict], top_n: int = 10) -> str:
    e = html.escape
    cards = []
    for r in rows[:top_n]:
        link = (f'<a href="{e(r["evidence_link"])}" target="_blank" rel="noopener">evidence</a>'
                if r["evidence_link"] else "no public evidence link")
        badge = (f'<span class="badge">{"limited data: " if r["data_quality"] == "limited data" else ""}'
                 f'{e(r["limited_data_reason"])}</span>') if r["limited_data_reason"] else ""
        bars = "".join(
            f'<span title="{k} {r["score_" + k]}/{w}" style="width:{100 * r["score_" + k] / 100:.1f}%" class="b-{k}"></span>'
            for k, w in WEIGHTS.items())
        cards.append(f"""
<tr>
  <td class="rank">{r["rank"]}</td>
  <td><strong>{e(r["company"])}</strong><br><span class="muted">{e(r["sector"])}</span>{badge}</td>
  <td class="score">{r["why_now_score"]}<div class="bar">{bars}</div></td>
  <td>{e(r["why_now_signal"])}<br>{link}</td>
  <td>{e(r["persona_executive_inferred"])}<br><span class="muted">owner:</span> {e(r["persona_owner_inferred"])}</td>
  <td>{e(r["outreach_angle"])}</td>
</tr>""")
    legend = " · ".join(f'<span class="sw b-{k}"></span>{k.replace("_", " ")} ({w})' for k, w in WEIGHTS.items())
    limited = sum(r["data_quality"] == "limited data" for r in rows)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>NYC prospecting: top {top_n} why-now</title>
<style>
body{{font:14px/1.45 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;margin:24px;color:#1b1f24;background:#fafbfc}}
h1{{font-size:20px;margin:0 0 4px}} .muted{{color:#6a737d;font-size:12px}}
table{{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 2px #0001}}
th,td{{padding:10px;border-bottom:1px solid #e1e4e8;vertical-align:top;text-align:left}}
th{{background:#f3f4f6;font-size:12px;text-transform:uppercase;letter-spacing:.03em}}
.rank{{font-weight:600;color:#6a737d}} .score{{font-size:22px;font-weight:700;width:110px}}
.bar{{display:flex;height:6px;background:#eee;border-radius:3px;overflow:hidden;margin-top:4px}}
.b-project_work{{background:#2f6fde}} .b-hiring{{background:#28a745}} .b-nyc{{background:#f0ad4e}} .b-tool_stack{{background:#8e44ad}}
.sw{{display:inline-block;width:10px;height:10px;margin-right:4px;border-radius:2px}}
.badge{{display:block;margin-top:4px;font-size:11px;color:#9a6700;background:#fff8c5;padding:2px 6px;border-radius:4px}}
a{{color:#0366d6}}
</style></head><body>
<h1>NYC prospecting: top {top_n} by why-now score</h1>
<p class="muted">Generated {date.today().isoformat()} from public job boards and public GitHub repos. {len(rows)} companies scored,
{limited} with limited data. Personas are inferred titles, not people. Score weights: {legend}</p>
<table><thead><tr><th>#</th><th>Company</th><th>Score</th><th>Why now (evidence)</th><th>Personas (inferred)</th><th>Outreach angle</th></tr></thead>
<tbody>{"".join(cards)}
</tbody></table></body></html>
"""


def run(companies_csv: Path, out_dir: Path) -> list[dict]:
    rows = build_rows(load_companies(companies_csv), _read(out_dir / "phase1_companies.csv"),
                      _read(out_dir / "phase1_postings.csv"), _read(out_dir / "phase2_github.csv"))
    with open(out_dir / "phase3_ranked.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RANKED_FIELDS)
        w.writeheader()
        w.writerows({k: csv_safe(r[k]) for k in RANKED_FIELDS} for r in rows)
    (out_dir / "dashboard.html").write_text(render_dashboard(rows), encoding="utf-8")
    log.info("Phase 3 done: %d companies ranked, %d limited data", len(rows),
             sum(r["data_quality"] == "limited data" for r in rows))
    for has_board, label in ((False, "Workday, no public board"), (True, "public board found, careers site also on Workday")):
        names = [r["company"] for r in rows if "workday" in r["ats_detected"] and bool(r["board_provider"]) == has_board]
        log.info("%s: %s", label, ", ".join(sorted(names)) or "none")
    return rows
