"""
Quick end-to-end test for jira/client.py against live Jira.
Run with:  python scripts/test_jira.py
Set JIRA_MODE=live in environment before running.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("JIRA_MODE", "live")
os.environ.setdefault("JIRA_BASE_URL", "https://axitrader.atlassian.net")
os.environ.setdefault("JIRA_EMAIL", "timur.dosmurzayev@axi.com")
os.environ.setdefault("JIRA_PROJECT_KEY", "APM")
os.environ.setdefault("DASHBOARD_URL", "http://localhost:5000")

from jira.client import create_ticket, add_response_comment, update_ticket_status

SAMPLE_L4 = {
    "id": "e5f6a7b8-0005-4005-8005-000000000005",
    "platform": "brokersview",
    "url": "https://brokersview.com/broker/axi/reviews/complaint-104872",
    "author": "KhaledM_UAE",
    "posted_at": "2026-04-30T06:10:00Z",
    "summary": "User reports account freeze without explanation, $12,000 locked. DFSA threat.",
    "raw_text_redacted": "My Axi account [ACCOUNT_NUMBER] was frozen on April 27 without any communication. "
                         "I have emailed [EMAIL] and called support 6 times. No one can tell me why my $12,000 "
                         "is locked. I am contacting the DFSA if this is not resolved by end of week.",
    "sentiment": "negative",
    "sentiment_reasoning": "Serious distress about frozen funds with explicit DFSA regulatory threat.",
    "risk_level": "L4",
    "risk_reasoning": "Claude returned L3. [Platform floor: brokersview → L3]. [Client info escalation: PII detected → L4]",
    "has_client_info": True,
    "pending_axi_reply": False,
    "engagement": 47,
    "watch_flags": "DFSA,withdrawal",
    "response_text": (
        "Thank you for sharing your concerns. We understand this situation is important to you "
        "and we want to make sure it receives the attention it deserves. To protect your privacy "
        "and ensure this is handled properly, we'd like to continue this conversation through a "
        "private channel. Please contact our support team via https://support.axi.com and a senior "
        "member of our team will follow up with you directly."
    ),
}


def main():
    token = os.environ.get("JIRA_API_TOKEN")
    if not token:
        print("ERROR: set JIRA_API_TOKEN before running")
        sys.exit(1)

    print("1. Creating ticket...")
    ticket_id = create_ticket(SAMPLE_L4)
    print(f"   Created: {ticket_id}")

    print("2. Adding response comment...")
    add_response_comment(ticket_id, SAMPLE_L4, posted_by="Community Manager")
    print(f"   Comment added to {ticket_id}")

    print("3. Transitioning to Done (simulating 'responded')...")
    update_ticket_status(ticket_id, "responded")
    print(f"   {ticket_id} transitioned to Done")

    print(f"\nDone. Verify at: https://axitrader.atlassian.net/browse/{ticket_id}")


if __name__ == "__main__":
    main()
