import os
from flask import Flask, render_template, redirect, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-lighthouse")


@app.route("/")
def index():
    return redirect(url_for("tickets"))


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


if __name__ == "__main__":
    app.run(debug=True)
