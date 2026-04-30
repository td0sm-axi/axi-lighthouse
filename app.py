import os
import json
from pathlib import Path

from flask import Flask, render_template, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-lighthouse")

DATA_PATH        = Path("prototype/data.json")
TICKETED_IDS_PATH = Path("data/ticketed_ids.json")


def _load_data() -> dict:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _load_ticketed_ids() -> dict:
    if TICKETED_IDS_PATH.exists():
        return json.loads(TICKETED_IDS_PATH.read_text(encoding="utf-8"))
    return {}


def _save_ticketed_ids(ids: dict) -> None:
    TICKETED_IDS_PATH.write_text(json.dumps(ids, indent=2), encoding="utf-8")


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
    return render_template("tickets.html", tickets=ticket_list, epic_key=epic_key, error=error)


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


if __name__ == "__main__":
    app.run(debug=True)
