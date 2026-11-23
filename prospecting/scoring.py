"""Phase 3 logic: the 0-100 "why now" score, inferred personas and the outreach angle. Pure functions."""
import math
import re
from collections import Counter

# Points per component (sum = 100). See README "Scoring".
WEIGHTS = {"project_work": 45, "hiring": 20, "nyc": 15, "tool_stack": 20}
PROJECT_ROLES_CAP = 10    # unique flagged roles at which project_work maxes out
HIRING_CAP = 100          # engineering postings at which hiring maxes out
NYC_HQ_POINTS = {"nyc": 7.5, "ny_metro": 5.0}
NYC_ROLES_CAP = 5         # NYC engineering postings at which the NYC-hiring half maxes out
TOOL_STACK_POINTS = {"Uses Cursor": 20, "Uses Claude Code": 20, "Uses Copilot": 20, "Mixed": 20,
                     "AGENTS.md only": 15, "No public signal": 10}

KEYBOARD_LABELS = {"Uses Cursor", "Uses Claude Code", "Uses Copilot", "Mixed"}
CATEGORY_WORK = {"modernization": "migration and modernization", "legacy_stack": "legacy-stack upgrade",
                 "security_remediation": "security-remediation", "test_coverage": "test-coverage"}
ENTERPRISE_SECTORS = {"banking", "payments", "asset management", "financial data", "market infrastructure",
                      "fintech infrastructure", "insurance", "telecom", "pharma", "retail"}


def log_scaled(n: float, cap: float, points: float) -> float:
    """0 at n=0, `points` at n>=cap, log-shaped in between, so the first few signals count most."""
    if n <= 0:
        return 0.0
    return points * min(1.0, math.log1p(n) / math.log1p(cap))


def hq_area(why_on_list: str) -> str:
    """'NYC HQ; ...' / 'Brooklyn HQ' -> 'nyc'; 'Purchase NY HQ' -> 'ny_metro'; else ''."""
    m = re.search(r"([\w .'-]+?)\s+HQ\b", why_on_list or "", re.I)
    if not m:
        return ""
    place = m.group(1).strip().lower()
    if place in {"nyc", "new york", "new york city", "manhattan", "brooklyn", "queens", "bronx", "staten island"}:
        return "nyc"
    return "ny_metro" if re.search(r"\b(?:ny|new york|nj|new jersey|ct)\b", place) else ""


def score(*, flagged_unique_roles: int, engineering_postings: int, nyc_engineering_postings: int, hq: str,
          tool_stack_label: str) -> dict:
    parts = {
        "project_work": log_scaled(flagged_unique_roles, PROJECT_ROLES_CAP, WEIGHTS["project_work"]),
        "hiring": log_scaled(engineering_postings, HIRING_CAP, WEIGHTS["hiring"]),
        "nyc": NYC_HQ_POINTS.get(hq, 0.0)
               + (WEIGHTS["nyc"] - max(NYC_HQ_POINTS.values())) * min(1.0, nyc_engineering_postings / NYC_ROLES_CAP),
        "tool_stack": TOOL_STACK_POINTS.get(tool_stack_label, TOOL_STACK_POINTS["No public signal"]),
    }
    parts = {k: round(v, 1) for k, v in parts.items()}
    return {**parts, "total": round(sum(parts.values()))}


def executive_persona(sector: str, engineering_postings: int, has_board: bool) -> str:
    if sector.strip().lower() in ENTERPRISE_SECTORS:
        return "CIO"
    if has_board and engineering_postings < 10:
        return "Head of Engineering"
    return "CTO"


def owner_persona(hiring_manager_titles: list[str], sector: str) -> tuple[str, str]:
    """Most common inferred hiring-manager title among flagged postings (VP wins ties). Returns (title, basis)."""
    titles = [t for t in hiring_manager_titles if t]
    if titles:
        counts = Counter(titles)
        best = max(counts, key=lambda t: (counts[t], t.startswith("VP"), t))
        return best, f"most common across {len(titles)} flagged posting{'s' * (len(titles) != 1)}"
    if sector.strip().lower() in ENTERPRISE_SECTORS:
        return "Head of Application Modernization", "sector default (no public postings)"
    return "VP Engineering", "sector default (no flagged postings)"


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def work_phrase(categories: Counter) -> str:
    top = [c for c, _ in categories.most_common(2) if c in CATEGORY_WORK]
    return _join([CATEGORY_WORK[c] for c in top]) if top else "modernization"


def _signal_clause(roles: int, keywords: list[str], example_title: str, why_on_list: str) -> str:
    if roles:
        kw = _join([f"“{k}”" for k in keywords[:3]]) if keywords else "project work"
        eg = f" (e.g. “{example_title}”)" if example_title else ""
        return f"{roles} open engineering role{'s' * (roles != 1)} mention {kw}{eg}"
    cue = re.sub(r"^[^;]*\bHQ\b;?\s*", "", why_on_list or "").strip().rstrip(".")
    return f"With {cue[0].lower() + cue[1:]}" if cue else "With a large NYC engineering org"


def outreach_angle(*, roles: int, keywords: list[str], categories: Counter, example_title: str,
                   tool_stack_label: str, why_on_list: str) -> str:
    """One sentence. Keyboard AI tools are complementary to Devin, never a displacement pitch."""
    signal = _signal_clause(roles, keywords, example_title, why_on_list)
    work = work_phrase(categories)
    sep = "; " if roles else ", "
    if tool_stack_label in KEYBOARD_LABELS:
        tools = {"Uses Cursor": "Cursor", "Uses Claude Code": "Claude Code", "Uses Copilot": "Copilot",
                 "Mixed": "several keyboard AI tools"}[tool_stack_label]
        tail = (f"you already have AI for individual engineers ({tools} in your public repos); "
                f"Devin finishes whole projects, so hand it the {work} backlog and run those projects in parallel.")
    elif tool_stack_label == "AGENTS.md only":
        tail = (f"your public repos already carry AGENTS.md files for coding agents, "
                f"so Devin can pick up whole {work} projects end to end from those same instructions.")
    else:
        tail = (f"there's no public AI coding-tool footprint yet, so Devin can be the team's first agent, "
                f"taking whole {work} projects off engineers' plates end to end.")
    return f"{signal}{sep}{tail}"
