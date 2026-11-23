from collections import Counter

import pytest

from prospecting.companies import Company
from prospecting.phase3 import build_rows, render_dashboard
from prospecting.scoring import (TOOL_STACK_POINTS, WEIGHTS, executive_persona, hq_area, log_scaled,
                                 outreach_angle, owner_persona, score)


def test_weights_sum_to_100():
    assert sum(WEIGHTS.values()) == 100


def test_tool_stack_points_match_spec():
    for label in ("Uses Cursor", "Uses Claude Code", "Uses Copilot", "Mixed"):
        assert TOOL_STACK_POINTS[label] == 20
    assert TOOL_STACK_POINTS["AGENTS.md only"] == 15
    assert TOOL_STACK_POINTS["No public signal"] == 10


def test_log_scaled_is_monotonic_and_capped():
    vals = [log_scaled(n, 10, 45) for n in range(0, 15)]
    assert vals[0] == 0 and vals == sorted(vals)
    assert vals[10] == pytest.approx(45) and vals[14] == pytest.approx(45)
    assert log_scaled(1, 10, 45) > 45 / 10  # first role matters more than a linear scale would say


def test_score_bounds_and_components():
    top = score(flagged_unique_roles=50, engineering_postings=500, nyc_engineering_postings=50, hq="nyc",
                tool_stack_label="Mixed")
    assert top == {"project_work": 45, "hiring": 20, "nyc": 15, "tool_stack": 20, "total": 100}
    empty = score(flagged_unique_roles=0, engineering_postings=0, nyc_engineering_postings=0, hq="",
                  tool_stack_label="No public signal")
    assert empty["total"] == 10
    metro = score(flagged_unique_roles=0, engineering_postings=0, nyc_engineering_postings=0, hq="ny_metro",
                  tool_stack_label="Unknown label")
    assert metro["nyc"] == 5 and metro["tool_stack"] == 10


def test_project_work_dominates_tool_stack():
    a = score(flagged_unique_roles=5, engineering_postings=20, nyc_engineering_postings=5, hq="nyc",
              tool_stack_label="No public signal")
    b = score(flagged_unique_roles=0, engineering_postings=20, nyc_engineering_postings=5, hq="nyc",
              tool_stack_label="Uses Cursor")
    assert a["total"] > b["total"]


def test_hq_area():
    assert hq_area("NYC HQ; big bank") == "nyc"
    assert hq_area("Brooklyn HQ; PHP") == "nyc"
    assert hq_area("Purchase NY HQ; payments") == "ny_metro"
    assert hq_area("Lake Success NY HQ") == "ny_metro"
    assert hq_area("London HQ") == "" and hq_area("") == ""


def test_personas():
    assert executive_persona("Banking", 0) == "CIO"
    assert executive_persona("Fintech", 6) == "Head of Engineering"
    assert executive_persona("Software", 100) == "CTO"
    assert owner_persona(["Director of Platform Engineering", "VP Platform Engineering",
                          "VP Platform Engineering", "CTO / SVP Engineering"], "Software")[0] == "VP Platform Engineering"
    title, basis = owner_persona([], "Insurance")
    assert title == "Head of Application Modernization" and "default" in basis


@pytest.mark.parametrize("label,tools", [("Uses Cursor", ["cursor"]), ("Mixed", ["cursor", "copilot"]),
                                         ("Uses Claude Code", ["claude_code"]), ("Uses Copilot", ["copilot"])])
def test_angle_is_complementary_for_keyboard_tools(label, tools):
    a = outreach_angle(company="Acme", roles=3, keywords=["migration"], categories=Counter(modernization=3),
                       example_title="Platform Engineer", tool_stack_label=label, tools=tools, why_on_list="NYC HQ")
    assert "you already have AI for individual engineers" in a and "Devin finishes whole projects" in a
    for bad in ("switch", "replace", "instead of", "displace", "rip out"):
        assert bad not in a.lower()
    assert a.replace("e.g.", "").count(".") == 1 and a.endswith(".")


def test_angle_without_postings_uses_profile():
    a = outreach_angle(company="BNY", roles=0, keywords=[], categories=Counter(), example_title="",
                       tool_stack_label="No public signal", tools=[], why_on_list="NYC HQ; core custody systems")
    assert a.startswith("For BNY (core custody systems),") and "Devin finishes whole projects" in a


def _fixture():
    companies = [Company("Acme", "acme.com", "Software", "NYC HQ; big"),
                 Company("Bank", "bank.com", "Banking", "NYC HQ; legacy core")]
    p1c = [{"company": "Acme", "board_status": "found", "board_provider": "greenhouse", "ats_detected": "",
            "engineering_postings": "40", "nyc_engineering_postings": "10", "flagged_postings": "3",
            "flagged_unique_roles": "3", "flagged_by_category": "modernization=3", "existing_customer_public": "no"},
           {"company": "Bank", "board_status": "not_found", "board_provider": "", "ats_detected": "workday",
            "existing_customer_public": "no"}]
    p1p = [{"company": "Acme", "job_title": "Platform Engineer", "nyc": "yes", "matched_keywords": "migration",
            "keyword_categories": "modernization", "link": "https://jobs/1",
            "likely_hiring_manager_title_inferred": "VP Platform Engineering"}]
    p2 = [{"company": "Acme", "github_orgs": "acme", "tool_stack_label": "Uses Cursor", "cursor_repos": "2",
           "copilot_repos": "0", "claude_code_repos": "0", "ai_files_found": ".cursor/ (2 repos)",
           "example_repos": "acme/app", "scan_complete": "yes"},
          {"company": "Bank", "github_orgs": "", "tool_stack_label": "No public signal", "scan_complete": "yes"}]
    return build_rows(companies, p1c, p1p, p2)


def test_build_rows_ranks_and_marks_limited_data():
    rows = _fixture()
    assert [r["company"] for r in rows] == ["Acme", "Bank"] and rows[0]["rank"] == 1
    acme, bank = rows
    assert acme["data_quality"] == "ok" and acme["evidence_link"] == "https://jobs/1"
    assert acme["persona_owner_inferred"] == "VP Platform Engineering"
    assert "Cursor" in acme["outreach_angle"]
    assert bank["data_quality"] == "limited data"
    assert "workday" in bank["limited_data_reason"] and "no GitHub org" in bank["limited_data_reason"]


def test_dashboard_escapes_and_limits_to_top_n():
    rows = _fixture()
    rows[0]["company"] = "<script>x</script>"
    out = render_dashboard(rows, top_n=1)
    assert "<script>x" not in out and "&lt;script&gt;" in out
    assert "Bank" not in out


def test_total_rounds_unrounded_sum():
    s = score(flagged_unique_roles=0, engineering_postings=9, nyc_engineering_postings=0, hq="nyc",
              tool_stack_label="No public signal")
    assert s["total"] == round(log_scaled(9, 100, 20) + 7.5 + 10)
