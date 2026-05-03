Run a QA review of the sentiment classifier to verify that Brandwatch and Claude labels agree, and flag any mentions that need reclassification.

## What this command does

1. **Run the review script** against the latest Brandwatch CSV.
2. **Read the JSON report** it produces in `data/qa_reports/`.
3. **Summarise the findings** in a structured way.
4. **Recommend actions** if problems are found.

---

## Step 1 — run the audit

```bash
python skills/review_classifier.py
```

If a specific CSV or sample size is needed, pass flags:
```bash
python skills/review_classifier.py --csv data/brandwatch/mentions_apr2026.csv --sample-size 75
```

---

## Step 2 — read the report

Find the most recent file in `data/qa_reports/` (highest timestamp) and read its JSON contents.

---

## Step 3 — produce a structured summary

Report on:

### Overall Health
- Agreement rate, minor disagreement rate, major disagreement rate
- Classifier healthy (true/false) — threshold is < 15 % major disagreement

### Platform Breakdown
- Which platforms have the highest disagreement counts
- Call out any platform-floor violations (Reddit / TrustPilot / BrokersView mentions that BW labelled non-negative but Claude labelled negative — these are under-escalated and should be minimum L3)

### Reclassification Recommendations
For each mention in `reclassify_recommended`:
- Show: platform, BW label → Claude label, engagement count
- Show: a snippet of the text
- Show: Claude's sentiment reasoning
- State clearly whether to accept the reclassification

### Systematic Patterns
Look across all disagreements and call out any patterns, e.g.:
- "Claude consistently reads BW-neutral signal posts as positive"
- "BW over-labels forex signal tweets as neutral; Claude agrees — no action needed"
- "X% of BW-negative mentions are seen as neutral by Claude — possible prompt calibration needed"

### Verdict
End with one of:
- **HEALTHY** — classifier is working well, no action needed
- **MINOR DRIFT** — a few borderline cases, monitor next cycle
- **REVIEW SYSTEM PROMPT** — systematic disagreement, the classifier's rules may need adjusting

---

## Step 4 — if action is required

If major disagreement rate ≥ 15 %:
- Open `skills/reclassify_mentions.py` and review `_SYSTEM`
- Identify which sentiment or risk-tier rule is misfiring
- Propose a concrete wording change
- Do NOT change the prompt unilaterally — present the proposed change and ask for approval first
