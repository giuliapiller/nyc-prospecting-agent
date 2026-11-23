from prospecting.boards import Posting
from prospecting.phase1 import analyze_postings
from prospecting.sections import drop_vendor_context, load_config, relevant_text, role_sections

CFG = load_config()

VENDOR_POSTING = """About MongoDB
MongoDB powers the AI Application Modernization Program, helping enterprises migrate legacy apps.
What you'll do
Build distributed query execution features in C++.
Requirements
5+ years of systems programming.
Why you should apply
Join our app modernization offering and help customers' legacy migration."""

INTERNAL_POSTING = """About the team
We run the payments platform.
Responsibilities
Lead the migration of our ledger off the legacy mainframe.
Benefits
Great health insurance."""


def test_role_sections_keeps_only_responsibilities_and_requirements():
    text, structured = role_sections(VENDOR_POSTING, CFG)
    assert structured
    assert "C++" in text and "systems programming" in text
    assert "Modernization Program" not in text and "customers" not in text


def test_unstructured_falls_back_to_whole_text():
    text, structured = role_sections("Help us migrate to Kubernetes.", CFG)
    assert not structured and "migrate" in text


def test_vendor_sentences_are_dropped():
    text = drop_vendor_context("We help customers modernize legacy apps. You will reduce tech debt.", CFG)
    assert "tech debt" in text and "customers" not in text
    assert drop_vendor_context("Own Relational Migrator releases.", CFG) == ""
    assert "migration" in drop_vendor_context("Drive the migration of our billing service.", CFG)


def posting(pid, desc, title="Senior Software Engineer"):
    return Posting("Acme", "greenhouse", pid, title, "Engineering", ["New York, NY"], "https://x", desc)


def test_vendor_context_does_not_flag_but_internal_work_does():
    rows, stats = analyze_postings([posting("1", VENDOR_POSTING), posting("2", INTERNAL_POSTING)], CFG)
    assert stats["flagged_postings"] == 1
    assert "migration" in rows[0]["matched_keywords"] and "mainframe" in rows[0]["matched_keywords"]
    assert relevant_text(INTERNAL_POSTING, CFG)[1]


def test_vendor_product_titles_do_not_flag():
    rows, stats = analyze_postings([posting("1", "Responsibilities\nBuild the sync service.",
                                            title="Senior Software Engineer, Migration Tooling")], CFG)
    assert stats["flagged_postings"] == 0


def test_short_bullets_are_not_lost_or_section_enders():
    desc = ("Responsibilities\nYou have experience migrating legacy systems\nManage benefits enrollment integrations\n"
            "Reduce tech debt in the payroll service\nBenefits\nUnlimited PTO and migration stipend")
    text, structured = role_sections(desc, CFG)
    assert structured
    assert "migrating legacy systems" in text and "tech debt" in text
    assert "stipend" not in text


def test_inline_formatting_keeps_vendor_sentence_whole():
    from prospecting.boards import html_to_text
    text = html_to_text("<h3>Responsibilities</h3><p>We help <strong>customers</strong> migrate their systems.</p>"
                        "<ul><li>Own <a href='#'>billing</a></li><li>Line one<br>line two</li></ul>")
    assert text.split("\n") == ["Responsibilities", "We help customers migrate their systems.", "Own billing",
                                 "Line one", "line two"]
    assert "migrate" not in relevant_text(text, CFG)[0]


def test_internal_migration_tooling_still_counts():
    assert "migration" in drop_vendor_context("Build migration tooling for our internal billing database.", CFG)
    assert drop_vendor_context("Build migration tooling used by thousands of developers.", CFG) == ""
