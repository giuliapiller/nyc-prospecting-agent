"""Keyword rules for flagging engineering postings that describe legacy / project-shaped work.

Each rule has a display name, a category (used for scoring in Phase 3) and a regex.
Patterns are case-insensitive unless the rule sets ``case_sensitive``.
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class KeywordRule:
    name: str
    category: str
    pattern: str
    case_sensitive: bool = False

    @property
    def regex(self) -> re.Pattern:
        return re.compile(self.pattern, 0 if self.case_sensitive else re.IGNORECASE)


_LEGACY_NOUNS = (r"(?:systems?|code(?:base)?s?|applications?|apps?|platforms?|stacks?|technolog(?:y|ies)|"
                 r"infrastructure|services?|software|environments?|tools?|tooling|databases?|data|monoliths?|"
                 r"architectures?|estates?|products?|components?|frameworks?)")

KEYWORD_RULES: list[KeywordRule] = [
    # Legacy stacks
    KeywordRule("COBOL", "legacy_stack", r"\bCOBOL\b"),
    KeywordRule("mainframe", "legacy_stack", r"\bmainframes?\b|\bz/OS\b"),
    KeywordRule("Java 8", "legacy_stack", r"\bJava\s?(?:SE\s?)?8\b|\bJDK\s?(?:1\.)?8\b|\bJava\s?1\.8\b"),
    KeywordRule(".NET Framework", "legacy_stack", r"\.NET\s+Framework\b"),
    # SAS (the analytics language) is always upper-case; avoids matching "sas" fragments or "SaaS".
    KeywordRule("SAS", "legacy_stack", r"\bSAS\b(?!\s*(?:token|URL|signature))", case_sensitive=True),
    KeywordRule("Angular", "legacy_stack", r"\bAngular(?:JS|\.js)?\b"),
    # Modernization / migration
    # "legacy" only counts in a technical context ("legacy systems", "legacy Java code"), not "a legacy of excellence".
    KeywordRule("legacy", "modernization", rf"\blegacy\b(?:[\s-]+[\w.+#/-]+){{0,2}}?[\s-]+{_LEGACY_NOUNS}\b"),
    KeywordRule("modernization", "modernization", r"\bmoderni[sz](?:ation|ations|e|es|ed|ing)\b"),
    KeywordRule("migration", "modernization", r"\bmigrat(?:e|es|ed|ing|ion|ions)\b"),
    KeywordRule("re-platforming", "modernization", r"\bre-?platform(?:ing|ed|s)?\b"),
    KeywordRule("tech debt", "modernization", r"\btech(?:nical)?[\s-]+debt\b"),
    # Test coverage
    KeywordRule("test coverage", "test_coverage", r"\b(?:test|code|unit[\s-]test)[\s-]+coverage\b"),
    # Security remediation
    KeywordRule("security remediation", "security_remediation",
                r"\b(?:security|vulnerabilit(?:y|ies)|CVEs?)(?:\s+\w+){0,2}\s+remediat(?:e|es|ed|ing|ion)\b"
                r"|\bremediat(?:e|es|ed|ing|ion)(?:\s+of)?(?:\s+\w+){0,2}\s+(?:vulnerabilit(?:y|ies)|CVEs?|security\s+(?:findings|issues))\b"),
    KeywordRule("CVE", "security_remediation", r"\bCVEs?\b", case_sensitive=True),
]


def match_keywords(text: str, rules: list[KeywordRule] = KEYWORD_RULES) -> list[str]:
    """Return the names of all rules that match ``text``, in rule order."""
    if not text:
        return []
    return [r.name for r in rules if r.regex.search(text)]


def categories_for(matched: list[str], rules: list[KeywordRule] = KEYWORD_RULES) -> list[str]:
    by_name = {r.name: r.category for r in rules}
    return sorted({by_name[m] for m in matched if m in by_name})


def evidence(text: str, matched: list[str], rules: list[KeywordRule] = KEYWORD_RULES, width: int = 90) -> str:
    """Short snippet around the first match of the first matched rule, for human review."""
    by_name = {r.name: r for r in rules}
    for name in matched:
        m = by_name[name].regex.search(text)
        if m:
            start, end = max(0, m.start() - width), min(len(text), m.end() + width)
            snippet = " ".join(text[start:end].split())
            return ("..." if start else "") + snippet + ("..." if end < len(text) else "")
    return ""
