from prospecting.boards import Posting
from prospecting.phase1 import analyze_postings, csv_safe


def posting(pid, title, job_key="", desc="Lead the migration of legacy systems."):
    return Posting("Acme", "greenhouse", pid, title, "Engineering", ["New York, NY"], "https://x", desc, job_key)


def test_unique_roles_group_by_job_key():
    ps = [posting("1", "Software Engineer", "A"), posting("2", "Software Engineer", "B"),
          posting("3", "Software Engineer II", "A")]
    _, stats = analyze_postings(ps)
    assert stats["flagged_postings"] == 3
    assert stats["flagged_unique_roles"] == 2


def test_unique_roles_fallback_title_team():
    _, stats = analyze_postings([posting("1", "Software Engineer"), posting("2", "Software Engineer ")])
    assert stats["flagged_unique_roles"] == 1


def test_csv_safe():
    assert csv_safe("=HYPERLINK(\"x\")") == "'=HYPERLINK(\"x\")"
    assert csv_safe("+1") == "'+1" and csv_safe("@SUM(A1)") == "'@SUM(A1)"
    assert csv_safe("Senior Engineer") == "Senior Engineer"
    assert csv_safe(5) == 5
