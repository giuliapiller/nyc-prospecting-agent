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
