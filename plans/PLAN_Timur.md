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
  "category": "withdrawal_complaint",
  "sentiment": "negative",
  "sentiment_reasoning": "Post expresses clear frustration about a delayed withdrawal process.",
  "risk_level": "L3",
  "risk_reasoning": "Withdrawal complaint with regulatory implication. User mentions escalating to a financial regulator if unresolved.",
  "routing_status": "PENDING_HUMAN_REVIEW",
  "classified_at": "2026-04-30T08:15:32Z",
  "thread_id": "t3_abc123"
}
```

**Key fields Timur's layer consumes:**

| Field | Who sets it | Used for |
|---|---|---|
| `platform` | Som | Selects posting method + template |
| `category` | Som / Julie (TBC) | Selects response template |
| `sentiment` | Julie Stage 1 | Selects response template |
| `risk_level` | Julie Stage 2 | Routes to auto-reply vs compliance queue |
| `routing_status` | Julie | Entry condition for all of Timur's jobs |
| `summary` | Som enrichment | Shown in dashboard + Slack alert + Jira ticket |
| `screenshot_path` | Som enrichment | Shown in dashboard + Jira ticket |
| `thread_id` | Som | Used by thread monitor to poll for replies |
| `raw_text` | Som | Passed to Claude for response personalisation |

> `category` allowed values (proposed — confirm with Som/Julie): `withdrawal_complaint` · `kyc_issue` · `general_complaint` · `positive_review` · `platform_feedback` · `regulatory_mention`

---

## Orchestration Flow

```
PostgreSQL mentions table
         │
         │  Poll for routing_status IN
         │  ('PENDING_RESPONSE', 'PENDING_HUMAN_REVIEW')
         │
         ▼
┌─────────────────────┐
│   Scheduler (daily) │
│   orchestrator.py   │
└──────────┬──────────┘
           │
           ├─── risk_level IN (L1, L2) ────────────────────────────────────┐
           │    routing_status = PENDING_RESPONSE                           │
           │                                                                ▼
           │                                               ┌───────────────────────────┐
           │                                               │     Response Agent (4a)   │
           │                                               │                           │
           │                                               │  1. Lock: set status      │
           │                                               │     RESPONDING             │
           │                                               │  2. Lookup template       │
           │                                               │     (platform+sentiment   │
           │                                               │      +category)           │
           │                                               │  3. Claude personalise    │
           │                                               │  4. Post via platform API │
           │                                               │  5. Update DB:            │
           │                                               │     AUTO_RESPONDED        │
           │                                               │     + response_url        │
           │                                               └───────────────────────────┘
           │                                                          │
           │                                                          │ Daily
           │                                                          ▼
           │                                               ┌───────────────────────────┐
           │                                               │   Thread Monitor (4a)     │
           │                                               │                           │
           │                                               │  Poll platform for new    │
           │                                               │  replies on thread_id     │
           │                                               │                           │
           │                                               │  New reply found?         │
           │                                               │  → New mention record     │
           │                                               │  → Julie classifies it    │
           │                                               │  → If L3/L4: enters       │
           │                                               │    compliance path ───────┼──┐
           │                                               └───────────────────────────┘  │
           │                                                                              │
           └─── risk_level IN (L3, L4) ────────────────────────────────────┐             │
                routing_status = PENDING_HUMAN_REVIEW                       │             │
                                                                            ▼             ▼
                                                           ┌───────────────────────────────────┐
                                                           │      Compliance Path (4b)         │
                                                           │                                   │
                                                           │  1. Create Jira ticket            │
                                                           │     (L3=High, L4=Critical)        │
                                                           │  2. Send Slack/Teams alert        │
                                                           │     with summary + dashboard link │
                                                           │  3. Surface in /compliance queue  │
                                                           │                                   │
                                                           │  Human actions:                   │
                                                           │  ┌──────────────────────────┐     │
                                                           │  │ Draft Response           │     │
                                                           │  │ Claude generates text    │     │
                                                           │  │ Human copies + posts     │     │
                                                           │  └──────────────────────────┘     │
                                                           │  ┌──────────────────────────┐     │
                                                           │  │ Escalate                 │     │
                                                           │  │ Jira priority → Critical │     │
                                                           │  │ 2nd Slack alert          │     │
                                                           │  └──────────────────────────┘     │
                                                           │  ┌──────────────────────────┐     │
                                                           │  │ Dismiss                  │     │
                                                           │  │ Jira closed              │     │
                                                           │  │ Removed from queue       │     │
                                                           │  └──────────────────────────┘     │
                                                           └───────────────────────────────────┘
                                                                            │
                                                                            │ Hourly
                                                                            ▼
                                                           ┌───────────────────────────────────┐
                                                           │       Jira Sync (5)               │
                                                           │                                   │
                                                           │  Poll Jira for ticket status      │
                                                           │  Write back to mentions.jira_status│
                                                           │  READ-ONLY — never modifies Jira  │
                                                           └───────────────────────────────────┘
```

---

## Template Selection Logic

```
mention.platform  +  mention.sentiment  +  mention.category
         │                   │                     │
         └───────────────────┴─────────────────────┘
                             │
                             ▼
              SELECT template_text FROM response_templates
              WHERE platform = ? AND sentiment = ? AND category = ?
                             │
                    ┌────────┴────────┐
                    │                 │
                 FOUND            NOT FOUND
                    │                 │
                    ▼                 ▼
            Claude call:       Flag mention as
            personalise        REPLY_FAILED
            opening 1-2        Surface on dashboard
            sentences          Do NOT skip silently
                    │
                    ▼
            Final response =
            personalised_opening + template_body
```

**Proposed template matrix** (cells = template exists / needs writing):

| Category | Positive | Negative | Neutral |
|---|---|---|---|
| positive_review | ✅ thank you + brand | — | — |
| general_complaint | — | ✅ ack + support link | ✅ ack + support link |
| withdrawal_complaint | — | ✅ ack + resolution path | ✅ ack + resolution path |
| kyc_issue | — | ✅ ack + KYC support | — |
| platform_feedback | ✅ thank you | ✅ ack + roadmap note | — |
| regulatory_mention | — | ❌ L3/L4 — compliance only | — |

All templates need to be written and approved before Phase 4 implementation begins.

---

## Component 4a — Response Agent (L1 / L2)

For mentions where `routing_status = PENDING_RESPONSE`.

**Flow:**
1. Read mention from DB (platform, raw_text, summary, sentiment, risk_level, **category**)
2. Select the correct response template from `response_templates` table based on platform + sentiment + category
3. Claude call — personalise the opening 1–2 sentences of the template to the specific mention
4. Post the reply via the platform's API
5. Update DB: set `response_text`, `response_posted_at`, `response_url`, `routing_status = AUTO_RESPONDED`

> **Note on `category` field:** Category is assigned upstream — by Som's enrichment layer or Julie's classification pipeline — and arrives as a pre-populated field. Timur's response agent consumes it but does not determine it. Coordinate with Som and Julie to confirm the field name, allowed values, and which stage sets it.

**Template categories (to be written before Phase 4 ships):**

| Category | Trigger | Template purpose |
|---|---|---|
| Positive review | sentiment = positive | Thank you + brand reinforcement |
| General complaint L1 | risk_level = L1, negative | Acknowledgement + support link |
| Minor product complaint L2 | risk_level = L2, negative | Acknowledgement + resolution path |

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

## Component 4b — Compliance Queue (L3 / L4)

For mentions where `routing_status = PENDING_HUMAN_REVIEW`.

- Jira ticket created immediately (see Component 5)
- Slack/Teams alert sent immediately (see Component 4c)
- No automated response posted — ever
- Dashboard `/compliance` page shows the queue with three actions:
  - **Draft response** — system generates a draft reply using the appropriate template + Claude personalisation. Dashboard displays the draft text for the human to copy-paste and post manually on the platform. The system does **not** post on behalf of the human.
  - **Escalate** — routes to Legal, updates Jira priority, sends a second Slack/Teams alert
  - **Dismiss** — marks as not actionable, closes Jira ticket, removed from compliance queue

---

## Component 4c — Slack / Teams Alert (L3 / L4)

Triggered immediately when a mention is classified L3 or L4.

- Send a message to a configured Slack channel or Teams webhook
- Message includes: platform, risk tier, mention URL, one-line summary, link to dashboard compliance page
- Second alert sent if a mention is **escalated** from L3 to L4 by a human in the dashboard
- Config: support both Slack (incoming webhook URL) and Teams (webhook URL) — one is active at a time, set via `.env`

File: `notifications/slack.py` or `notifications/teams.py`

---

## Component 5 — Jira Integration

**Ticket creation — L3 and L4 only:**

| Tier | Jira status on creation | Priority |
|---|---|---|
| L3 | `PENDING_HUMAN_REVIEW` | High |
| L4 | `PENDING_HUMAN_REVIEW` | Critical |

> L1 and L2 mentions do **not** get Jira tickets. They are tracked in the Lighthouse dashboard only. If a follow-up reply to an L1/L2 auto-response escalates to L3/L4, the new mention gets a Jira ticket at that point.

**Ticket body includes:**
- Mention URL
- Screenshot (linked from `data/screenshots/`)
- Summary
- Raw text (PII-redacted version)
- Classification reasoning (from Julie's pipeline)
- Sentiment + risk tier + category

**Jira sync job (runs hourly):**
- Polls Jira API for updated ticket statuses
- Writes current status back to `mentions.jira_status` in PostgreSQL
- Read-only from Jira's perspective — never modifies Jira state
- This keeps the dashboard in sync without relying on Jira webhooks

File: `jira/client.py`, `jira/sync.py`

---

## Component 6 — Flask Dashboard

HTTP basic auth on all routes. Credentials from `.env`.

| Route | Purpose |
|---|---|
| `/` | Overview — mention counts by tier, platform, routing status |
| `/mentions` | Full filterable mention list (filter by platform, tier, status, date) |
| `/mention/<id>` | Detail view — screenshot, raw text, summary, classification, Jira ticket link |
| `/compliance` | L3/L4 queue — approve / escalate / dismiss controls |
| `/tickets` | All Jira tickets and current sync'd status |
| `/runs` | Crawler run history with mention counts and errors |

File: `app.py`, `templates/`, `static/`

---

## Component 7 — Scheduler

APScheduler running in-process within the Flask app.

| Job | Cadence | What it does |
|---|---|---|
| Crawler + enrichment | Daily | Triggers Som's crawlers across all platforms |
| Classification | Daily (after crawl) | Triggers Julie's pipeline on all unclassified mentions |
| Response agent | Daily (after classify) | Posts L1/L2 replies |
| Thread monitor | Daily | Checks for new replies on all AUTO_RESPONDED threads |
| Jira sync | Hourly | Syncs Jira ticket statuses to local DB |
| Weekly digest email | Monday 08:00 | Summary email to stakeholders (future phase) |

File: `scheduler.py`

---

## Data Model (Timur's additions to mentions table)

```
mentions
  -- existing fields from Som + Julie --
  response_text           str | None
  response_posted_at      datetime | None
  response_url            str | None
  thread_id               str | None       ← platform-specific thread/post ID for thread monitoring
  jira_ticket_id          str | None       ← only set for L3/L4
  jira_status             str | None       ← only set for L3/L4
  slack_alert_sent        bool             ← only true for L3/L4
  updated_at              datetime

response_templates
  id                      UUID, primary key
  platform                str
  sentiment               str
  category                str              ← value provided by Som/Julie upstream
  template_text           str
```

---

## Planning Checklist

### Design Decisions to Confirm
- [ ] **Response template ownership** — who writes the actual template text? Timur builds the system, but the brand voice needs to come from someone with authority on Axi comms tone. Confirm who approves templates before they go live.
- [ ] **Auto-posting risk** — L1/L2 auto-reply posts publicly on behalf of Axi with no human approval. Confirm this is accepted by stakeholders. One misclassification posting the wrong template is a brand risk.
- [ ] **TrustPilot owner reply** — TrustPilot owner replies require a logged-in business account. Confirm Axi has one and credentials are obtainable. Playwright posting a TrustPilot reply is fragile.
- [ ] **Jira project key** — which project handles CX mentions? Which handles Legal/regulatory? Confirm with the Jira admin.
- [ ] **Jira ticket assignee** — who gets assigned L3 tickets? Who gets L4? Is this a fixed person or a team queue?
- [ ] **Compliance queue actions** — "Approve response" on an L3 means a human posts manually. What platform? What account? Does the dashboard just show the drafted text, or does it also handle posting?
- [ ] **Screenshot storage** — local disk won't scale and won't survive a server restart. Confirm cloud storage (S3 or GCS) is available, or document that local disk is acceptable for v1.
- [ ] **Dashboard access** — who gets access? Internal only? Does it need to be reachable externally (requires proper hosting, not just localhost)?

### Edge Cases to Resolve
- [ ] **Auto-reply to a deleted mention** — by the time the response agent runs, the original post was deleted. Posting a reply fails. What happens? Mark as `REPLY_FAILED`? Retry? Create Jira ticket anyway?
- [ ] **Platform API rejects the reply** — rate limit hit, or account flagged for automated activity. How do we detect, log, and surface this failure?
- [ ] **Same mention replied to twice** — pipeline runs, posts reply, but `routing_status` update fails. Next run picks up the same mention again and posts a second reply. Idempotency: set `routing_status = RESPONDING` (in-progress lock) before the post attempt, only move to `AUTO_RESPONDED` on success.
- [ ] **L3 compliance queue: dismiss then reappear** — a mention is dismissed, but the same complaint is reposted by the same user. New mention or same one? Does dismiss carry over?
- [ ] **Jira ticket creation fails** — Jira is down or auth expires. The mention is classified L3 but no ticket is created. It sits in `PENDING_HUMAN_REVIEW` indefinitely with no Jira reference. How do we detect and retry?
- [ ] **Jira sync conflicts** — human closes a ticket in Jira, but our sync overwrites it. Sync is read-only from Jira: it updates local DB from Jira state, never the other way.
- [ ] **Dashboard screenshot missing** — screenshot failed during enrichment. Mention detail page must show a placeholder, not a broken image.
- [ ] **Response template has no match** — mention arrives with a platform + sentiment + category combo that has no template. Response agent must not silently skip — flag as `REPLY_FAILED` and surface on dashboard.
- [ ] **Scheduler overlap** — daily crawl takes longer than 24 hours. Next crawl fires before previous finishes. APScheduler `max_instances=1` per job prevents overlap; second trigger is skipped and logged.
- [ ] **App store and forum mentions (manual response required)** — these pile up with no notification. Need a dedicated dashboard badge or count on the `/mentions` page filtered by `routing_status = MANUAL_RESPONSE_NEEDED`.
- [ ] **Multiple mentions from same author on same platform** — coordinated complaint by one person. Responding to all with the same template looks spammy. Define per-author reply rate limit (e.g. max 1 auto-reply per author per platform per 7 days).
- [ ] **Thread monitor: platform doesn't expose reply thread** — some platforms (TrustPilot, app stores) don't have a reply-thread API. Thread monitoring is only possible on platforms where replies are accessible. Document which platforms support it.
- [ ] **Slack/Teams webhook failure** — alert not delivered when L3/L4 is created. Mark `slack_alert_sent = false`, retry on next Jira sync cycle. Dashboard must visually flag mentions where alert delivery failed.

### Logic to Validate
- [ ] Walk through the full auto-reply flow on paper: a mention arrives as `PENDING_RESPONSE` → template selected → Claude call → post → DB update. At what point is `routing_status` updated? Before or after posting? (If after, and posting succeeds but DB write fails, we post twice.)
- [ ] Walk through the full compliance flow: L3 mention arrives → Jira ticket created → `PENDING_HUMAN_REVIEW` set → human dismisses in dashboard → what exact DB and Jira state results?
- [ ] Confirm the scheduler job order is strictly: crawl → classify → respond. If classify hasn't finished, the respond job must not run.
- [ ] Confirm Jira sync is read-only from Jira's perspective — it must never modify Jira state, only read it.
- [ ] Confirm that the dashboard compliance queue shows only L3/L4 and never surfaces an L1/L2 that was auto-responded.

---

## Environment Variables (Timur's section)

```
# Dashboard auth
DASHBOARD_USERNAME=
DASHBOARD_PASSWORD=

# Jira (L3/L4 only)
JIRA_BASE_URL=            # e.g. https://yourcompany.atlassian.net
JIRA_EMAIL=
JIRA_API_TOKEN=
JIRA_PROJECT_KEY=         # e.g. CX or LGL

# Slack / Teams alert (set one, leave the other blank)
SLACK_WEBHOOK_URL=
TEAMS_WEBHOOK_URL=

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/lighthouse

# Anthropic (for response personalisation and compliance draft)
ANTHROPIC_API_KEY=
```

---

## Pre-Implementation Sign-Off

Before Timur moves to implementation, the following must be resolved:

- [ ] Auto-posting approval confirmed by stakeholders — brand risk decision, not a technical one
- [ ] Response template text written and approved (at minimum one per category before Phase 4 starts)
- [ ] Jira project key(s) and assignee rules confirmed with Jira admin
- [ ] TrustPilot business account credentials confirmed as obtainable
- [ ] Screenshot storage location agreed with Som (impacts enrichment output and DB path field)
- [ ] `category` field name, allowed values, and which stage sets it confirmed with Som and Julie
- [ ] Slack or Teams confirmed — which one does Axi use? Webhook URL obtainable?
- [ ] Per-author auto-reply rate limit value agreed (proposed: 1 reply per author per platform per 7 days)
- [ ] Which platforms support thread monitoring confirmed with Som (depends on crawler API access)
- [ ] Scheduler job ordering and overlap prevention strategy agreed with Som and Julie
- [ ] Dashboard hosting decision made: localhost only, or externally reachable?
