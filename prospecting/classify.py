"""Heuristics for posting classification: engineering or not, NYC or not, likely hiring manager."""
import re

_ENG_TITLE = re.compile(
    r"\b(?:engineer(?:ing)?s?|developers?|programmers?|swe|sre|site reliability|devops|devsecops|architect|"
    r"software|full[\s-]?stack|front[\s-]?end|back[\s-]?end|mobile|ios|android|infrastructure|platform|"
    r"data engineer|machine learning|ml|qa|quality assurance|test automation|sdet|tech lead|technical lead|cto)\b",
    re.IGNORECASE)
# Customer-facing or non-software "engineer" titles.
_NON_ENG_TITLE = re.compile(
    r"\b(?:sales|solutions?|pre[\s-]?sales|customer[\s-]+(?:engineer|success|support|facing)|support|field|account|partner|recruit(?:er|ing)|sourcer|"
    r"marketing|product marketing|designer|counsel|legal|finance|accountant|mechanical|electrical|civil|"
    r"hardware|manufacturing|facilities|audio|video|broadcast|technical writer|success|advoca(?:te|cy)|"
    r"developer relations|community|engagement|enablement|compensation|program manager|forward[\s-]deploy(?:ed|ment)|"
    r"services architect|escalations?|technical services|consult(?:ing|ant)|implementation|professional services|"
    r"intern(?:ship)?)\b",
    re.IGNORECASE)
# Teams whose "engineers" are customer-facing (pre/post-sales, support, professional services).
_NON_ENG_TEAM = re.compile(
    r"\b(?:sales|post[\s-]?sales|pre[\s-]?sales|technical support|customer success|professional services|ps|"
    r"(?:field|apac|emea|amer|latam|customer) delivery|engagement manager|consulting)\b",
    re.IGNORECASE)
_PRODUCT_TITLE = re.compile(r"\bproduct (?:manager|owner|lead|director)\b", re.IGNORECASE)


def is_engineering(title: str, team: str = "") -> bool:
    if not title or _NON_ENG_TITLE.search(title) or _PRODUCT_TITLE.search(title):
        return False
    if team and _NON_ENG_TEAM.search(team):
        return False
    return bool(_ENG_TITLE.search(title))


_NYC = re.compile(r"\bnew york(?!\s+state)\b|\bnyc\b|\bmanhattan\b|\bbrooklyn\b|\bqueens\b|\bbronx\b|\bstaten island\b",
                  re.IGNORECASE)


def is_nyc(*locations: str) -> bool:
    return any(loc and _NYC.search(loc) for loc in locations)


# (regex on title+team, functional area used in the manager title)
_AREAS = [
    (r"mainframe|cobol|core banking|core systems", "Core Systems Engineering"),
    (r"security|appsec|devsecops|vulnerab", "Security Engineering"),
    (r"platform|infrastructure|infra\b|sre|site reliability|devops|cloud|developer productivity|dev ?ex|reliability",
     "Platform Engineering"),
    (r"\bdata\b|analytics|machine learning|\bml\b|\bai\b|data science", "Data & ML Engineering"),
    (r"mobile|ios|android", "Mobile Engineering"),
    (r"front[\s-]?end|web|ui\b", "Frontend Engineering"),
    (r"\bqa\b|quality|test|sdet", "Quality Engineering"),
    (r"payments?", "Payments Engineering"),
]
_EXEC = re.compile(r"\b(?:vp|vice president|head of|director|chief|cto|svp|evp)\b", re.IGNORECASE)
_MGR = re.compile(r"\b(?:manager|staff|principal|distinguished|lead)\b", re.IGNORECASE)


def likely_hiring_manager(title: str, team: str = "") -> str:
    """Infer the probable hiring manager's *title* (never a person) from the posting title and team."""
    text = f"{title} {team}"
    area = next((a for p, a in _AREAS if re.search(p, text, re.IGNORECASE)), "Software Engineering")
    if _EXEC.search(title):
        return "CTO / SVP Engineering"
    if _MGR.search(title):
        return f"VP {area}"
    return f"Director of {area}"
