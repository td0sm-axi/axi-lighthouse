#!/usr/bin/env python3
"""
Creates the 'Axi Lighthouse' Epic in APM and seeds it with 11 dummy L3/L4 tickets
covering all status states needed for the dashboard demo.

Epic: APM-75 (already created)

Usage:
    JIRA_API_TOKEN=<token> python scripts/create_jira_demo_data.py
"""
import os
import sys
import base64

import requests

BASE_URL = "https://axitrader.atlassian.net"
EMAIL = "timur.dosmurzayev@axi.com"
TOKEN = os.environ.get("JIRA_API_TOKEN", "")
PROJECT = "APM"
EPIC_KEY = "APM-75"
ASSIGNEE = "712020:701a8b9a-c04d-4ca3-8278-97e4f0c9a203"  # Timur Dosmurzayev

# Transition IDs confirmed for APM project
T_IN_PROGRESS = "31"
T_DONE        = "41"
T_ESCALATED   = "51"   # Shareholder dependence

PRIORITY = {"L3": "High", "L4": "Critical"}


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _hdrs():
    enc = base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
    return {"Authorization": f"Basic {enc}",
            "Content-Type": "application/json",
            "Accept": "application/json"}


def _post(path, body):
    r = requests.post(f"{BASE_URL}{path}", headers=_hdrs(), json=body, timeout=10)
    if not r.ok:
        print(f"  ERROR {r.status_code}: {r.text[:300]}")
        r.raise_for_status()
    return r.json() if r.text else {}


def _transition(key, tid):
    r = requests.post(
        f"{BASE_URL}/rest/api/3/issue/{key}/transitions",
        headers=_hdrs(), json={"transition": {"id": tid}}, timeout=10,
    )
    if not r.ok:
        print(f"  Warning: transition failed for {key}: {r.text[:150]}")


# ── ADF builders ───────────────────────────────────────────────────────────────

def _t(text, bold=False):
    n = {"type": "text", "text": str(text)}
    if bold:
        n["marks"] = [{"type": "strong"}]
    return n


def _p(*children):
    return {"type": "paragraph", "content": list(children)}


def _h(level, label):
    return {"type": "heading", "attrs": {"level": level}, "content": [_t(label)]}


def _bq(text):
    return {"type": "blockquote", "content": [_p(_t(text))]}


def _rule():
    return {"type": "rule"}


def _description(tk):
    content = [
        _h(2, "Mention Details"),
        _p(_t("Platform: ", bold=True),   _t(tk["platform"])),
        _p(_t("Author: ", bold=True),      _t(tk["author"])),
        _p(_t("Posted at: ", bold=True),   _t(tk["posted_at"])),
        _p(_t("Engagement: ", bold=True),  _t(tk["engagement"])),
        _p(_t("URL: ", bold=True),         _t(tk["url"])),
        _rule(),
        _h(2, "Summary"),
        _p(_t(tk["summary_long"])),
        _h(2, "Mention Text (PII-redacted)"),
        _bq(tk["raw_text"]),
        _rule(),
        _h(2, "Classification"),
        _p(_t("Sentiment: ", bold=True),         _t(tk["sentiment"])),
        _p(_t("Risk tier: ", bold=True),          _t(tk["risk_level"])),
        _p(_t("Risk reasoning: ", bold=True),     _t(tk["risk_reasoning"])),
        _p(_t("Watch flags: ", bold=True),        _t(tk.get("watch_flags", "—"))),
        _p(_t("Client info detected: ", bold=True), _t("Yes" if tk.get("has_client_info") else "No")),
    ]
    if tk.get("draft_response"):
        content += [
            _rule(),
            _h(2, "Drafted Response (pending Community Manager approval)"),
            _bq(tk["draft_response"]),
        ]
    content.append(_p(_t("Lighthouse: ", bold=True),
                      _t(f"http://localhost:5000/mention/{tk['id']}")))
    return {"type": "doc", "version": 1, "content": content}


def _response_comment(tk, posted_by="Community Manager"):
    return {
        "body": {
            "type": "doc", "version": 1,
            "content": [
                _h(3, "Response Posted"),
                _p(_t("Posted by: ", bold=True),  _t(posted_by)),
                _p(_t("Platform: ", bold=True),   _t(tk["platform"])),
                _p(_t("Posted at: ", bold=True),  _t("2026-04-30 14:32 UTC")),
                _p(_t("Response URL: ", bold=True), _t("—")),
                _rule(),
                _h(3, "Response Text"),
                _bq(tk["draft_response"]),
            ]
        }
    }


# ── Ticket data ────────────────────────────────────────────────────────────────

TICKETS = [

    # ══ L4 ══════════════════════════════════════════════════════════════════
    {
        "id": "e5f6a7b8-L4-01",
        "risk_level": "L4",
        "platform": "BrokersView",
        "author": "KhaledM_UAE",
        "posted_at": "2026-04-30T06:10:00Z",
        "engagement": 47,
        "url": "https://brokersview.com/broker/axi/reviews/complaint-104872",
        "summary_snippet": "Account freeze, $12,000 locked, DFSA regulatory threat — client info detected",
        "summary_long": "User reports account freeze without explanation with $12,000 locked. Has contacted support 6 times with no resolution. Explicitly threatening a DFSA complaint by end of week. Account number and personal email visible in the original post before PII redaction.",
        "raw_text": "My Axi account [ACCOUNT_NUMBER] was frozen on April 27 without any communication. I have emailed [EMAIL] and called support 6 times. No one can tell me why my $12,000 is locked. I am contacting the DFSA if this is not resolved by end of week. This is completely unacceptable.",
        "sentiment": "negative",
        "risk_reasoning": "Claude Stage 2 returned L3. [Platform floor: brokersview negative → L3 minimum]. [Client info escalation: PII detected → L4] — [ACCOUNT_NUMBER] and [EMAIL] present in redacted text.",
        "watch_flags": "DFSA, withdrawal",
        "has_client_info": True,
        "draft_response": "Thank you for sharing your concerns. We understand this situation is important to you and we want to make sure it receives the attention it deserves. To protect your privacy and ensure this is handled properly, we'd like to continue this conversation through a private channel. Please contact our support team via https://support.axi.com and a senior member of our team will follow up with you directly.",
        "transition": T_IN_PROGRESS,
        "add_comment": False,
    },
    {
        "id": "d4e5f6a7-L4-02",
        "risk_level": "L4",
        "platform": "Reddit",
        "author": "forex_trader_uk",
        "posted_at": "2026-04-30T07:15:00Z",
        "engagement": 847,
        "url": "https://reddit.com/r/Forex/comments/1cyabc1/fca_complaint_axi",
        "summary_snippet": "FCA complaint filed against Axi, 847 engagements, coordinated campaign forming in r/Forex",
        "summary_long": "User claims to have filed an FCA complaint against Axi after 3 weeks without resolution on a withdrawal issue. Post gaining significant traction (847 engagements) in r/Forex. Multiple corroborating comments suggest a coordinated negative narrative forming. Escalated to Shareholder dependence.",
        "raw_text": "I've officially filed an FCA complaint against Axi. Three weeks, zero resolution on a withdrawal, and their support just keeps closing my tickets. If you've had similar issues, file a complaint too — regulators need to see the pattern.",
        "sentiment": "negative",
        "risk_reasoning": "Explicit FCA regulatory complaint filed and publicised. 847 engagements — coordinated narrative pattern with multiple corroborating comments. [Platform floor: reddit negative → L3 minimum]. Escalated to L4: named regulatory body in complaint context, crisis-level engagement.",
        "watch_flags": "FCA, withdrawal",
        "has_client_info": False,
        "draft_response": "Thanks for the discussion here. We take all feedback seriously and want to understand the specific situation. We'd encourage anyone with account concerns to reach out to our support team directly at https://support.axi.com — our team is best placed to ensure issues are resolved properly and promptly.",
        "transition": T_ESCALATED,
        "add_comment": False,
    },

    # ══ L3 ══════════════════════════════════════════════════════════════════
    {
        "id": "c3d4e5f6-L3-01",
        "risk_level": "L3",
        "platform": "TrustPilot",
        "author": "disgruntled_trader_99",
        "posted_at": "2026-04-29T14:30:00Z",
        "engagement": 7,
        "url": "https://www.trustpilot.com/reviews/6630f1c2a4b7c80012d3e4f5",
        "summary_snippet": "8-day withdrawal delay, copy-paste support responses, considering leaving Axi",
        "summary_long": "User reports an 8-day withdrawal delay on TrustPilot. Has contacted support three times and received only copy-paste replies. Now actively considering switching brokers. Claude returned L2; platform floor elevated to L3.",
        "raw_text": "I have been waiting 8 days for a withdrawal that should take 2. I contacted support three times and keep getting copy-paste responses telling me to wait. No one is actually looking into this. I am seriously considering moving to another broker.",
        "sentiment": "negative",
        "risk_reasoning": "Claude Stage 2 returned L2 (specific withdrawal complaint, no regulatory language, engagement < 10). [Platform floor applied: trustpilot negative → L3 minimum].",
        "watch_flags": "withdrawal",
        "has_client_info": False,
        "draft_response": "Thank you for reaching out and we're sorry to hear your experience hasn't met your expectations. An 8-day wait is not the standard we hold ourselves to, and we'd like to understand exactly what happened with your withdrawal request. Please contact our support team at https://support.axi.com with your account details so a senior member of our team can prioritise a resolution for you.",
        "transition": T_DONE,
        "add_comment": True,
    },
    {
        "id": "d4e5f6a7-L3-02",
        "risk_level": "L3",
        "platform": "Reddit",
        "author": "ForexNomad_SG",
        "posted_at": "2026-04-30T07:45:00Z",
        "engagement": 31,
        "url": "https://www.reddit.com/r/Forex/comments/1cxyz99/axi_spread_nfp/",
        "summary_snippet": "EUR/USD spread hit 15 pips during NFP, position wiped, 31 engagements in r/Forex",
        "summary_long": "User reports a 15-pip EUR/USD spread during the NFP release on Axi, which liquidated their position. Post gaining traction (31 engagements) in r/Forex. Considering switching brokers. Platform floor applies; viral escalation above 10-engagement L3 threshold.",
        "raw_text": "During the NFP release yesterday Axi's spreads on EUR/USD went to something insane like 15 pips. I get that spreads widen but that completely wiped my position. Has anyone else had this with Axi? Starting to think I need to look elsewhere for major news events.",
        "sentiment": "negative",
        "risk_reasoning": "Spread/leverage complaint during high-impact economic event. 31 engagements — viral escalation above L2 threshold. [Platform floor: reddit negative → L3 minimum].",
        "watch_flags": "spread, leverage",
        "has_client_info": False,
        "draft_response": "Thanks for the discussion here. Spread widening during high-impact events like NFP is a market condition we work hard to manage as tightly as possible. We'd encourage anyone with questions about a specific trade or their account to contact our support team at https://support.axi.com — they're best placed to review individual cases.",
        "transition": None,
        "add_comment": False,
    },
    {
        "id": "f6a7b8c9-L3-03",
        "risk_level": "L3",
        "platform": "ForexPeaceArmy",
        "author": "daytrader_sg",
        "posted_at": "2026-04-29T11:20:00Z",
        "engagement": 12,
        "url": "https://www.forexpeacearmy.com/community/reviews/axi.com/?review=104921",
        "summary_snippet": "Margin call executed at incorrect level, no explanation provided, 12 engagements",
        "summary_long": "User claims their margin call was executed at an incorrect level with a resulting unexpected drawdown. Has reviewed the account agreement and believes the calculation was wrong. Support is confirming the call was valid but refusing to provide the calculation detail. Platform floor applies.",
        "raw_text": "My margin call was executed at a completely wrong level last week. I've checked my account agreement and the numbers don't add up. Axi support just tells me the call was valid but won't explain the calculation. This is not acceptable from a regulated broker.",
        "sentiment": "negative",
        "risk_reasoning": "Margin call dispute — explicitly named in L3 tier definition. User alleges calculation error. [Platform floor: forexpeacearmy negative → L3 minimum].",
        "watch_flags": "margin call",
        "has_client_info": False,
        "draft_response": "Thank you for raising this. We take margin call queries very seriously and want to ensure we can explain exactly what occurred on your account. Please contact our support team at https://support.axi.com with your account details and we'll review the margin call calculation in full and respond directly.",
        "transition": T_IN_PROGRESS,
        "add_comment": False,
    },
    {
        "id": "a7b8c9d0-L3-04",
        "risk_level": "L3",
        "platform": "X (Twitter)",
        "author": "mt5_user_de",
        "posted_at": "2026-04-30T06:00:00Z",
        "engagement": 11,
        "url": "https://twitter.com/mt5_user_de/status/1785500000000000001",
        "summary_snippet": "MT5 platform freezing during volatility spikes, positions stuck, happened 3x this week",
        "summary_long": "User reports MT5 platform freezing repeatedly during volatility spikes, making it impossible to close or modify positions at critical moments. Has occurred 3 times this week. Support not responding. 11 engagements triggers viral escalation threshold.",
        "raw_text": "@AxiTrader MT5 keeps freezing whenever there's a volatility spike. Can't close positions when it matters most. This happened 3 times this week. Support isn't helping. Is anyone else experiencing this?",
        "sentiment": "negative",
        "risk_reasoning": "MT4/MT5 platform issue — explicitly named in L3 tier definition. 11 engagements above viral escalation threshold. Standard platform (Twitter) — no platform floor, tier rule applies.",
        "watch_flags": "—",
        "has_client_info": False,
        "draft_response": "Thank you for flagging this. Platform stability during high-volatility periods is something we take seriously and we're sorry to hear you've been affected. We'd like to investigate the specific instances you encountered. Please reach out at https://support.axi.com with the dates and times and our team will look into this immediately.",
        "transition": None,
        "add_comment": False,
    },
    {
        "id": "b8c9d0e1-L3-05",
        "risk_level": "L3",
        "platform": "TrustPilot",
        "author": "newtrader_au_22",
        "posted_at": "2026-04-28T09:00:00Z",
        "engagement": 5,
        "url": "https://www.trustpilot.com/reviews/6630f1c2a4b7c80012d3e4f6",
        "summary_snippet": "KYC taking 7+ days with no updates, account still inaccessible",
        "summary_long": "New user reports KYC verification taking over 7 days without any status updates. Account remains inaccessible. Two emails sent; only generic auto-replies received. Platform floor applies (TrustPilot negative → L3 minimum).",
        "raw_text": "It's been 7 days since I submitted my KYC documents and my account is still pending verification. No updates, no estimated timeline. I've emailed twice and got generic auto-replies. Very disappointing first experience.",
        "sentiment": "negative",
        "risk_reasoning": "KYC friction complaint. [Platform floor: trustpilot negative → L3 minimum]. Claude Stage 2 returned L2 (specific service complaint, no fraud allegation).",
        "watch_flags": "KYC",
        "has_client_info": False,
        "draft_response": "Thank you for your patience and we sincerely apologise for the delay. KYC timelines can extend during peak periods, but 7 days without an update is not the experience we want you to have. Please contact our support team at https://support.axi.com and reference this review — we'll prioritise your application and provide a direct update.",
        "transition": T_DONE,
        "add_comment": True,
    },
    {
        "id": "c9d0e1f2-L3-06",
        "risk_level": "L3",
        "platform": "BrokersView",
        "author": "leverage_trader_hk",
        "posted_at": "2026-04-29T16:45:00Z",
        "engagement": 9,
        "url": "https://brokersview.com/broker/axi/reviews/complaint-104873",
        "summary_snippet": "Leverage limits on XAU/USD changed without notice, open positions affected",
        "summary_long": "User claims leverage limits on gold (XAU/USD) were reduced without advance notice, changing margin requirements on open positions and causing unexpected liquidation. Argues a regulated broker should not make such changes without warning. Platform floor applies.",
        "raw_text": "Axi changed the leverage limits on XAU/USD without any advance notice. I had open positions calculated on the previous leverage and suddenly found my margin requirements had changed. This caused unnecessary liquidation. This is not how a regulated broker should operate.",
        "sentiment": "negative",
        "risk_reasoning": "Leverage dispute — explicitly named in L3 tier definition. [Platform floor: brokersview negative → L3 minimum].",
        "watch_flags": "leverage",
        "has_client_info": False,
        "draft_response": "Thank you for raising this concern. We understand how significant leverage changes can be for open positions and we take this feedback seriously. We'd like to review the specific circumstances of your account and explain what occurred. Please contact us at https://support.axi.com with your account details so we can investigate directly.",
        "transition": None,
        "add_comment": False,
    },
    {
        "id": "d0e1f2a3-L3-07",
        "risk_level": "L3",
        "platform": "Reddit",
        "author": "anon_trader_91",
        "posted_at": "2026-04-28T20:00:00Z",
        "engagement": 88,
        "url": "https://www.reddit.com/r/Daytrading/comments/1cwxyz1/axi_fraud_fomc/",
        "summary_snippet": "Fraud allegation: spread manipulation during FOMC spike, 88 engagements in r/Daytrading",
        "summary_long": "User alleges Axi manipulated spreads during the FOMC event to trigger stop losses. Post gaining significant traction (88 engagements) in r/Daytrading with multiple corroborating comments. Pattern suggests coordinated negative campaign. Escalated to Shareholder dependence.",
        "raw_text": "I'm going to say it plainly: what Axi did to my account during the FOMC spike was spread manipulation to trigger my stop loss. The spread was kept artificially wide for 4 minutes. I have screenshots. Anyone else? I'm gathering evidence and will share with regulators.",
        "sentiment": "negative",
        "risk_reasoning": "Fraud allegation — explicitly named in L3 tier definition. 88 engagements — viral escalation. Coordinated narrative (multiple corroborating comments). [Platform floor: reddit negative → L3 minimum]. Regulatory escalation threat. Escalated to Shareholder dependence.",
        "watch_flags": "fraud, spread",
        "has_client_info": False,
        "draft_response": "Thank you for your message. We take any allegation of this nature extremely seriously. We'd like to review the specific circumstances you've described in detail. Please contact our compliance team at https://support.axi.com with the relevant dates, times, and any documentation — we want to ensure this is investigated thoroughly and handled properly.",
        "transition": T_ESCALATED,
        "add_comment": False,
    },
    {
        "id": "e1f2a3b4-L3-08",
        "risk_level": "L3",
        "platform": "ForexPeaceArmy",
        "author": "fx_veteran_99",
        "posted_at": "2026-04-29T08:30:00Z",
        "engagement": 22,
        "url": "https://www.forexpeacearmy.com/community/reviews/axi.com/?review=104922",
        "summary_snippet": "Withdrawal 'processed' 2 weeks ago but funds not received — implying intentional withholding",
        "summary_long": "User claims their withdrawal was marked 'processed' by Axi on April 15 but has not arrived in their bank account after 2 weeks. Axi support attributes it to a bank issue, but the bank has no record of an incoming transfer. 22 engagements above viral escalation threshold. Platform floor applies.",
        "raw_text": "My withdrawal was marked as 'processed' by Axi on April 15. It is now April 29 and the funds have not arrived in my bank. Axi support says it's a bank issue but my bank has no record of any incoming transfer. Where is my money?",
        "sentiment": "negative",
        "risk_reasoning": "Withdrawal complaint with implicit fraud allegation (processed status vs no bank receipt). [Platform floor: forexpeacearmy negative → L3 minimum]. 22 engagements above L2 viral threshold.",
        "watch_flags": "withdrawal, fraud",
        "has_client_info": False,
        "draft_response": "Thank you for raising this urgently — we understand how serious it is when a processed withdrawal has not arrived. We want to resolve this as a priority. Please contact our support team immediately at https://support.axi.com with your account details and withdrawal reference number so we can trace the transfer with our banking partners.",
        "transition": T_IN_PROGRESS,
        "add_comment": False,
    },
    {
        "id": "f2a3b4c5-L3-09",
        "risk_level": "L3",
        "platform": "TrustPilot",
        "author": "fomc_trader",
        "posted_at": "2026-04-27T18:00:00Z",
        "engagement": 6,
        "url": "https://www.trustpilot.com/reviews/6630f1c2a4b7c80012d3e4f7",
        "summary_snippet": "Platform outage during FOMC announcement, 8-minute blackout, positions unmanageable",
        "summary_long": "User reports the Axi platform was inaccessible for approximately 8 minutes during the FOMC announcement on April 27, preventing position management during a critical trading window. Platform floor applies (TrustPilot negative → L3 minimum).",
        "raw_text": "Axi's platform went down at exactly the moment of the FOMC announcement on Wednesday. Couldn't close or modify any positions for 8 minutes. This is a critical failure for a trading platform. I had significant open exposure during this time and there was nothing I could do.",
        "sentiment": "negative",
        "risk_reasoning": "MT4/MT5 platform outage during high-impact economic event — explicitly named in L3 tier definition. [Platform floor: trustpilot negative → L3 minimum]. Claude Stage 2 returned L2.",
        "watch_flags": "—",
        "has_client_info": False,
        "draft_response": "Thank you for bringing this to our attention and we sincerely apologise for the disruption during the FOMC announcement. Platform stability during high-impact events is a top priority and we understand how critical that window was. We'd like to review what occurred on your account. Please contact our support team at https://support.axi.com with your account details.",
        "transition": T_DONE,
        "add_comment": True,
    },
]


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if not TOKEN:
        print("ERROR: set JIRA_API_TOKEN")
        sys.exit(1)

    print(f"Epic: {EPIC_KEY}  |  Project: {PROJECT}")
    print(f"Creating {len(TICKETS)} tickets...\n")

    results = []

    for tk in TICKETS:
        sys.stdout.write(f"  [{tk['risk_level']}] {tk['platform']} — {tk['author']} ... ")
        sys.stdout.flush()

        payload = {
            "fields": {
                "project":     {"key": PROJECT},
                "parent":      {"key": EPIC_KEY},
                "summary":     f"[{tk['risk_level']}] {tk['platform']} — {tk['summary_snippet']}",
                "issuetype":   {"name": "Task"},
                "priority":    {"name": PRIORITY[tk["risk_level"]]},
                "assignee":    {"accountId": ASSIGNEE},
                "labels":      ["lighthouse", tk["risk_level"].lower(), tk["platform"].lower().replace(" ", "-").replace("(", "").replace(")", "")],
                "description": _description(tk),
            }
        }

        result = _post("/rest/api/3/issue", payload)
        key = result["key"]
        status = "To Do"

        if tk.get("transition"):
            _transition(key, tk["transition"])
            status = {T_IN_PROGRESS: "In Progress", T_DONE: "Done", T_ESCALATED: "Shareholder dependence"}[tk["transition"]]

        if tk.get("add_comment") and tk.get("draft_response"):
            _post(f"/rest/api/3/issue/{key}/comment", _response_comment(tk))

        print(f"{key}  ->  {status}")
        results.append((key, tk["risk_level"], tk["platform"], status))

    print("\n" + "-"*62)
    print(f"{'Ticket':<12} {'Tier':<6} {'Platform':<22} {'Status'}")
    print("-"*62)
    for key, tier, platform, status in results:
        print(f"{key:<12} {tier:<6} {platform:<22} {status}")
    print("-"*62)
    print(f"\nEpic: https://axitrader.atlassian.net/browse/{EPIC_KEY}")
    print(f"Board: https://axitrader.atlassian.net/jira/software/c/projects/APM/boards/3068")


if __name__ == "__main__":
    main()
