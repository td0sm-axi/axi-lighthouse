import os
import json
import base64
import datetime
from pathlib import Path

import requests

JIRA_MODE = os.environ.get("JIRA_MODE", "mock")
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
JIRA_PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "APM")
JIRA_COMMUNITY_MANAGER_ACCOUNT_ID = os.environ.get("JIRA_COMMUNITY_MANAGER_ACCOUNT_ID", "")

MOCK_PAYLOAD_DIR = Path("service/jira_payloads")

# Transition IDs confirmed against axitrader.atlassian.net project APM
TRANSITION_MAP = {
    "responded":    "41",  # Done
    "not_relevant": "41",  # Done
    "wont_respond": "41",  # Done
    "escalated":    "51",  # Shareholder dependence
    "in_progress":  "31",  # In Progress
}

PRIORITY_MAP = {
    "L3": "High",
    "L4": "Critical",
}

_mock_counter = [0]


def _auth_headers():
    token = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _next_mock_id():
    _mock_counter[0] += 1
    return f"DEMO-{_mock_counter[0]:03d}"


def _t(content, bold=False):
    node = {"type": "text", "text": str(content)}
    if bold:
        node["marks"] = [{"type": "strong"}]
    return node


def _para(*children):
    return {"type": "paragraph", "content": list(children)}


def _heading(level, label):
    return {"type": "heading", "attrs": {"level": level}, "content": [_t(label)]}


def _blockquote(body_text):
    return {"type": "blockquote", "content": [_para(_t(body_text))]}


def _build_description(mention: dict) -> dict:
    raw = mention.get("raw_text_redacted") or mention.get("raw_text", "")
    response_text = mention.get("response_text") or ""
    watch = mention.get("watch_flags") or "—"
    dashboard_url = os.environ.get("DASHBOARD_URL", "http://localhost:5000")

    content = [
        _heading(2, "Mention Details"),
        _para(_t("Platform: ", bold=True),    _t(mention.get("platform", ""))),
        _para(_t("Author: ", bold=True),       _t(mention.get("author", ""))),
        _para(_t("Posted at: ", bold=True),    _t(mention.get("posted_at", ""))),
        _para(_t("Engagement: ", bold=True),   _t(mention.get("engagement", 0))),
        _para(_t("URL: ", bold=True),          _t(mention.get("url", ""))),
        {"type": "rule"},
        _heading(2, "Summary"),
        _para(_t(mention.get("summary", ""))),
        _heading(2, "Mention Text (PII-redacted)"),
        _blockquote(raw),
        {"type": "rule"},
        _heading(2, "Classification"),
        _para(_t("Sentiment: ", bold=True),          _t(mention.get("sentiment", ""))),
        _para(_t("Sentiment reasoning: ", bold=True), _t(mention.get("sentiment_reasoning", ""))),
        _para(_t("Risk tier: ", bold=True),           _t(mention.get("risk_level", ""))),
        _para(_t("Risk reasoning: ", bold=True),      _t(mention.get("risk_reasoning", ""))),
        _para(_t("Watch flags: ", bold=True),         _t(watch)),
        _para(_t("Client info detected: ", bold=True),
              _t("Yes" if mention.get("has_client_info") else "No")),
    ]

    if response_text:
        content += [
            {"type": "rule"},
            _heading(2, "Drafted Response (pending Community Manager approval)"),
            _blockquote(response_text),
        ]

    content.append(
        _para(_t("Lighthouse: ", bold=True),
              _t(f"{dashboard_url}/mention/{mention.get('id', '')}"))
    )

    return {"type": "doc", "version": 1, "content": content}


def create_ticket(mention: dict) -> str:
    """Create a Jira ticket for an L3/L4 mention. Returns the ticket key (e.g. APM-73)."""
    risk_level = mention.get("risk_level", "L3")
    platform = mention.get("platform", "unknown").capitalize()
    author = mention.get("author", "unknown")
    summary_snippet = (mention.get("summary") or "")[:80]

    payload = {
        "fields": {
            "project":     {"key": JIRA_PROJECT_KEY},
            "summary":     f"[{risk_level}] {platform} — {summary_snippet} — {author}",
            "issuetype":   {"name": "Task"},
            "priority":    {"name": PRIORITY_MAP.get(risk_level, "High")},
            "labels":      ["lighthouse", risk_level.lower(), mention.get("platform", "").lower()],
            "description": _build_description(mention),
        }
    }

    if JIRA_COMMUNITY_MANAGER_ACCOUNT_ID:
        payload["fields"]["assignee"] = {"accountId": JIRA_COMMUNITY_MANAGER_ACCOUNT_ID}

    if JIRA_MODE == "mock":
        ticket_id = _next_mock_id()
        _write_mock(f"{mention.get('id', ticket_id)}_create.json",
                    {"ticket_id": ticket_id, "payload": payload})
        return ticket_id

    resp = requests.post(
        f"{JIRA_BASE_URL}/rest/api/3/issue",
        headers=_auth_headers(),
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["key"]


def add_response_comment(ticket_id: str, mention: dict, posted_by: str = "Auto-agent") -> None:
    """Post a comment to the Jira ticket when a response is published."""
    posted_at = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    response_url = mention.get("response_url") or "—"

    body = {
        "type": "doc",
        "version": 1,
        "content": [
            _heading(3, "Response Posted"),
            _para(_t("Posted by: ", bold=True),  _t(posted_by)),
            _para(_t("Platform: ", bold=True),   _t(mention.get("platform", "").capitalize())),
            _para(_t("Posted at: ", bold=True),  _t(posted_at)),
            _para(_t("Response URL: ", bold=True), _t(response_url)),
            {"type": "rule"},
            _heading(3, "Response Text"),
            _blockquote(mention.get("response_text") or ""),
        ]
    }

    if JIRA_MODE == "mock":
        _write_mock(f"{ticket_id}_comment.json", {"ticket_id": ticket_id, "body": body})
        return

    resp = requests.post(
        f"{JIRA_BASE_URL}/rest/api/3/issue/{ticket_id}/comment",
        headers=_auth_headers(),
        json={"body": body},
        timeout=10,
    )
    resp.raise_for_status()


def update_ticket_status(ticket_id: str, resolution: str) -> None:
    """Transition a Jira ticket based on the resolution_status set in the dashboard."""
    transition_id = TRANSITION_MAP.get(resolution)
    if not transition_id:
        return

    if JIRA_MODE == "mock":
        _write_mock(f"{ticket_id}_transition.json",
                    {"ticket_id": ticket_id, "resolution": resolution, "transition_id": transition_id})
        return

    resp = requests.post(
        f"{JIRA_BASE_URL}/rest/api/3/issue/{ticket_id}/transitions",
        headers=_auth_headers(),
        json={"transition": {"id": transition_id}},
        timeout=10,
    )
    resp.raise_for_status()


def get_epic_tickets(epic_key: str = None) -> list:
    """Return all Lighthouse tickets under the given epic, newest first.

    Each item: key, tier, platform, description, status, priority, created, jira_url.
    """
    epic_key = epic_key or os.environ.get("JIRA_EPIC_KEY", "APM-75")

    if JIRA_MODE == "mock":
        return _mock_tickets()

    payload = {
        "jql": f"parent = {epic_key} AND labels = lighthouse ORDER BY created DESC",
        "maxResults": 50,
        "fields": ["summary", "status", "priority", "labels", "created"],
    }
    resp = requests.post(
        f"{JIRA_BASE_URL}/rest/api/3/search/jql",
        headers=_auth_headers(),
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    return [_parse_ticket(issue) for issue in resp.json().get("issues", [])]


def _parse_ticket(issue: dict) -> dict:
    key = issue["key"]
    fields = issue["fields"]
    summary = fields.get("summary", "")
    status = fields.get("status", {}).get("name", "")
    priority = fields.get("priority", {}).get("name", "")
    created_raw = fields.get("created", "")

    # Parse "[L3] TrustPilot — description text"
    tier = platform = description = ""
    if summary.startswith("[") and "]" in summary:
        tier = summary[1:summary.index("]")]
        rest = summary[summary.index("]") + 2:]
        if " — " in rest:
            platform, description = rest.split(" — ", 1)
        elif " - " in rest:
            platform, description = rest.split(" - ", 1)
        else:
            description = rest

    created_display = ""
    if created_raw:
        try:
            dt = datetime.datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            created_display = f"{dt.day} {dt.strftime('%b %Y')}"
        except Exception:
            created_display = created_raw[:10]

    return {
        "key": key,
        "tier": tier,
        "platform": platform,
        "description": description,
        "summary": summary,
        "status": status,
        "priority": priority,
        "created": created_raw,
        "created_display": created_display,
        "jira_url": f"https://axitrader.atlassian.net/browse/{key}",
    }


def _mock_tickets() -> list:
    return [
        {"key": "DEMO-002", "tier": "L4", "platform": "Reddit",
         "description": "FCA complaint filed against Axi, 847 engagements",
         "status": "Shareholder dependence", "priority": "Critical",
         "created_display": "30 Apr 2026", "jira_url": "#"},
        {"key": "DEMO-001", "tier": "L4", "platform": "BrokersView",
         "description": "Account freeze, $12,000 locked, DFSA regulatory threat",
         "status": "In Progress", "priority": "Critical",
         "created_display": "30 Apr 2026", "jira_url": "#"},
        {"key": "DEMO-007", "tier": "L3", "platform": "Reddit",
         "description": "Fraud allegation: spread manipulation during FOMC spike",
         "status": "Shareholder dependence", "priority": "High",
         "created_display": "28 Apr 2026", "jira_url": "#"},
        {"key": "DEMO-005", "tier": "L3", "platform": "ForexPeaceArmy",
         "description": "Margin call executed at incorrect level, no explanation",
         "status": "In Progress", "priority": "High",
         "created_display": "29 Apr 2026", "jira_url": "#"},
        {"key": "DEMO-008", "tier": "L3", "platform": "ForexPeaceArmy",
         "description": "Withdrawal 'processed' 2 weeks ago but funds not received",
         "status": "In Progress", "priority": "High",
         "created_display": "29 Apr 2026", "jira_url": "#"},
        {"key": "DEMO-003", "tier": "L3", "platform": "TrustPilot",
         "description": "8-day withdrawal delay, copy-paste support responses",
         "status": "Done", "priority": "High",
         "created_display": "29 Apr 2026", "jira_url": "#"},
    ]


def _write_mock(filename: str, data: dict) -> None:
    MOCK_PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (MOCK_PAYLOAD_DIR / filename).write_text(json.dumps(data, indent=2))
