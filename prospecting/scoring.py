"""Phase 3 logic: the 0-100 "why now" score, inferred personas and the outreach angle. Pure functions."""
import math
import re
from collections import Counter

WEIGHTS = {"project_work": 45, "hiring": 20, "nyc": 15, "tool_stack": 20}
PROJECT_ROLES_CAP = 10   # unique flagged roles at which project work maxes out
HIRING_CAP = 100         # engineering postings at which hiring volume maxes out
NYC_HQ_POINTS = {"nyc": 7.5, "ny_metro": 5.0}
NYC_ROLES_CAP = 5        # NYC engineering postings at which the other half of NYC presence maxes out
TOOL_STACK_POINTS = {
    "Uses Cursor": 20, "Uses Claude Code": 20, "Uses Copilot": 20, "Mixed": 20,
    "AGENTS.md only": 15,
    "No public signal": 10,
}
KEYBOARD_LABELS = {"Uses Cursor", "Uses Claude Code", "Uses Copilot", "Mixed"}
TOOL_NAMES = {"cursor": "Cursor", "copilot": "Copilot", "claude_code": "Claude Code"}

CATEGORY_WORK = {
    "modernization": "modernization",
    "legacy_stack": "legacy-stack upgrade",
    "security_remediation": "security-remediation",
    "test_coverage": "test-coverage",
}
# Large, regulated enterprises where IT reports to a CIO; elsewhere engineering usually reports to a CTO.
CIO_SECTORS = {"banking", "payments", "asset management", "financial data", "market infrastructure",
               "fintech infrastructure", "insurance", "telecom", "pharma"}
SMALL_ENG_ORG = 10       # fewer open engineering postings than this -> "Head of Engineering"
NYC_PLACES = {"nyc", "new york", "new york city", "manhattan", "brooklyn", "queens", "bronx", "staten island"}


def log_scaled(n: float, cap: float, points: float) -> float:
    """0 at n=0, `points` at n>=cap, logarithmic in between so one huge company doesn't flatten the rest."""
    if n <= 0:
        return 0.0
    return points * min(1.0, math.log1p(n) / math.log1p(cap))


def hq_area(why_on_list: str) -> str:
    """'nyc', 'ny_metro' or '' from the "<place> HQ" cue in companies.csv."""
    m = re.search(r"([\w .'-]+?)\s+HQ\b", why_on_list or "", re.I)
    if not m:
        return ""
    place = m.group(1).strip().lower()
    if place in NYC_PLACES:
        return "nyc"
    return "ny_metro" if re.search(r"\b(?:ny|new york|nj|new jersey|ct)\b", place) else ""


def score(*, flagged_unique_roles: int, engineering_postings: int, nyc_engineering_postings: int,
          hq: str, tool_stack_label: str) -> dict:
    nyc_roles_points = WEIGHTS["nyc"] - NYC_HQ_POINTS["nyc"]
    parts = {
        "project_work": log_scaled(flagged_unique_roles, PROJECT_ROLES_CAP, WEIGHTS["project_work"]),
        "hiring": log_scaled(engineering_postings, HIRING_CAP, WEIGHTS["hiring"]),
        "nyc": NYC_HQ_POINTS.get(hq, 0.0) + nyc_roles_points * min(1.0, nyc_engineering_postings / NYC_ROLES_CAP),
        "tool_stack": TOOL_STACK_POINTS.get(tool_stack_label, TOOL_STACK_POINTS["No public signal"]),
    }
    parts = {k: round(v, 1) for k, v in parts.items()}
    return {**parts, "total": min(100, round(sum(parts.values())))}


def executive_persona(sector: str, engineering_postings: int) -> str:
    if sector.strip().lower() in CIO_SECTORS:
        return "CIO"
    if 0 < engineering_postings < SMALL_ENG_ORG:
        return "Head of Engineering"
    return "CTO"


def owner_persona(hiring_manager_titles: list[str], sector: str) -> tuple[str, str]:
    """Most common inferred hiring-manager title across flagged postings (VP wins ties). Returns (title, basis)."""
    titles = [t for t in hiring_manager_titles if t and not t.startswith("CTO")]
    if titles:
        counts = Counter(titles)
        best = max(counts, key=lambda t: (counts[t], t.startswith("VP"), t))
        return best, f"from {counts[best]} of {len(titles)} flagged posting{'s' * (len(titles) != 1)}"
    if sector.strip().lower() in CIO_SECTORS:
        return "Head of Application Modernization", "sector default (no flagged postings)"
    return "VP Engineering", "sector default (no flagged postings)"


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def work_phrase(categories: Counter) -> str:
    top = [c for c, _ in categories.most_common() if c in CATEGORY_WORK][:2]
    return _join([CATEGORY_WORK[c] for c in top]) if top else "modernization"


def profile_cue(why_on_list: str) -> str:
    """why_on_list without the HQ cue, e.g. 'large legacy payments stack'."""
    parts = [p.strip() for p in (why_on_list or "").split(";") if p.strip() and not re.search(r"\bHQ\b", p)]
    return ", ".join(parts)


def outreach_angle(*, company: str, roles: int, keywords: list[str], categories: Counter, example_title: str,
                   tool_stack_label: str, tools: list[str], why_on_list: str) -> str:
    """One sentence. Keyboard AI tools are positioned as complementary to Devin, never as something to replace."""
    work = work_phrase(categories)
    if roles:
        kw = _join([f"“{k}”" for k in keywords[:3]]) if keywords else "project work"
        eg = f" (e.g. “{example_title}”)" if example_title else ""
        lead = f"{roles} open engineering role{'s' * (roles != 1)} at {company} mention{'s' * (roles == 1)} {kw}{eg}; "
    else:
        cue = profile_cue(why_on_list)
        lead = f"For {company}{f' ({cue})' if cue else ''}, "
    if tool_stack_label in KEYBOARD_LABELS:
        names = _join([TOOL_NAMES[t] for t in tools if t in TOOL_NAMES]) or "keyboard AI tools"
        tail = (f"you already have AI for individual engineers ({names} configs in your public repos); "
                f"Devin finishes whole projects, so hand it the {work} backlog to run in parallel.")
    elif tool_stack_label == "AGENTS.md only":
        tail = (f"your public repos already carry AGENTS.md instructions for coding agents, so Devin can take whole "
                f"{work} projects end to end and run several in parallel.")
    else:
        tail = (f"whatever AI your engineers use day to day, Devin finishes whole projects, so hand it "
                f"{work} work end to end and run several projects in parallel.")
    return lead + tail
