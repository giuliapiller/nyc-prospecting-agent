from prospecting.companies import Company
from prospecting.github import CHECKS, domain_matches, is_company_org, summarize, tool_stack_label


def co(name, site):
    return Company(name, site, "", "")


def org(login, blog=None, email=None, repos=10, verified=False):
    return {"login": login, "blog": blog, "email": email, "public_repos": repos, "is_verified": verified}


def test_labels():
    assert tool_stack_label(set()) == "No public signal"
    assert tool_stack_label({"agents_md"}) == "AGENTS.md only"
    assert tool_stack_label({"cursor"}) == "Uses Cursor"
    assert tool_stack_label({"claude_code", "agents_md"}) == "Uses Claude Code"
    assert tool_stack_label({"copilot"}) == "Uses Copilot"
    assert tool_stack_label({"cursor", "copilot"}) == "Mixed"


def test_domain_matches():
    assert domain_matches(co("Datadog", "datadoghq.com"), org("DataDog", blog="https://datadoghq.com"))[1]
    assert domain_matches(co("Bloomberg", "bloomberg.com"), org("b", blog="https://techatbloomberg.com")) == ("blog: techatbloomberg.com", False)
    dd = co("Datadog", "datadoghq.com")
    assert domain_matches(dd, org("DataDog", blog="https://datadoghq.com"))[0]
    assert domain_matches(dd, org("x", email="info@datadoghq.com"))[0]
    assert domain_matches(co("Zocdoc", "zocdoc.com"), org("Zocdoc", blog="engineering.zocdoc.com"))[1]
    assert not domain_matches(co("Fox Corporation", "foxcorporation.com"), org("fox-it", blog="https://fox-it.com"))[0]
    assert not domain_matches(dd, org("x", blog=None))[0]
    assert not domain_matches(co("BlackRock", "blackrock.com"), org("BlackrockNeurotech", blog="https://blackrockneurotech.com"))[0]


def test_is_company_org_rejects_spoofs_and_empty_orgs():
    ch = co("Chainalysis", "chainalysis.com")
    assert not is_company_org(ch, org("DEVENLOPMENT-VIETNAM-TEAM", blog="https://www.chainalysis.com/"))
    assert not is_company_org(ch, org("chainalysis", blog="https://chainalysis.com", repos=0, verified=True))
    assert is_company_org(co("Peloton", "onepeloton.com"), org("pelotoncycle", blog="www.onepeloton.com"))
    assert is_company_org(co("Two Sigma", "twosigma.com"), org("twosigma", blog="https://twosigma.com"))
    assert is_company_org(co("Datadog", "datadoghq.com"), org("vectordotdev", email="v@datadoghq.com", verified=True))
    lem = co("Lemonade", "lemonade.com")
    assert is_company_org(lem, org("lemonade-hq", blog="https://lemonade.com", verified=True))
    assert not is_company_org(lem, org("AlexsLemonade", blog="https://www.alexslemonade.org"))
    assert not is_company_org(lem, org("lemonadesocial", blog="https://lemonade.social/", verified=True))
    assert not is_company_org(co("Travelers", "travelers.com"), org("WanderlandTravelers", blog="https://wanderlandtravelers.us"))
    assert is_company_org(co("American Express", "americanexpress.com"), org("americanexpress", blog="https://americanexpress.io"))


def check(label):
    return next(c for c in CHECKS if c.label == label)


def test_path_filters():
    assert check(".cursor/").match.search("svc/.cursor/rules/general.mdc")
    assert not check(".cursor/").match.search("src/db.cursor.py")
    assert check(".cursorrules").match.search(".cursorrules")
    assert check("CLAUDE.md").match.search("pkg/CLAUDE.md")
    assert not check("CLAUDE.md").match.search("docs/claude.md.bak")
    assert not check("AGENTS.md").match.search("docs/development/agents.md")
    assert check("AGENTS.md").match.search("svc/AGENTS.md")
    assert check(".github/copilot-instructions.md").match.search(".github/copilot-instructions.md")
    assert not check(".github/copilot-instructions.md").match.search("docs/copilot-instructions.md")
    assert check(".github/instructions/").match.search(".github/instructions/python.instructions.md")
    assert not check(".github/instructions/").match.search(".github/instructions/README.md")


def test_summarize_counts_repos_not_files():
    files = [{"repo": "o/a", "tool": "cursor", "file_type": ".cursor/"},
             {"repo": "o/a", "tool": "cursor", "file_type": ".cursor/"},
             {"repo": "o/b", "tool": "agents_md", "file_type": "AGENTS.md"}]
    s = summarize(files)
    assert s["tool_stack_label"] == "Uses Cursor"
    assert s["cursor_repos"] == 1 and s["agents_md_repos"] == 1
    assert s["ai_files_found"] == ".cursor/ (1 repo); AGENTS.md (1 repo)"
