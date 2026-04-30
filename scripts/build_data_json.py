"""
Transform data/brandwatch/mentions_apr2026.csv into prototype/data.json.

Run from repo root:
    python scripts/build_data_json.py
"""

import csv
import json
import re
from collections import Counter
from pathlib import Path

CSV_PATH    = Path("data/brandwatch/mentions_apr2026.csv")
OUTPUT_PATH = Path("prototype/data.json")

PLATFORM_MAP = {
    "twitter":          "X (Twitter)",
    "facebook_public":  "Facebook",
    "reddit":           "Reddit",
    "youtube":          "YouTube",
    "instagram_public": "Instagram",
    "bluesky":          "Bsky",
    "tumblr":           "Tumblr",
    # blog / news / forum → prettified from domain (see _platform_from_domain)
}

# Platforms where negative sentiment automatically floors to L3
ESCALATION_PLATFORMS = {
    "trustpilot.com", "brokersview.com", "fastbull.com",
    "forexpeacearmy.com", "forexfactory.com", "reddit.com",
    "play.google.com", "apps.apple.com",
}

AXI_SELECT_RE = re.compile(r"axi[\s_-]?select", re.IGNORECASE)


def _platform_from_domain(domain: str) -> str:
    """Turn a bare domain into a readable platform label."""
    host = domain.replace("www.", "").split(".")[0]
    return host.capitalize() if host else domain


def normalize_platform(page_type: str, domain: str) -> str:
    pt = (page_type or "").lower().strip()
    if pt in PLATFORM_MAP:
        return PLATFORM_MAP[pt]
    # blog / news / forum: use domain name
    dm = (domain or "").lower().strip()
    if dm:
        return _platform_from_domain(dm)
    return "Unknown"


def compute_engagement(row: dict) -> int:
    # Engagement Score is the canonical Brandwatch-computed total
    v = row.get("Engagement Score", "").strip()
    if v:
        try:
            return int(float(v))
        except ValueError:
            pass
    # Fallback: sum individual signal columns
    total = 0
    for col in ("Likes", "Twitter Likes", "Twitter Retweets",
                "Reddit Score", "Facebook Likes", "Facebook Comments"):
        s = row.get(col, "").strip()
        if s:
            try:
                total += int(float(s))
            except ValueError:
                pass
    return total


def assign_tier(sentiment: str, domain: str, engagement: int) -> str:
    if sentiment == "negative":
        if domain in ESCALATION_PLATFORMS or engagement >= 50:
            return "L3"
        return "L2"
    return "L1"


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    header_idx = next(i for i, r in enumerate(rows) if "Date" in r)
    headers = rows[header_idx]
    data = []
    for row in rows[header_idx + 1:]:
        if not any(row):
            continue
        if len(row) < len(headers):
            row = row + [""] * (len(headers) - len(row))
        data.append(dict(zip(headers, row)))
    return data


def build_mention(row: dict) -> dict:
    text      = (row.get("Title") or "").replace("\n", " ").replace("\r", "").strip()
    sentiment = (row.get("Sentiment") or "neutral").lower()
    if sentiment not in ("positive", "negative", "neutral"):
        sentiment = "neutral"
    domain     = (row.get("Domain") or "").lower().strip()
    page_type  = row.get("Page Type") or ""
    platform   = normalize_platform(page_type, domain)
    engagement = compute_engagement(row)
    tier       = assign_tier(sentiment, domain, engagement)

    return {
        "text":          text,
        "author":        (row.get("Author") or "").strip(),
        "platform":      platform,
        "sentiment":     sentiment,
        "tier":          tier,
        "engagement":    engagement,
        "date":          row.get("Date") or "",
        "url":           (row.get("Url") or "").strip(),
        "is_axi_select": bool(AXI_SELECT_RE.search(text)),
    }


def _mention_without_flag(m: dict) -> dict:
    return {k: v for k, v in m.items() if k != "is_axi_select"}


def build_compliance_queue(mentions: list[dict], max_items: int = 10) -> list[dict]:
    items = [m for m in mentions if m["tier"] in ("L2", "L3", "L4")]
    items.sort(key=lambda m: (m["tier"] == "L3" or m["tier"] == "L4", m["engagement"]), reverse=True)
    return [
        {
            "title":      m["text"][:120],
            "platform":   m["platform"],
            "engagement": m["engagement"],
            "tier":       m["tier"],
            "date":       m["date"],
            "url":        m["url"],
        }
        for m in items[:max_items]
    ]


def main():
    print(f"Reading {CSV_PATH}...")
    rows = read_csv(CSV_PATH)
    mentions = [build_mention(r) for r in rows]
    print(f"Parsed {len(mentions)} mentions")

    # ── Overall stats ──────────────────────────────────────────────────────────
    total    = len(mentions)
    positive = sum(1 for m in mentions if m["sentiment"] == "positive")
    negative = sum(1 for m in mentions if m["sentiment"] == "negative")
    neutral  = total - positive - negative

    sorted_all     = sorted(mentions, key=lambda m: m["date"], reverse=True)
    recent_mentions = [_mention_without_flag(m) for m in sorted_all[:25]]
    compliance_queue = build_compliance_queue(mentions)

    platform_counts = [
        [p, c]
        for p, c in Counter(m["platform"] for m in mentions).most_common(8)
    ]

    # ── Axi Select section ─────────────────────────────────────────────────────
    sel = [m for m in mentions if m["is_axi_select"]]
    sel_total    = len(sel)
    sel_positive = sum(1 for m in sel if m["sentiment"] == "positive")
    sel_negative = sum(1 for m in sel if m["sentiment"] == "negative")
    sel_neutral  = sel_total - sel_positive - sel_negative

    axi_select = {
        "total":    sel_total,
        "positive": sel_positive,
        "negative": sel_negative,
        "neutral":  sel_neutral,
        "by_tier":  {
            "L4": sum(1 for m in sel if m["tier"] == "L4"),
            "L3": sum(1 for m in sel if m["tier"] == "L3"),
            "L2": sum(1 for m in sel if m["tier"] == "L2"),
            "L1": sum(1 for m in sel if m["tier"] == "L1"),
        },
        "by_platform": [
            [p, c]
            for p, c in Counter(m["platform"] for m in sel).most_common(8)
        ],
        "recent_mentions": [
            _mention_without_flag(m)
            for m in sorted(sel, key=lambda m: m["date"], reverse=True)[:25]
        ],
        "compliance_queue": build_compliance_queue(sel),
    }

    output = {
        "generated":      "2026-04-30",
        "period":         "Apr 1 – Apr 30 2026",
        "total":          total,
        "positive":       positive,
        "negative":       negative,
        "neutral":        neutral,
        "recent_mentions": recent_mentions,
        "compliance_queue": compliance_queue,
        "platform_counts": platform_counts,
        "axi_select":     axi_select,
    }

    OUTPUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Written to {OUTPUT_PATH}")
    print(f"  Overall:    {total} total | {positive} pos | {negative} neg | {neutral} neutral")
    print(f"  Axi Select: {sel_total} mentions | {sel_positive} pos | {sel_negative} neg")
    print(f"  By tier:    {axi_select['by_tier']}")
    print(f"  By platform (top 5): {axi_select['by_platform'][:5]}")


if __name__ == "__main__":
    main()
