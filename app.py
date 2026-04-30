import os
import json
from pathlib import Path

from flask import Flask, render_template, jsonify, request, abort

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-lighthouse")

DATA_PATH              = Path("service/data.json")
TICKETED_IDS_PATH      = Path("service/ticketed_ids.json")
COMPLIANCE_ACTIONS_PATH = Path("service/compliance_actions.json")


def _load_data() -> dict:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _load_ticketed_ids() -> dict:
    if TICKETED_IDS_PATH.exists():
        return json.loads(TICKETED_IDS_PATH.read_text(encoding="utf-8"))
    return {}


def _save_ticketed_ids(ids: dict) -> None:
    TICKETED_IDS_PATH.write_text(json.dumps(ids, indent=2), encoding="utf-8")


def _load_compliance_actions() -> dict:
    if COMPLIANCE_ACTIONS_PATH.exists():
        return json.loads(COMPLIANCE_ACTIONS_PATH.read_text(encoding="utf-8"))
    return {}


def _save_compliance_actions(actions: dict) -> None:
    COMPLIANCE_ACTIONS_PATH.write_text(json.dumps(actions, indent=2), encoding="utf-8")


@app.context_processor
def inject_nav_data():
    try:
        data = _load_data()
        queue = data.get("compliance_queue", [])
        badge = len([c for c in queue if c.get("tier") in ("L3", "L4")])
    except Exception:
        badge = 0
    return dict(compliance_badge_count=badge)


@app.route("/")
def index():
    data      = _load_data()
    jira_mode = os.environ.get("JIRA_MODE", "mock")
    ticketed  = _load_ticketed_ids()
    n_candidates = len(data.get("ticket_candidates", []))
    n_ticketed   = sum(1 for c in data.get("ticket_candidates", []) if c["id"] in ticketed)
    return render_template(
        "dashboard.html",
        data=data,
        jira_mode=jira_mode,
        n_candidates=n_candidates,
        n_ticketed=n_ticketed,
    )


@app.route("/mentions")
def mentions():
    data        = _load_data()
    platform_filter  = request.args.get("platform", "")
    tier_filter      = request.args.get("tier", "")
    sentiment_filter = request.args.get("sentiment", "")

    all_mentions = data.get("recent_mentions", [])

    platforms  = sorted(set(m["platform"] for m in all_mentions))
    tiers      = ["L1", "L2", "L3", "L4"]
    sentiments = ["positive", "negative", "neutral"]

    filtered = all_mentions
    if platform_filter:
        filtered = [m for m in filtered if m["platform"] == platform_filter]
    if tier_filter:
        filtered = [m for m in filtered if m["tier"] == tier_filter]
    if sentiment_filter:
        filtered = [m for m in filtered if m["sentiment"] == sentiment_filter]

    return render_template(
        "mentions.html",
        mentions=filtered,
        total=len(all_mentions),
        platforms=platforms,
        tiers=tiers,
        sentiments=sentiments,
        platform_filter=platform_filter,
        tier_filter=tier_filter,
        sentiment_filter=sentiment_filter,
        active_page="mentions",
        period=data.get("period", ""),
    )


@app.route("/mention/<mention_id>")
def mention_detail(mention_id):
    data       = _load_data()
    ticketed   = _load_ticketed_ids()
    actions    = _load_compliance_actions()

    candidates = data.get("ticket_candidates", [])
    mention    = next((m for m in candidates if m.get("id") == mention_id), None)
    if mention is None:
        abort(404)

    action_record = actions.get(mention_id, {})
    jira_key      = ticketed.get(mention_id)

    return render_template(
        "mention_detail.html",
        mention=mention,
        jira_key=jira_key,
        action_record=action_record,
        active_page="mentions",
    )


@app.route("/compliance")
def compliance():
    data      = _load_data()
    ticketed  = _load_ticketed_ids()
    actions   = _load_compliance_actions()

    candidates = data.get("ticket_candidates", [])
    items = [
        {**m, "jira_key": ticketed.get(m["id"]), "action": actions.get(m["id"], {})}
        for m in candidates
        if m.get("risk_level") in ("L2", "L3", "L4")
    ]

    return render_template(
        "compliance.html",
        items=items,
        active_page="compliance",
        period=data.get("period", ""),
    )


@app.route("/watchlist")
def watchlist():
    data        = _load_data()
    watch_terms = data.get("watch_counts", [])
    return render_template(
        "watchlist.html",
        watch_terms=watch_terms,
        active_page="watchlist",
        period=data.get("period", ""),
    )


@app.route("/runs")
def runs():
    data           = _load_data()
    platform_counts = data.get("platform_counts", [])
    return render_template(
        "runs.html",
        platform_counts=platform_counts,
        active_page="runs",
        period=data.get("period", ""),
        total=data.get("total", 0),
    )


@app.route("/tickets")
def tickets():
    from jira.client import get_epic_tickets
    epic_key = os.environ.get("JIRA_EPIC_KEY", "APM-75")
    try:
        ticket_list = get_epic_tickets(epic_key)
        error = None
    except Exception as e:
        ticket_list = []
        error = str(e)
    return render_template(
        "tickets.html",
        tickets=ticket_list,
        epic_key=epic_key,
        error=error,
        active_page="tickets",
    )


@app.route("/api/create-jira-tickets", methods=["POST"])
def create_jira_tickets():
    from jira.client import create_ticket
    data       = _load_data()
    candidates = data.get("ticket_candidates", [])
    ticketed   = _load_ticketed_ids()

    created = []
    skipped = []
    errors  = []

    for m in candidates[:10]:
        mid = m.get("id")
        if mid in ticketed:
            skipped.append({"id": mid, "jira_key": ticketed[mid]})
            continue
        try:
            key = create_ticket(m)
            ticketed[mid] = key
            created.append({"id": mid, "jira_key": key, "summary": m.get("summary", "")[:60]})
        except Exception as exc:
            errors.append({"id": mid, "error": str(exc)})

    _save_ticketed_ids(ticketed)
    jira_mode = os.environ.get("JIRA_MODE", "mock")
    return jsonify({
        "jira_mode": jira_mode,
        "created":   created,
        "skipped":   skipped,
        "errors":    errors,
    })


@app.route("/api/compliance-action", methods=["POST"])
def compliance_action():
    payload       = request.get_json(force=True) or {}
    mention_id    = payload.get("id", "")
    action        = payload.get("action", "")  # responded | escalated | not_relevant | wont_respond
    response_text = payload.get("response_text", "")

    if not mention_id or not action:
        return jsonify({"error": "id and action required"}), 400

    actions = _load_compliance_actions()
    actions[mention_id] = {"action": action, "response_text": response_text}
    _save_compliance_actions(actions)

    ticketed  = _load_ticketed_ids()
    jira_key  = ticketed.get(mention_id)

    if jira_key:
        try:
            from jira.client import update_ticket_status, add_response_comment
            update_ticket_status(jira_key, action)
            if action == "responded" and response_text:
                data       = _load_data()
                candidates = data.get("ticket_candidates", [])
                mention    = next((m for m in candidates if m.get("id") == mention_id), {})
                mention    = {**mention, "response_text": response_text}
                add_response_comment(jira_key, mention)
        except Exception as exc:
            return jsonify({"ok": True, "jira_key": jira_key, "jira_error": str(exc)})

    return jsonify({"ok": True, "jira_key": jira_key})


if __name__ == "__main__":
    app.run(debug=True)
