# Lighthouse v1 — Timur: Response, Jira, Dashboard & Scheduler

Owner: Timur  
Depends on: Som's Crawler/Enrichment Layer + Julie's Classification Layer  
This is the terminal layer — everything the end user sees and acts on.

> **STATUS: PLANNING PHASE ONLY**
> Do not begin implementation. The goal right now is to identify all edge cases, validate the logic, and surface any unknowns before a single line of code is written. Review each section critically and add questions or concerns inline.

---

## Context

Timur owns everything downstream of classification. This includes: auto-replying to L1/L2 mentions, routing L3/L4 to the compliance queue, creating and syncing Jira tickets, the Flask dashboard, and the APScheduler that ties the whole pipeline together. This layer reads `routing_status` from the `mentions` table and drives all outcomes from there.

---

## Architecture Position

```
[3] Classification Layer   → Julie
    │
    ├── L1 / L2 ──────────► [4a] Response Agent   ← Timur
    │
    └── L3 / L4 ──────────► [4b] Compliance Queue ← Timur
    │
    ▼
[5] Jira Sync              ← Timur
    │
    ▼
[6] Dashboard (Flask)      ← Timur
    │
    ▼
[7] Scheduler              ← Timur
```

---

## Data Contract — What Timur Receives from Julie

Every row Timur's layer acts on looks like this. This is the agreed interface between Julie's pipeline and Timur's orchestrator.

```json
{
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "platform": "reddit",
  "url": "https://reddit.com/r/Forex/comments/abc123/axi_withdrawal_pending",
  "author": "trader_xyz",
  "posted_at": "2026-04-30T08:14:00Z",
  "title": "Axi withdrawal still pending after 3 weeks",
  "raw_text": "Has anyone else had issues with Axi? My withdrawal has been pending for 3 weeks and support keeps closing my tickets.",
  "summary": "User reports a 3-week pending withdrawal, expresses frustration, and asks if others have had similar experiences.",
  "screenshot_path": "data/screenshots/f47ac10b.png",
  "sentiment": "negative",
  "sentiment_reasoning": "Post expresses clear frustration about a delayed withdrawal process.",
  "risk_level": "L3",
  "risk_reasoning": "Withdrawal complaint with regulatory implication. User mentions escalating to a financial regulator if unresolved.",
  "routing_status": "PENDING_HUMAN_POST",
  "classified_at": "2026-04-30T08:15:32Z",
  "thread_id": "t3_abc123"
}
```

**Key fields Timur's layer consumes:**

| Field | Who sets it | Used for |
|---|---|---|
| `platform` | Som | Selects posting method + template |
| `sentiment` | Julie Stage 1 | Selects response template |
| `risk_level` | Julie Stage 2 | Routes to auto-reply vs human queue |
| `routing_status` | Julie | Entry condition for all of Timur's jobs |
| `summary` | Som enrichment | Shown in dashboard + Telegram alert + Jira ticket |
| `screenshot_path` | Som enrichment | Shown in dashboard + Jira ticket |
| `thread_id` | Som | Used by thread monitor to poll for replies |
| `raw_text` | Som | Passed to Claude for response personalisation |

---

## Component 4a — Response Agent

For mentions where `routing_status = PENDING_AUTO_RESPOND` or `routing_status = PENDING_HUMAN_POST`.

- `LOGGED_ONLY` — no response generated; mention is counted in stats and digest only (positive reviews on non-app-store platforms)
- `PENDING_AUTO_RESPOND` — draft generated and posted automatically (L1/L2 on standard platforms; positive App Store reviews)
- `PENDING_HUMAN_POST` — draft generated and queued; Community Manager approves and posts (L4, client info, pending reply, forum mentions)

**Flow:**
1. Read mention from DB (platform, raw_text, summary, sentiment, risk_level, routing_status)
2. Select the correct response template from `response_templates` table based on platform + sentiment + category
3. Claude call — personalise the template to the specific mention and write the full response in the **same language as the original mention** (use `detected_language` from Julie's layer). Templates are authored in English; Claude translates as part of the personalisation call. English mentions skip the translation cost. This rule applies to all responses — auto-posted and human-approved.
4. If `PENDING_AUTO_RESPOND`: post reply via platform API → update DB: `response_text`, `response_posted_at`, `response_url`, `routing_status = AUTO_RESPONDED`
5. If `PENDING_HUMAN_POST`: save draft to DB → surface in dashboard approval queue → human clicks post → same DB update

---

### Brand Voice & Tone

All responses — auto-posted and human-approved — must follow the Axi brand voice:

- **Polite and professional**: never defensive, never dismissive, never casual
- **Corporate but human**: warm and empathetic without being informal; acknowledge the person, not just the issue
- **Solution-oriented**: every response should offer a clear next step (support link, email, callback, escalation path) — never a dead end
- **Consistent with Axi's website tone**: measured, confident, regulated-industry appropriate
- **No discounts, no admissions of fault, no legal commitments** in any auto-generated response — these require human review

These constraints must be encoded directly in the Claude system prompt for the personalisation call. Claude is not given latitude on tone or language — the prompt enforces both.

**Language rule:** responses are always written in the same language as the original mention. `detected_language` (ISO 639-1) is passed to Claude in the prompt. English mentions receive English responses; all others receive a response in their language. No exceptions.

Prompt file: `prompts/response_personalise.txt`

---

> **Note on `category` field:** Category is assigned upstream — by Som's enrichment layer or Julie's classification pipeline — and arrives as a pre-populated field. Timur's response agent consumes it but does not determine it. Coordinate with Som and Julie to confirm the field name, allowed values, and which stage sets it.

**Template categories (to be written before Phase 4 ships):**

| Category | Trigger | Routing | Template purpose |
|---|---|---|---|
| Positive review — App Store | sentiment = positive, platform = google_play or app_store | `PENDING_AUTO_RESPOND` | Thank you + brand reinforcement, encourage rating |
| Positive review — other platforms | sentiment = positive, platform = anything else | `LOGGED_ONLY` | No response — counted only |
| General complaint L1 | risk_level = L1, negative | `PENDING_AUTO_RESPOND` | Acknowledgement + support link |
| Minor product complaint L2 | risk_level = L2, negative | `PENDING_AUTO_RESPOND` | Acknowledgement + resolution path |
| L4 / client identified | risk_level = L4 or has_client_info | `PENDING_HUMAN_POST` | Empathetic acknowledgement + escalation to private support — no detail discussed publicly |
| Forum mention | platform in FORUM_PLATFORMS | `PENDING_HUMAN_POST` | Community-appropriate acknowledgement + invite to contact support privately |

**Per-platform posting methods:**

| Platform | Posting method |
|---|---|
| Reddit | `praw` — reply to comment/post |
| TrustPilot | Playwright — owner reply via logged-in session |
| X (Twitter) | X API v2 — reply tweet |
| Facebook / Instagram | Meta Graph API — comment reply |
| App stores | Manual (no public API for owner replies) — flag for human |
| Forums / Web | Flag for human — no API available |

### Thread Monitoring (L1 / L2 escalation detection)

After an L1/L2 mention is auto-responded, the conversation does not end. A customer may reply and escalate — turning an L1/L2 into an L3/L4 situation. The thread monitor handles this.

**Flow:**
- After auto-reply is posted, store `thread_id` / `parent_url` alongside the mention
- Thread monitor job (runs daily, same cadence as crawler) checks for new replies on all `AUTO_RESPONDED` threads
- If a new reply is found: create a new mention record, run it through Julie's classification pipeline
- If the new mention classifies as L3 or L4: trigger compliance queue and Slack/Teams alert as normal
- No re-classification of the original mention — the new reply is treated as a fresh mention with its own record

File: `response/agent.py`, `response/poster.py`, `response/templates.py`, `response/thread_monitor.py`

---

## Component 4c — Immediate Notifications (L3 / L4)

Triggered the moment Julie's classification pipeline writes `risk_level = L3` or `risk_level = L4` to the DB — before the community manager next opens the dashboard.

**Channels:**
- **Telegram** — message sent to the community manager's Telegram via Bot API. Fires for every L3 and L4.
- **Email** — backup alert to the community manager's email address via SMTP. Same trigger.

**Telegram message format:**
```
🔴 [L4] TrustPilot — Action required
"[first 100 chars of mention text]..."
Platform: TrustPilot | Engagement: 847
Draft response ready. Open: https://lighthouse.axi.com/mention/1234
```

```
🟠 [L3] Reddit r/Forex — Review needed
"[first 100 chars of mention text]..."
Platform: Reddit | Engagement: 312
Draft response ready. Open: https://lighthouse.axi.com/mention/5678
```

Link uses `DASHBOARD_URL` from `.env` — update this to the live domain before deploying.

**Rules:**
- L4 → Telegram + email, immediately on classification
- L3 → Telegram + email, immediately on classification
- L1 / L2 → no notification; dashboard only
- If Telegram delivery fails → email is sent regardless (fallback, not replacement)
- Notifications are logged to DB (`notifications` table) with `sent_at`, `channel`, `status`

**SLA & Reminder Rules:**

| Clock | Action |
|---|---|
| T+0 | L3/L4 classified → immediate Telegram + email alert |
| T+12h | Still unresolved → reminder Telegram + email ("Action still required") |
| T+24h | Still unresolved → final escalation alert to **Julie** ("SLA breached — 24h without response") |
| Any time | Community Manager marks as `not_relevant` or `wont_respond` → all future reminders suppressed |

- "Unresolved" means `resolution_status IS NULL` — i.e. no action taken (not posted, not dismissed, not escalated)
- Once any manual resolution is set, the reminder job skips that mention permanently
- The 12-hour reminder repeats every 12 hours until either the SLA is breached or the mention is resolved — it does not stop after the first reminder

**Reminder message format (Telegram):**
```
⏰ [L3] Reminder — action still required (12h)
TrustPilot: "[first 80 chars]..."
Draft response waiting. Open: http://lighthouse.internal/mention/1234
```

No inline Telegram action buttons — link only. All actions (approve, edit, dismiss, escalate) are taken inside the dashboard after tapping the link.

**Resolution statuses (set by Community Manager in dashboard):**
- `responded` — reply posted (set automatically when Approve & Post is clicked)
- `escalated` — routed to Legal (reminders suppressed; Jira priority updated)
- `not_relevant` — mention does not require a response (e.g. clearly spam, already handled offline)
- `wont_respond` — deliberate decision not to respond publicly

All resolutions require a one-line reason to be typed before confirming — logged to DB for audit purposes.

**Environment variables:**
```
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=            # community manager's chat ID
NOTIFICATION_EMAIL=          # community manager's email
ESCALATION_TELEGRAM_CHAT_ID= # Julie's Telegram chat ID — receives SLA breach alerts
ESCALATION_EMAIL=            # Julie's email — julie.sharova@axi.com
DIGEST_RECIPIENTS=julie.sharova@axi.com  # comma-separated; Julie is always included
WATCH_SPIKE_COUNT=3          # flag if a watch-list term appears in ≥N mentions in 7 days
WATCH_SPIKE_MULTIPLIER=2     # flag if a term doubles week-on-week
SLA_HOURS=24                 # hours before SLA breach alert (default 24)
REMINDER_INTERVAL_HOURS=12   # hours between reminders (default 12)
```

File: `notifications/telegram.py`, `notifications/email.py`, `notifications/dispatcher.py`, `notifications/sla_checker.py`

---

## Component 4b — Human Post Queue (L3 / L4 + Forums)

For mentions where `routing_status = PENDING_HUMAN_POST`.

**Owner: Community Manager.** The community manager is the sole approver for this queue. All drafts land here for their review before anything is published.

- Jira ticket created immediately (see Component 5) and assigned to the community manager
- Response draft is auto-generated by the Response Agent — the community manager reviews, not writes
- Dashboard `/compliance` page shows two sub-queues:
  - **Pending post** — draft ready, awaiting community manager approval to publish
  - **Needs review** — edge cases flagged by the agent (e.g. language detection failed, platform API unavailable)
- Three actions per mention:
  - **Approve & post** — publishes the draft via platform API, updates DB and Jira
  - **Edit & post** — community manager edits the draft before posting
  - **Escalate** — routes to Legal, updates Jira priority, suppresses any response

---

## Component 5 — Jira Integration

**Ticket creation — L3 and L4 only:**

| Tier | Jira status on creation | Priority |
|---|---|---|
| L3 | `PENDING_HUMAN_POST` | High |
| L4 | `PENDING_HUMAN_POST` | Critical |

> L1 and L2 mentions do **not** get Jira tickets. They are tracked in the Lighthouse dashboard only. If a follow-up reply to an L1/L2 auto-response escalates to L3/L4, the new mention gets a Jira ticket at that point.

**Ticket body includes:**
- Mention URL
- Screenshot (linked from `data/screenshots/`)
- Summary
- Raw text (PII-redacted version)
- Classification reasoning (from Julie's pipeline)
- Sentiment + risk tier
- Drafted response text (for `PENDING_HUMAN_POST` mentions)

**Ticket assignment:**
- L3/L4 pending post: assigned to community manager as the action owner

**Response logging to Jira (automatic, fires immediately on post):**

When a response is posted — either auto-posted or approved and posted by the Community Manager — the system immediately adds a comment to the Jira ticket:

```
Response posted by: [Community Manager / Auto-agent]
Platform: TrustPilot
Posted at: 2026-04-30 14:32 UTC
Response URL: https://trustpilot.com/...

Response text:
"[full response text]"
```

Ticket status is also updated automatically:
- `AUTO_RESPONDED` if posted by the agent
- `RESPONDED` if posted by the Community Manager
- `ESCALATED` / `DISMISSED` / `NOT_RELEVANT` if a manual resolution was set without posting

No manual Jira updates required — every action taken in the dashboard is reflected in Jira automatically.

**Jira sync job (runs hourly):**
- Polls Jira API for any status changes made directly in Jira (e.g. Legal moves a ticket)
- Writes current status back to `mentions.jira_status` in PostgreSQL
- Read-only from Jira's perspective — never modifies Jira state
- This keeps the dashboard in sync with any manual Jira changes

File: `jira/client.py`, `jira/sync.py`

---

## Component 6 — Flask Dashboard

**Authentication: Flask-Login with persistent sessions.**

Replaces HTTP Basic Auth (which prompts every browser session). Users log in once via a `/login` form and stay logged in across sessions via a long-lived remember-me cookie.

- Login page: `/login` — username + password form, "Remember me" checkbox ticked by default
- Session persists for 30 days (configurable via `SESSION_LIFETIME_DAYS`)
- All other routes redirect to `/login` if not authenticated
- Logout: `/logout` — clears the session cookie
- Credentials still stored in `.env` (`DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD`) — no database user table needed for a single-user setup
- Cookie is `HttpOnly` and `Secure` (HTTPS only); `SameSite=Lax`

**Public deployment requirements (dashboard is internet-facing):**
- **HTTPS mandatory** — serve behind a reverse proxy (nginx or Caddy) with a valid TLS certificate (Let's Encrypt). Never expose Flask directly on port 80/443.
- **Strong credentials** — `DASHBOARD_PASSWORD` must be at least 20 characters, randomly generated. Not stored in plaintext anywhere other than `.env`.
- **Login rate limiting** — max 5 failed attempts per IP per 10 minutes before a 10-minute lockout. Implemented via `Flask-Limiter`.
- **`SECRET_KEY`** — minimum 32 random bytes, generated once and stored in `.env`. Never committed to git.
- **No sensitive data in URLs** — mention IDs are integers, no tokens or PII in query strings.

```
SESSION_LIFETIME_DAYS=30     # how long the remember-me cookie lasts
SECRET_KEY=                  # min 32 random bytes — generate with: python -c "import secrets; print(secrets.token_hex(32))"
DASHBOARD_URL=               # public URL e.g. https://lighthouse.axi.com — used in Telegram alert links
LOGIN_MAX_ATTEMPTS=5         # failed logins before lockout
LOGIN_LOCKOUT_MINUTES=10
```

| Route | Purpose |
|---|---|
| `/` | Overview — mention counts by tier, platform, routing status, watch list spike summary, classification error count |
| `/mentions` | Full filterable mention list (filter by platform, tier, status, date) |
| `/mention/<id>` | Detail view — screenshot, raw text, summary, classification, Jira ticket link |
| `/compliance` | L3/L4 queue — approve / escalate / dismiss controls |
| `/watchlist` | All mentions that matched at least one watch-list term — see below |
| `/errors` | All mentions where classification failed — error message, raw text, retry button |
| `/tickets` | All Jira tickets and current sync'd status |
| `/runs` | Crawler run history with mention counts and errors |

**Watch List view (`/watchlist`):**

- Shows all mentions where `watch_flags IS NOT NULL`, newest first
- Filter bar across the top: one button per watch term (FCA, CySEC, ASIC, DFSA, Pepperstone, FxPro, CMC Markets, Capital.com, withdrawal, spread, leverage, KYC, margin call, scam, fraud, compensation, investigation) — click to filter to that term only
- Each mention row shows: matched terms (as badges), platform, tier, sentiment, engagement, snippet, date
- Week-on-week count per term shown at the top of the page — terms spiking above threshold highlighted in red
- Exportable to CSV from this view

**Overview dashboard watch list panel (`/`):**

A compact panel on the main dashboard showing this week's watch list at a glance — visible the moment you log in:

- One row per watch-list term that has at least one mention this week
- Columns: term | this week | last week | trend (↑ ↓ —) | highest tier hit
- Terms spiking above threshold shown in red; stable terms in grey; terms with no mentions this week hidden
- "View all →" link goes to `/watchlist` filtered to that term
- Terms with zero mentions all week are collapsed into a "X terms quiet this week" line at the bottom

**Overview dashboard error panel (`/`):**
- Count of mentions currently in `classification_status = error`
- If count > 0: shown in red with "View errors →" link to `/errors`
- If count = 0: shown in green "All mentions classified"
- Retry button on each `/errors` row — resets `classification_status = NULL` and `classified_at = NULL` so the 60-second poll picks it up again automatically

**Mobile-friendly:** all dashboard views must be fully usable on a phone. The Community Manager receives a Telegram alert and should be able to open the dashboard link, review the draft, and tap Approve & Post without needing a desktop. Priority views for mobile: `/compliance` (approve/post queue), `/mention/<id>` (detail + action buttons), `/` (overview + watch list panel). Layout: single-column on mobile, responsive grid on desktop. Touch targets minimum 44px. No horizontal scrolling.

File: `app.py`, `templates/`, `static/`

---

## Component 7 — Scheduler

APScheduler running in-process within the Flask app.

| Job | Cadence | What it does |
|---|---|---|
| Crawler + enrichment | Every 30 minutes | Triggers Som's crawlers across all platforms; new mentions written to DB immediately |
| Classification | Continuous | Julie's pipeline polls for unclassified mentions every 60 seconds; classifies and routes each one as it arrives — no batching |
| Response agent | Continuous | Polls for `PENDING_AUTO_RESPOND` mentions every 60 seconds; posts replies as they are classified |
| Notifications | Event-driven | Fires immediately when classification writes L3 or L4 — no polling delay |
| SLA checker | Every 12 hours | Finds unresolved L3/L4 mentions; sends reminders at 12h intervals; sets `sla_breached = True` and fires escalation alert at 24h |
| Thread monitor | Daily | Checks for new replies on all AUTO_RESPONDED threads |
| Jira sync | Hourly | Syncs Jira ticket statuses to local DB |
| Weekly digest email | Monday 08:00 | Weekly summary to Julie + `DIGEST_RECIPIENTS` — what Axi responded to, what was left unanswered, what's trending |

File: `scheduler.py`

---

## Component 8 — Weekly Digest

Sent every Monday at 08:00 to Julie (julie.sharova@axi.com) + `DIGEST_RECIPIENTS`.

**Digest sections (in order):**

**1. What Axi responded to this week**
- All mentions where `resolution_status = responded` in the past 7 days
- Grouped by platform, sorted by tier (L4 → L3 → L2 → L1)
- Shows: platform, tier, snippet, response posted, engagement count

**2. What was left unanswered**
- All L3/L4 mentions still `PENDING_HUMAN_POST` or with `sla_breached = True`
- Flagged clearly — these are the open risks heading into the new week
- Includes time open and whether an SLA breach occurred

**3. What's trending**
- Top 5 platforms by mention volume this week vs. last week
- Top 5 mentions by engagement (regardless of tier)
- Any platform showing a significant spike (>50% increase week-on-week)
- Sentiment breakdown: % positive / negative / neutral across all mentions

**Watch list — flagged automatically if appearing in mentions alongside Axi:**

| Category | Terms to watch |
|---|---|
| Regulators | FCA, CySEC, ASIC, DFSA |
| Competitors | Pepperstone, FxPro, CMC Markets, Capital.com |
| Topics | withdrawal, spread, leverage, KYC, margin call, scam, fraud, compensation, investigation |

Any mention containing a watch-list term is highlighted in the trending section with a count for the week. A spike is flagged if a term appears in >3 mentions in 7 days or doubles week-on-week. These thresholds are configurable via env vars (`WATCH_SPIKE_COUNT=3`, `WATCH_SPIKE_MULTIPLIER=2`).

**4. Numbers at a glance**
- Total mentions this week
- L4 / L3 / L2 / L1 counts
- Total positive reviews | Total negative reviews | Total neutral
- Responded vs. unanswered vs. dismissed
- SLA breaches

Format: HTML email, same dark-themed styling as Lighthouse v0.01 digest. Built by Claude from the weekly DB query — not a static template.

File: `digest/builder.py`, `digest/sender.py`, `prompts/digest_summary.txt`

---

## Data Model (Timur's additions to mentions table)

```
mentions
  -- existing fields from Som + Julie --
  response_text           str | None
  response_posted_at      datetime | None
  response_url            str | None
  thread_id               str | None       (platform-specific thread/post ID for thread monitoring)
  jira_ticket_id          str | None       (only set for L3/L4)
  jira_status             str | None       (only set for L3/L4)
  resolution_status       str | None    ("responded" / "escalated" / "not_relevant" / "wont_respond")
  resolution_reason       str | None    (one-line reason, required before any resolution is saved)
  resolved_at             datetime | None
  sla_breached            bool          (set True when 24h passes without resolution)
  updated_at              datetime

response_templates
  id                      UUID, primary key
  platform                str
  sentiment               str
  category                str              ← value provided by Som/Julie upstream
  template_text           str

notifications
  id                      UUID, primary key
  mention_id              int (FK → mentions)
  channel                 str              ("telegram" / "email")
  sent_at                 datetime
  status                  str              ("sent" / "failed")
  error                   str | None
```

---

## Build Checklist

### Phase 4 — Response & Escalation
- [ ] `prompts/response_personalise.txt` — Claude personalisation prompt enforcing Axi brand voice (polite, corporate, solution-oriented, no fault admissions)
- [ ] `response/templates.py` — seed `response_templates` table with initial templates (5 categories × platforms)
- [ ] `response/agent.py` — select template, Claude personalisation call (respects `detected_language`), route to auto-post or human queue
- [ ] `response/poster.py` — per-platform posting (Reddit, X, Meta, TrustPilot); flag app-store mentions as manual
- [ ] Human post queue: draft saved to DB, surfaced in `/compliance` with Approve & Post / Edit & Post / Escalate controls
- [ ] `notifications/telegram.py` — Telegram Bot API, send formatted L3/L4 alert
- [ ] `notifications/email.py` — SMTP alert, same trigger
- [ ] `notifications/dispatcher.py` — called by classification pipeline on L3/L4 write; Telegram first, email as fallback; log to `notifications` table
- [ ] `notifications/sla_checker.py` — runs every 12h; finds unresolved L3/L4 (`resolution_status IS NULL`); sends reminder; sets `sla_breached = True` and fires escalation alert at 24h
- [ ] Dashboard resolution controls: Not Relevant / Won't Respond / Escalate buttons — require one-line reason before saving; sets `resolution_status`, `resolution_reason`, `resolved_at`
- [ ] Add `resolution_status`, `resolution_reason`, `resolved_at`, `sla_breached` columns to DB schema

### Phase 5 — Jira Integration
- [ ] `jira/client.py` — Jira Cloud REST API v3, ticket creation with all required fields
- [ ] `jira/client.py` — `add_response_comment()` — posts response text + metadata as a Jira comment immediately when a response is published; updates ticket status automatically
- [ ] `jira/sync.py` — hourly poll, write status back to `mentions.jira_status`
- [ ] Add `jira_ticket_id`, `jira_status`, `updated_at` columns to DB schema

### Phase 6 — Dashboard
- [ ] `app.py` — Flask app, Flask-Login setup, persistent session cookie (30-day remember-me), Flask-Limiter on `/login` (5 attempts / 10 min lockout)
- [ ] `templates/login.html` — login form with remember-me checkbox ticked by default
- [ ] nginx/Caddy config — reverse proxy with TLS termination, HTTPS enforced, HTTP → HTTPS redirect
- [ ] `templates/base.html` — shared responsive layout (Bootstrap 5 or equivalent), mobile-first, no horizontal scrolling
- [ ] `templates/index.html` — overview stats including watch list spike panel (see below)
- [ ] `templates/mentions.html` — filterable mention list
- [ ] `templates/mention_detail.html` — single mention with screenshot + classification
- [ ] `templates/compliance.html` — L3/L4 queue with action controls
- [ ] `templates/watchlist.html` — watch-list view with term filter buttons, spike indicators, CSV export
- [ ] `templates/errors.html` — failed classifications list with error message, raw text snippet, and Retry button (requeues mention for classification)
- [ ] `templates/tickets.html` — Jira ticket list
- [ ] `templates/runs.html` — crawler run history

### Phase 6b — Weekly Digest
- [ ] `digest/builder.py` — query DB for past 7 days, build four sections: responded / unanswered / trending / numbers
- [ ] `prompts/digest_summary.txt` — Claude prompt for the trending narrative section
- [ ] `digest/sender.py` — SMTP send to `DIGEST_RECIPIENTS`; HTML email matching Lighthouse dark theme

### Phase 7 — Scheduler + Hardening
- [ ] `scheduler.py` — APScheduler setup, all jobs wired
- [ ] Rotate default credentials before sharing dashboard access
- [ ] Confirm compliance PII sign-off before enabling live mode
- [ ] End-to-end test: trigger full pipeline manually, confirm mention flows from crawl → classify → reply/queue → Jira → dashboard

---

## Environment Variables (Timur's section)

```
# Dashboard auth
DASHBOARD_USERNAME=
DASHBOARD_PASSWORD=
SESSION_LIFETIME_DAYS=30
SECRET_KEY=               # min 32 random bytes — generate with: python -c "import secrets; print(secrets.token_hex(32))"
DASHBOARD_URL=            # public URL e.g. https://lighthouse.axi.com — used in Telegram alert links
LOGIN_MAX_ATTEMPTS=5
LOGIN_LOCKOUT_MINUTES=10

# Jira (L3/L4 only)
JIRA_BASE_URL=            # e.g. https://yourcompany.atlassian.net
JIRA_EMAIL=
JIRA_API_TOKEN=
JIRA_PROJECT_KEY=         # e.g. CX or LGL

# Notifications (Telegram + email)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=                  # community manager's chat ID
NOTIFICATION_EMAIL=                # community manager's email
ESCALATION_TELEGRAM_CHAT_ID=       # Julie's Telegram chat ID — receives SLA breach alerts
ESCALATION_EMAIL=julie.sharova@axi.com
DIGEST_RECIPIENTS=julie.sharova@axi.com  # comma-separated
SLA_HOURS=24
REMINDER_INTERVAL_HOURS=12
WATCH_SPIKE_COUNT=3
WATCH_SPIKE_MULTIPLIER=2

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/lighthouse

# Anthropic (for response personalisation and compliance draft)
ANTHROPIC_API_KEY=
```

---

## Verification

- Post a test L1 mention in English — confirm auto-reply is in English
- Post a test mention in Arabic and one in Spanish — confirm responses are in the same language as the mention, not English
- Post a test L1 mention to a sandbox Reddit account — confirm auto-reply is posted and DB updated
- Create a test L3 mention — confirm Telegram message arrives within 30 seconds of classification, Jira ticket created, draft response in dashboard
- Create a test L4 mention — confirm both Telegram and email fire; confirm Jira priority is Critical
- Disable Telegram bot token temporarily — confirm email fallback fires for an L3 mention
- Set `REMINDER_INTERVAL_HOURS=1` and `SLA_HOURS=2` in test env — create an L3 mention, confirm reminder fires at 1h and SLA breach alert fires at 2h
- Mark a mention as `not_relevant` before the 12h reminder — confirm reminder job skips it
- Confirm `resolution_reason` is required — dashboard must reject saving a resolution with an empty reason field
- Post a test response via the dashboard — confirm Jira ticket receives a comment within 10 seconds containing the response text, platform, timestamp, and response URL
- Set a mention to `not_relevant` — confirm Jira ticket status updates to `NOT_RELEVANT` automatically
- Trigger Jira sync after manually moving a ticket in Jira — confirm `jira_status` in DB updates
- Open dashboard — confirm all routes load, compliance queue shows L3/L4 only, ticket list is accurate
- Trigger full pipeline via scheduler manually — confirm all jobs fire in correct order
