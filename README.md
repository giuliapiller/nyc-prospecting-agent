# NYC prospecting agent

Finds public "why now" signals for selling an AI coding agent to the NYC enterprises in `companies.csv`.
It's built in phases. This README will be expanded in Phase 4.

## Phase 1: job-posting signals

```bash
pip install -r requirements.txt
python -m prospecting phase1        # writes output/*.csv and output/run.log
python -m pytest -q
```

How it works:
- **Board discovery.** For each company, it scans the public careers page for ATS fingerprints and board links. It then tries name and domain slugs on the public Greenhouse, Lever and Ashby JSON APIs.
- **Slug-collision check.** A board only counts if its name matches the company, or the company's name or domain appears in the postings. For example, Greenhouse `fox` is a vet clinic and Ashby `jane` is a health app.
- **Overrides.** Pin or block a board in `config/board_overrides.csv` (`provider=none` blocks).
- **Skipped companies.** Companies without a public board are logged and written to `output/no_public_board.csv`, with the detected ATS (e.g. Workday) when it can be identified.
- **Engineering filter.** Engineering postings are picked by title and team. Customer-facing "engineers" are excluded: sales/solutions/support/consulting/forward-deployed roles.
- **Keyword matching.** Matching runs on the title plus the description. Text blocks repeated across 25% or more of a company's postings (About us, EEO, benefits) are removed first. Rules live in `prospecting/keywords.py`:

| Category | Keywords |
|---|---|
| legacy_stack | COBOL, mainframe, Java 8, .NET Framework, SAS, Angular |
| modernization | legacy (technical context only), modernization, migration, re-platforming, tech debt |
| test_coverage | test coverage |
| security_remediation | security/vulnerability remediation, CVE |

- **`existing_customer_public`.** Each company is matched against the case-study cards on https://devin.ai/customers.

Outputs:
- `output/phase1_postings.csv` has one row per flagged posting: title, team, location, `nyc`, matched keywords, an evidence snippet, link, and `likely_hiring_manager_title_inferred`. That last field is a rule-based guess at a title, never a person.
- `output/phase1_companies.csv` has board status and posting counts per company, plus `existing_customer_public`.
- `output/no_public_board.csv` lists the companies that were skipped.

API responses are cached in `.cache/` for 20h. Set `PROSPECTING_CACHE_TTL=0` to force a refresh.

## Phase 2: AI tool-stack signal (GitHub)

```bash
GITHUB_TOKEN=... python -m prospecting phase2   # writes output/phase2_*.csv; ~25 min cold, seconds when cached
```

How it works:
- **Org discovery.** Candidate orgs come from GitHub org search (company name and domain stem) plus login guesses. Anyone can type any website into an org profile, so a domain alone isn't enough:
  - Website/email on the company's domain: the org must also be GitHub-verified or have a login containing the company name or domain stem.
  - Website on a sibling domain named after the company (`americanexpress.io`, `techatbloomberg.com`): the login must be exactly the company name or domain stem. This rejects `alexslemonade.org`, `lemonade.social` and `wanderlandtravelers.us`.
  - Orgs with no public repos are skipped; up to 5 orgs per company are scanned.
- **Overrides.** Pin orgs in `config/github_orgs.csv` (`orgs` is `;`-separated).
- **File checks.** One GitHub code-search query per org per file type, with returned paths re-checked by regex:

| Tool | Files |
|---|---|
| Cursor | `.cursorrules`, `.cursor/` |
| Claude Code | `CLAUDE.md` |
| Copilot | `.github/copilot-instructions.md`, `.github/instructions/*.instructions.md` |
| Agent-aware | `AGENTS.md` (tool-neutral) |

- **Labels.** `Uses Cursor` / `Uses Claude Code` / `Uses Copilot` for one keyboard tool, `Mixed` for two or more, `AGENTS.md only` when the only file is AGENTS.md, else `No public signal`. AGENTS.md is always listed in `ai_files_found`.
- **Rate limits.** Requests are paced under GitHub's limits (code search 10/min, search 30/min) and back off on `Retry-After` / `X-RateLimit-Reset`. Responses are cached with the Phase 1 cache.
- **Privacy.** Only org profiles, repo names and file paths are read. No members, commit authors or contributor data.

Outputs:
- `output/phase2_github.csv`: per company, the matched orgs and why they matched, the label, repo counts per tool, `ai_files_found`, example repos, and `scan_complete`.
- `output/phase2_ai_files.csv`: one row per matched file (org, repo, path, link) for spot-checking.

Limits: code search only sees default branches of public, non-fork repos and returns at most 100 hits per query, so repo counts for very large orgs are lower bounds. Public repos are mostly open-source projects, so "No public signal" says nothing about internal tooling.
