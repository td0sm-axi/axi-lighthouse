"""
skills/review_classifier.py
Stratified QA audit: compare Brandwatch sentiment labels against a fresh
Claude re-classification to catch labelling drift and systematic errors.

Usage:
    python skills/review_classifier.py [--sample-size N] [--csv PATH] [--output DIR]

Exit codes:
    0 — major disagreement rate < 15 % (classifier looks healthy)
    1 — major disagreement rate >= 15 % (review the system prompt)
"""
import argparse
import csv
import io
import json
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.reclassify_mentions import reclassify_batch

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CSV = (
    Path(__file__).parent.parent / "data" / "brandwatch" / "mentions_apr2026.csv"
)
DEFAULT_OUTPUT = Path(__file__).parent.parent / "data" / "qa_reports"
DEFAULT_SAMPLE_SIZE = 50

PLATFORM_FLOORS = {"reddit", "trustpilot", "brokersview"}

_BW_SENTIMENT = {"positive", "negative", "neutral"}


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def _find_header_idx(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if '"Query Id"' in line and '"Date"' in line:
            return i
    raise ValueError("Cannot locate the CSV header row (expected 'Query Id','Date' columns).")


def load_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        lines = f.readlines()

    header_idx = _find_header_idx(lines)
    reader = csv.DictReader(io.StringIO("".join(lines[header_idx:])))

    mentions: list[dict] = []
    for row in reader:
        text = (row.get("Snippet") or row.get("Title") or "").strip()
        if not text:
            continue

        raw_sentiment = (row.get("Sentiment") or "neutral").strip().lower()
        bw_sentiment = raw_sentiment if raw_sentiment in _BW_SENTIMENT else "neutral"

        page_type = (row.get("Page Type") or "").strip().lower()
        domain = (row.get("Domain") or "").strip().lower()
        platform = page_type or domain.split(".")[0]

        engagement = 0
        for col in ("Engagement Score", "Twitter Likes", "Reddit Score", "Likes"):
            val = (row.get(col) or "").strip()
            if val:
                try:
                    engagement = int(float(val))
                    break
                except ValueError:
                    pass

        mentions.append(
            {
                "id": (row.get("") or row.get("Resource Id") or str(len(mentions) + 1)).strip(),
                "date": row.get("Date", "").strip(),
                "author": row.get("Author", "").strip(),
                "platform": platform,
                "text": text,
                "engagement": engagement,
                "bw_sentiment": bw_sentiment,
                "url": row.get("Url", "").strip(),
            }
        )
    return mentions


# ---------------------------------------------------------------------------
# Stratified sampling
# ---------------------------------------------------------------------------

def stratified_sample(mentions: list[dict], n: int, seed: int = 42) -> list[dict]:
    """
    Sample n mentions with deliberate weighting toward higher-risk cases:
      40 % negative (stress-tests L3/L4 boundary rules)
      30 % neutral  (common misclassification direction)
      20 % positive
      10 % high-engagement negative (top by engagement score)
    """
    rng = random.Random(seed)
    by_sentiment: dict[str, list[dict]] = defaultdict(list)
    for m in mentions:
        by_sentiment[m["bw_sentiment"]].append(m)

    slots = {
        "negative": int(n * 0.40),
        "neutral": int(n * 0.30),
        "positive": int(n * 0.20),
    }
    remainder = n - sum(slots.values())

    sample: list[dict] = []
    seen_ids: set[str] = set()

    for sentiment, count in slots.items():
        pool = [m for m in by_sentiment[sentiment] if m["id"] not in seen_ids]
        chosen = rng.sample(pool, min(count, len(pool)))
        sample.extend(chosen)
        seen_ids.update(m["id"] for m in chosen)

    # Fill remainder with highest-engagement negatives not already in sample
    neg_sorted = sorted(
        [m for m in by_sentiment["negative"] if m["id"] not in seen_ids],
        key=lambda m: m["engagement"],
        reverse=True,
    )
    for m in neg_sorted[:remainder]:
        sample.append(m)
        seen_ids.add(m["id"])

    rng.shuffle(sample)
    return sample[:n]


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------

_MINOR_PAIRS = {
    frozenset(["positive", "neutral"]),
    frozenset(["negative", "neutral"]),
}


def _verdict(bw: str, claude: str) -> str:
    if bw == claude:
        return "agree"
    if frozenset([bw, claude]) in _MINOR_PAIRS:
        return "minor_disagree"
    return "major_disagree"


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(sample: list[dict], classified: list[dict]) -> dict:
    agreements: list[dict] = []
    disagreements: list[dict] = []

    by_platform: dict[str, dict] = defaultdict(lambda: {"agree": 0, "minor": 0, "major": 0})
    by_bw_sentiment: dict[str, dict] = defaultdict(lambda: {"agree": 0, "minor": 0, "major": 0})

    for original, result in zip(sample, classified):
        bw_s = original["bw_sentiment"]
        claude_s = result.get("sentiment", "neutral")
        verdict = _verdict(bw_s, claude_s)

        entry = {
            "id": original["id"],
            "date": original["date"],
            "platform": original["platform"],
            "author": original["author"],
            "url": original["url"],
            "text_snippet": original["text"][:300],
            "engagement": original["engagement"],
            "bw_sentiment": bw_s,
            "claude_sentiment": claude_s,
            "claude_sentiment_reasoning": result.get("sentiment_reasoning", ""),
            "claude_risk_level": result.get("risk_level", ""),
            "claude_risk_reasoning": result.get("risk_reasoning", ""),
            "claude_watch_flags": result.get("watch_flags"),
            "has_client_info": result.get("has_client_info", False),
            "verdict": verdict,
        }

        bucket = "agree" if verdict == "agree" else ("minor" if verdict == "minor_disagree" else "major")
        by_platform[original["platform"]][bucket] += 1
        by_bw_sentiment[bw_s][bucket] += 1

        if verdict == "agree":
            agreements.append(entry)
        else:
            disagreements.append(entry)

    total = len(sample)
    agree_n = len(agreements)
    minor_n = sum(1 for d in disagreements if d["verdict"] == "minor_disagree")
    major_n = sum(1 for d in disagreements if d["verdict"] == "major_disagree")

    # Reclassification candidates: major disagreement on mentions with engagement >= 5
    # (high-engagement misclassifications carry more reputational risk)
    reclassify_recommended = [
        d for d in disagreements
        if d["verdict"] == "major_disagree" and d["engagement"] >= 5
    ]

    # Platform floor violations: BW labels a Reddit/TP/BV mention as non-negative
    # but Claude sees it as negative (potential under-escalation)
    floor_violations = [
        d for d in disagreements
        if d["platform"] in PLATFORM_FLOORS
        and d["bw_sentiment"] != "negative"
        and d["claude_sentiment"] == "negative"
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_size": total,
        "agreement_rate": round(agree_n / total, 3) if total else 0,
        "minor_disagreement_rate": round(minor_n / total, 3) if total else 0,
        "major_disagreement_rate": round(major_n / total, 3) if total else 0,
        "classifier_healthy": (major_n / total < 0.15) if total else True,
        "by_platform": {k: dict(v) for k, v in by_platform.items()},
        "by_bw_sentiment": {k: dict(v) for k, v in by_bw_sentiment.items()},
        "reclassify_recommended": reclassify_recommended,
        "reclassify_recommended_count": len(reclassify_recommended),
        "platform_floor_violations": floor_violations,
        "platform_floor_violation_count": len(floor_violations),
        "major_disagreements": [d for d in disagreements if d["verdict"] == "major_disagree"],
        "minor_disagreements": [d for d in disagreements if d["verdict"] == "minor_disagree"],
        "agreements_sample": agreements[:10],
    }


# ---------------------------------------------------------------------------
# Console output
# ---------------------------------------------------------------------------

def print_summary(report: dict) -> None:
    w = 62
    print(f"\n{'=' * w}")
    print("  CLASSIFIER QA REVIEW REPORT")
    print(f"  Generated : {report['generated_at']}")
    print(f"  Sample    : {report['sample_size']} mentions")
    print(f"{'=' * w}")
    print(f"  Agreement rate          : {report['agreement_rate']:.1%}")
    print(f"  Minor disagreement rate : {report['minor_disagreement_rate']:.1%}")
    print(f"  Major disagreement rate : {report['major_disagreement_rate']:.1%}")

    status = "HEALTHY ✓" if report["classifier_healthy"] else "REVIEW NEEDED ✗"
    print(f"\n  Classifier status: {status}")

    if report["by_platform"]:
        print("\n  Disagreements by platform:")
        for platform, counts in sorted(report["by_platform"].items()):
            total_p = sum(counts.values())
            dis = counts.get("minor", 0) + counts.get("major", 0)
            if total_p:
                print(f"    {platform:<22} {dis}/{total_p} disagree")

    if report["by_bw_sentiment"]:
        print("\n  Disagreements by BW sentiment label:")
        for label, counts in sorted(report["by_bw_sentiment"].items()):
            total_l = sum(counts.values())
            dis = counts.get("minor", 0) + counts.get("major", 0)
            if total_l:
                print(f"    {label:<22} {dis}/{total_l} disagree")

    if report["platform_floor_violation_count"]:
        print(
            f"\n  ⚠  PLATFORM FLOOR VIOLATIONS: {report['platform_floor_violation_count']}"
        )
        print(
            "     BW did not label these as negative, but Claude did."
        )
        print("     They should be at minimum L3 per platform floor rules.")
        for v in report["platform_floor_violations"]:
            print(f"       [{v['platform']}] {v['text_snippet'][:80]}…")

    if report["reclassify_recommended_count"]:
        print(f"\n  RECLASSIFICATION RECOMMENDED: {report['reclassify_recommended_count']} mention(s)")
        for rec in report["reclassify_recommended"][:5]:
            print(
                f"    [{rec['platform']}] BW={rec['bw_sentiment']} → Claude={rec['claude_sentiment']}"
                f" (engagement {rec['engagement']})"
            )
            print(f"    Text  : {rec['text_snippet'][:100]}…")
            print(f"    Reason: {rec['claude_sentiment_reasoning'][:120]}")
            print()
    else:
        print("\n  No high-priority reclassifications required.")

    print(f"{'=' * w}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="QA audit: Brandwatch vs Claude sentiment labels"
    )
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    print(f"Loading mentions from {args.csv} …")
    mentions = load_csv(args.csv)
    print(f"  Loaded {len(mentions):,} mentions")

    sample = stratified_sample(mentions, args.sample_size, seed=args.seed)
    print(f"  Sampled {len(sample)} for review (stratified by sentiment)")

    print(f"Re-classifying {len(sample)} mentions with Claude …")
    classified = reclassify_batch(sample)
    print("  Classification complete.")

    report = build_report(sample, classified)
    print_summary(report)

    args.output.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = args.output / f"qa_report_{ts}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Full report saved → {out_path}\n")

    return 0 if report["classifier_healthy"] else 1


if __name__ == "__main__":
    sys.exit(main())
