# Lighthouse — Presentation Build

Owner: Timur  
Scope: Minimum working demo for stakeholder presentation  
Base plans: PLAN.md · PLAN_Julie.md · PLAN_Timur.md

---

## Goal

A fully navigable, visually complete dashboard backed by a real database, with Jira ticket creation wired for L3/L4 mentions. The demo must run reliably from a single setup command and survive a live walkthrough without API dependency on the hot path.

The prototype to match is `prototype/dashboard.html` — font, colour tokens, layout, and all components are defined there. Do not deviate.

---

## What's In vs Backlogs

### In scope

| Component | Deliverable |
|---|---|
| Foundation | DB schema, models, `.env.example`, `requirements.txt` |
| Sample data | Seed script: inserts ~30 pre-classified mentions; covers all 5 archetypes at realistic volumes |
| Classification pipeline | PII redactor, Stage 1 sentiment (Claude Haiku), Stage 2 risk tier (Claude Sonnet), platform rules, routing, DB write |
| Jira ticket creation | L3/L4 only; `JIRA_MODE=live\|mock` flag (see below) |
| Response draft generation | Claude personalisation call; draft saved to DB; shown in compliance queue |
| Flask dashboard | All routes listed below; matches prototype exactly |
| Compliance queue actions | Review draft / Approve (no platform post) / Escalate / Dismiss |

### Backlogs — do not build for presentation

- Telegram notifications (`notifications/telegram.py`)
- Email notifications (`notifications/email.py`)
- SLA checker and reminders (`notifications/sla_checker.py`)
- Thread monitoring (`response/thread_monitor.py`)
- Weekly digest (`digest/`)
- Platform crawlers (Reddit, TrustPilot, X, Meta, TikTok, LinkedIn, etc.)
- Playwright screenshot capture
- Platform auto-posting (`response/poster.py`)
- Jira hourly sync (`jira/sync.py`)
- APScheduler continuous jobs
- nginx / TLS / production hardening

These share the same data path. Each is a new sink or source, not a redesign.

---

## Decisions Made

### 1 — Demo uses pre-classified seed data (no live Claude on hot path)

The seed script inserts pre-classified mentions directly into the DB. Classification pipeline is a separate mode triggered by `scripts/run_pipeline.py` — it can be demonstrated manually in a second tab but is not required for the dashboard to run.

**Rationale:** Eliminates API latency and failure risk during the presentation walkthrough.

### 2 — Jira runs in mock mode by default

Set `JIRA_MODE=mock` in `.env`. In mock mode, `jira/client.py` writes the Jira payload to `data/jira_payloads/<mention_id>.json` and returns a synthetic ticket ID (`DEMO-001`, `DEMO-002`, …). Set `JIRA_MODE=live` and supply real credentials to create actual Jira tickets.

**Rationale:** Demo works without a provisioned Jira sandbox. Swapping to live is one env-var change.

### 3 — Seed volume targets prototype numbers approximately

Seed produces approximately: L4 = 2, L3 = 9, L2 = 28, L1 = 41 (total ~80 mentions). The prototype shows 214 — that number is aspirational. Stakeholders won't count; distribution and tier colours matter.

**Rationale:** Five fixtures won't populate the stat cards convincingly.

### 4 — Screenshots use a static placeholder

A single `static/img/screenshot_placeholder.png` is used for all mention detail views. The seed script sets `screenshot_path = "static/img/screenshot_placeholder.png"` on every row.

**Rationale:** No Playwright setup needed; placeholder is visually sufficient for demo.

### 5 — "Approve & Post" records the response without posting

Clicking Approve in the compliance queue:
- Sets `routing_status = RESPONDED`, `resolution_status = responded`, `resolved_at = now()`
- Adds a comment to the Jira ticket (or writes to mock file)
- Shows a confirmation banner: "Response recorded — would post to [Platform] via API"
- No actual platform API call is made

**Rationale:** No platform API credentials needed for the demo.

### 6 — `DEMO_MODE=true` skips the login screen

When `DEMO_MODE=true` is set in `.env`, the app auto-authenticates as the demo user. Set `DEMO_MODE=false` (default) to re-enable Flask-Login for real deployments.

---

## File Structure

```
classification/
  __init__.py
  pipeline.py          # orchestrate: PII → Stage 1 → platform rules → Stage 2 → DB write
  pii_redactor.py
  platform_rules.py    # HIGH_RISK_PLATFORMS, apply_platform_floor, apply_client_info_escalation,
                       # detect_pending_axi_reply, derive_category
  stage1_sentiment.py  # Claude Haiku call
  stage2_risk.py       # Claude Sonnet call

jira/
  __init__.py
  client.py            # create_ticket(), add_response_comment(); respects JIRA_MODE env var

response/
  __init__.py
  templates.py         # seed response_templates table; template lookup by platform + category
  agent.py             # Claude personalisation call; saves draft to DB

scripts/
  seed_demo.py         # insert ~30 pre-classified mentions + seed response_templates
  run_pipeline.py      # optional: run classification on unclassified mentions in DB

prompts/
  stage1_sentiment.txt
  stage2_risk.txt
  response_personalise.txt

app.py                 # Flask app, Flask-Login, DEMO_MODE bypass
models.py              # SQLAlchemy models
db.py                  # engine + session factory

templates/
  base.html
  login.html
  index.html           # Overview — matches prototype exactly
  mentions.html        # Filterable mention list
  mention_detail.html  # Single mention: screenshot, text, classification, Jira link, draft
  compliance.html      # L3/L4 queue: review draft / approve / escalate / dismiss
  tickets.html         # Jira ticket list (created_at, status, mention link)
  runs.html            # Crawler run history (seeded rows)

static/
  img/
    screenshot_placeholder.png
  style.css            # Extract CSS from prototype/dashboard.html verbatim; do not redesign

.env.example
requirements.txt
```

---

## Database Schema (presentation subset)

Full schema is defined in PLAN_Julie.md and PLAN_Timur.md. The presentation build uses this subset:

```
mentions
  id                    UUID, primary key
  platform              str
  url                   str
  author                str
  posted_at             datetime
  title                 str | None
  raw_text              str
  raw_text_redacted     str | None
  summary               str
  screenshot_path       str | None
  engagement            int  default 0
  detected_language     str  default "en"
  -- classification --
  sentiment             str | None
  sentiment_reasoning   str | None
  risk_level            str | None
  risk_reasoning        str | None
  has_client_info       bool  default false
  pending_axi_reply     bool  default false
  routing_status        str | None
  category              str | None
  watch_flags           str | None
  classification_status str | None
  classification_error  str | None
  classified_at         datetime | None
  -- response --
  response_text         str | None
  -- jira --
  jira_ticket_id        str | None
  jira_status           str | None
  -- resolution --
  resolution_status     str | None
  resolution_reason     str | None
  resolved_at           datetime | None
  -- timestamps --
  created_at            datetime
  updated_at            datetime

response_templates
  id          UUID, primary key
  platform    str
  sentiment   str
  category    str
  template_text str

crawler_runs
  id            UUID, primary key
  platform      str
  started_at    datetime
  finished_at   datetime
  mentions_found int
  status        str   ("ok" / "error")
  error         str | None
```

---

## Build Phases

### Phase 1 — Foundation

- [ ] `requirements.txt` — flask, flask-login, sqlalchemy, psycopg2-binary, anthropic, requests
- [ ] `db.py` — SQLAlchemy engine + session factory; reads `DATABASE_URL` from env
- [ ] `models.py` — `Mention`, `ResponseTemplate`, `CrawlerRun` models matching schema above
- [ ] `.env.example` — all variables listed below, with comments
- [ ] `static/img/screenshot_placeholder.png` — any 800×500 placeholder image
- [ ] `static/style.css` — CSS extracted verbatim from `prototype/dashboard.html`

### Phase 2 — Sample Data Seed

- [ ] `scripts/seed_demo.py` — inserts ~30 mentions across all archetypes; distribution:
  - 2 × L4 (one with PII, one with regulatory language + high engagement)
  - 9 × L3 (mix of TrustPilot platform-floor, Reddit forum, ForexPeaceArmy, viral L2→L3)
  - 28 × L2 (Twitter, Facebook, Instagram — withdrawal, KYC, platform complaints)
  - 41 × L1 (Google Play positive, App Store positive, neutral Reddit queries)
  - Use the 5 fixtures in `sample_data/mentions/` as archetypes; vary author, timestamp, engagement count
- [ ] Seed sets `jira_ticket_id = "DEMO-00X"` on all L3/L4 rows (mock Jira IDs)
- [ ] Seed also inserts 5 × `CrawlerRun` rows (one per platform, status ok, 2–3 minutes ago) for the "Last crawler run" panel
- [ ] Seed inserts all 5 `ResponseTemplate` rows (categories from PLAN_Timur.md)
- [ ] Running `scripts/seed_demo.py` twice must be idempotent (delete-then-reinsert)

### Phase 3 — Classification Pipeline

*Required to demonstrate live classification. Not required for dashboard demo.*

- [ ] `prompts/stage1_sentiment.txt` — prompt with injection defence, CoT, JSON output, rules from PLAN_Julie.md
- [ ] `classification/pii_redactor.py` — regex: email, phone, account numbers (AXI-XXXXXX, >8-digit numeric strings)
- [ ] `classification/stage1_sentiment.py` — Claude Haiku call; parses `{"sentiment": ..., "reasoning": ...}`
- [ ] `prompts/stage2_risk.txt` — prompt with full L1–L4 rules from PLAN_Julie.md
- [ ] `classification/stage2_risk.py` — Claude Sonnet call; parses `{"risk_level": ..., "reasoning": ...}`
- [ ] `classification/platform_rules.py` — `HIGH_RISK_PLATFORMS`, `apply_platform_floor()`, `apply_client_info_escalation()`, `detect_pending_axi_reply()`, `derive_category()`
- [ ] `classification/pipeline.py` — orchestrate all steps for a single mention; write results to DB; mark `classification_status = error` on any failure
- [ ] `scripts/run_pipeline.py` — finds all mentions where `classification_status IS NULL`; runs pipeline on each; prints results

### Phase 4 — Jira Client

- [ ] `jira/client.py`:
  - `create_ticket(mention)` — builds ADF description (URL, summary, redacted text, reasoning, sentiment, tier, draft response); POST to Jira REST API v3 if `JIRA_MODE=live`; write JSON to `data/jira_payloads/<mention_id>.json` if `JIRA_MODE=mock`; returns ticket ID string
  - `add_response_comment(ticket_id, mention, posted_by)` — posts response text + metadata as a Jira comment; mock mode appends to the payload file
  - `update_ticket_status(ticket_id, transition_name)` — resolves and calls `/transitions`; mock mode logs only
- [ ] Priority mapping: L3 → `High`; L4 → `Critical`
- [ ] Labels: `["lighthouse", risk_level, platform]`
- [ ] `jira_ticket_id` and `jira_status` written back to `mentions` row after creation

### Phase 5 — Response Draft Agent

- [ ] `response/templates.py`:
  - `get_template(platform, category)` — looks up `response_templates` table
- [ ] `prompts/response_personalise.txt` — system prompt enforcing Axi brand voice (rules verbatim from PLAN_Timur.md); passes `detected_language`
- [ ] `response/agent.py`:
  - `generate_draft(mention)` — selects template, Claude personalisation call, saves `response_text` to DB
  - Called by `jira/client.py` create flow so the Jira ticket body includes the draft

### Phase 6 — Flask Dashboard

Match `prototype/dashboard.html` exactly: same CSS variables, same layout, same component structure.

- [ ] `app.py` — Flask app; `DEMO_MODE=true` bypasses Flask-Login; all routes defined here
- [ ] `templates/login.html` — login form (only shown when `DEMO_MODE=false`)
- [ ] `templates/base.html` — nav bar + shared layout from prototype; nav badge on Compliance = count of `PENDING_HUMAN_POST` mentions
- [ ] `templates/index.html` — Overview page:
  - Date range picker (client-side only, same JS as prototype)
  - Status bar: green "All mentions classified" / red "X classification errors" linking to `/errors`
  - 7 stat cards: Total, L4, L3, L2, L1, Positive, Negative — queried from DB filtered to selected date range
  - Recent mentions table: last 7 mentions ordered by `posted_at` desc
  - Compliance queue panel (right): first 3 `PENDING_HUMAN_POST` mentions
  - Watch list panel (right): query `watch_flags`, count per term vs prior 7-day window, spike logic
  - Last crawler run panel (right): last row per platform from `crawler_runs`
- [ ] `templates/mentions.html` — filterable by platform, tier, sentiment, date; paginated (25/page)
- [ ] `templates/mention_detail.html` — screenshot (placeholder), raw text, classification card (sentiment + tier + reasoning + flags), Jira ticket ID + link to `/tickets`, draft response; "Open in Jira" button if `JIRA_MODE=live`
- [ ] `templates/compliance.html` — L3/L4 queue:
  - Shows `routing_status = PENDING_HUMAN_POST` only
  - Per item: tier badge, platform, engagement, mention snippet, draft response (expandable)
  - **Approve** → sets `resolution_status = responded`, posts Jira comment, shows banner; does NOT call any platform API
  - **Escalate** → sets `resolution_status = escalated`, updates Jira status
  - **Dismiss** → sets `resolution_status = not_relevant`; requires one-line reason (inline text input before confirming)
- [ ] `templates/tickets.html` — all rows where `jira_ticket_id IS NOT NULL`; shows ticket ID, mention snippet, platform, tier, status, created_at
- [ ] `templates/runs.html` — all rows from `crawler_runs` table, newest first

---

## Environment Variables

```
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/lighthouse

# Anthropic (classification + response drafts)
ANTHROPIC_API_KEY=

# Jira
JIRA_MODE=mock                    # "mock" writes to data/jira_payloads/; "live" calls Jira API
JIRA_BASE_URL=                    # e.g. https://yourcompany.atlassian.net  (live only)
JIRA_EMAIL=                       # (live only)
JIRA_API_TOKEN=                   # (live only)
JIRA_PROJECT_KEY=CX               # (live only)
JIRA_COMMUNITY_MANAGER_ACCOUNT_ID=  # (live only)

# Dashboard
DEMO_MODE=true                    # "true" skips login; "false" enables Flask-Login
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=               # min 20 chars; required when DEMO_MODE=false
SECRET_KEY=                       # min 32 random bytes; required when DEMO_MODE=false
DASHBOARD_URL=http://localhost:5000

# Response drafts
SUPPORT_URL=https://support.axi.com
```

---

## What the Demo Fakes vs Omits

| Item | How the demo handles it |
|---|---|
| Telegram/email alerts | Backlogs for Phase 8 — same classification event, new sink |
| Platform API posting | "Approve" records the response locally; banner says "would post to [platform]" |
| Live crawlers | Seeded `CrawlerRun` rows show realistic "last run" panel; no actual crawl |
| Screenshots | Static placeholder image; same path for all mentions |
| Jira sandbox (optional) | `JIRA_MODE=mock` writes payloads to `data/jira_payloads/` locally |
| SLA reminders | Not shown; compliance queue and Jira tickets surface the same risk |
| Weekly digest | Not built; data for it exists in DB |

---

## Demo Script (how to run)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up DB and .env
# Copy .env.example to .env, fill in DATABASE_URL and ANTHROPIC_API_KEY

# 3. Create tables
python -c "from db import engine; from models import Base; Base.metadata.create_all(engine)"

# 4. Seed demo data
python scripts/seed_demo.py

# 5. Start dashboard
flask run

# 6. (Optional) Demonstrate live classification
# Wipe classification fields from a few rows in DB, then:
python scripts/run_pipeline.py
```

---

## Verification

- [ ] `seed_demo.py` runs clean; stat cards on Overview show the expected tier distribution
- [ ] Date range picker filters stat cards and mention table correctly
- [ ] All 7 routes load without errors; nav badge on Compliance shows correct count
- [ ] Compliance queue shows only `PENDING_HUMAN_POST` mentions; Approve / Escalate / Dismiss all write correct DB state
- [ ] Approve writes Jira comment to `data/jira_payloads/<id>.json` (mock) or Jira ticket (live)
- [ ] Dismiss requires a reason — form blocks empty submit
- [ ] Watch list panel shows spike logic correctly (withdrawal, FCA terms should spike based on seed data)
- [ ] Mention detail shows draft response, classification reasoning, and tier badge
- [ ] `run_pipeline.py` correctly classifies a hand-picked L3 and L4 mention; platform floor annotation appears in `risk_reasoning`; `jira_ticket_id` is set
- [ ] `DEMO_MODE=true` skips the login screen; `DEMO_MODE=false` requires credentials
