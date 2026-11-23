import pytest

from prospecting.keywords import categories_for, evidence, match_keywords


@pytest.mark.parametrize("text,expected", [
    ("Maintain our COBOL batch jobs on the mainframe", ["COBOL", "mainframe"]),
    ("Experience with Java 8 or JDK 1.8", ["Java 8"]),
    ("Port services from .NET Framework 4.8 to .NET 8", [".NET Framework"]),
    ("Build models in SAS and Python", ["SAS"]),
    ("Frontend in AngularJS", ["Angular"]),
    ("Lead the modernization of our legacy trading systems", ["legacy", "modernization"]),
    ("Drive cloud migration and re-platforming of batch workloads", ["migration", "re-platforming"]),
    ("Pay down technical debt and raise unit test coverage", ["tech debt", "test coverage"]),
    ("Own vulnerability remediation and track CVEs", ["security remediation", "CVE"]),
    ("Remediate critical vulnerabilities across services", ["security remediation"]),
])
def test_matches(text, expected):
    assert match_keywords(text) == expected


@pytest.mark.parametrize("text", [
    "We are a SaaS company with a legacy of excellence",   # SaaS != SAS; "legacy of" is not technical
    "Help customers with immigration paperwork",            # "immigration" must not match "migration"
    "sas lowercase is not the analytics language",
    "",
])
def test_no_false_positives(text):
    assert match_keywords(text) == []


def test_legacy_requires_technical_noun():
    assert match_keywords("migrate legacy Java code") == ["legacy", "migration"]
    assert "legacy" not in match_keywords("continue our legacy as a leader")


def test_categories():
    assert categories_for(["COBOL", "migration", "CVE"]) == ["legacy_stack", "modernization", "security_remediation"]


def test_evidence_snippet():
    snippet = evidence("x " * 200 + "we have tech debt to fix" + " y" * 200, ["tech debt"])
    assert "tech debt" in snippet and snippet.startswith("...")
