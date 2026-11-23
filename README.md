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
- **Role sections only.** Keywords count only under responsibilities/requirements headings ("What you'll do", "Requirements", "About you", ...). Intro, "About us", benefits and similar sections are ignored. Headings are listed in `config/job_sections.csv`. Postings with no recognizable heading are scanned whole and counted in `unstructured_engineering_postings`.
- **Vendor-context filter.** Sentences about the employer's own product or its customers' projects are dropped before matching, so MongoDB's app-modernization offering or "help customers migrate" doesn't count. Phrases are regexes in `config/vendor_context.txt`; the filter also applies to job titles.
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

## Phase 3: why-now score, personas, outreach angle

```bash
python -m prospecting phase3   # reads output/phase1_*.csv and output/phase2_github.csv
```

### Score (0–100)

| Component | Max | Input | How |
|---|---|---|---|
| Project-shaped work | 45 | `flagged_unique_roles` (legacy/migration/modernization, test coverage, security remediation) | log scale, full points at 10 unique roles |
| Engineering hiring volume | 20 | `engineering_postings` | log scale, full points at 100 postings |
| NYC presence | 15 | HQ cue in `companies.csv` + `nyc_engineering_postings` | 7.5 for an NYC HQ (5 for NY metro, e.g. Purchase, Lake Success) + up to 7.5 for NYC engineering postings, full at 5 |
| Tool stack | 20 | Phase 2 label | any keyboard AI tool (Cursor, Claude Code, Copilot, Mixed) 20; AGENTS.md only 15; no public signal 10 |

Why these weights: project-shaped work (45) is the strongest sign a team has whole projects to hand off, so it carries the most weight. Hiring volume (20) shows engineering capacity is tight. NYC presence (15) matters for in-person selling. Tool stack (20) rewards AI-forward orgs that have already bought keyboard AI tools. Devin complements those tools, so a keyboard-tool company scores highest, not lowest. Log scales keep one very large board (MongoDB, Jane Street) from flattening everyone else. Weights and caps are constants at the top of `prospecting/scoring.py`.

### Limited data

A company with no public Greenhouse/Lever/Ashby board or no GitHub org found is marked `data_quality=limited data`, and `limited_data_reason` says why. It stays in the ranking. Missing inputs score 0 (and "no public signal" for tool stack), so a company with no board can reach at most about 27. Treat its rank as "unknown", not "low priority".

### Personas (inferred titles only, no names)

- **Executive entry point:** CIO for banking, payments, asset management, financial data, market/fintech infrastructure, insurance, telecom and pharma. Head of Engineering for orgs with fewer than 10 open engineering postings. CTO otherwise.
- **Hands-on owner:** the most common inferred hiring-manager title across the company's flagged postings (VP wins ties). If there are none, a sector default is used, and `persona_owner_basis` says so.

### Outreach angle

One rule-based sentence per company: the specific signal (role count, keywords and an example title, or the `why_on_list` cue when there are no postings) followed by a tool-stack clause. Companies with a keyboard AI tool get "you already have AI for individual engineers; Devin finishes whole projects". Angles never suggest switching away from a tool.

### Outputs

- `output/phase3_ranked.csv`: all companies ranked, with score components, data quality, signal summary, evidence link, both personas and the angle.
- `output/dashboard.html`: self-contained one-page view of the top 10 (score, why-now signal, evidence link, personas, angle).
- The run log lists companies whose careers site uses Workday.
