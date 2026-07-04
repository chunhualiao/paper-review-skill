# Independent Quality Critic

Use the quality critic after drafting `final_review.md` and before rendering final HTML or submitting an SC/Linklings form. The critic evaluates the review, not the paper.

The critic should not introduce new paper claims. It should identify whether the review is complete, evidence-grounded, internally consistent, appropriate, and ready to render or submit.

## Artifact Paths

Required:

```text
review_artifacts/<paper_id>/quality_report.md
```

Optional:

```text
review_artifacts/<paper_id>/quality_report.json
```

## Markdown Format

```markdown
# Review Quality Report

Evidence manifest: `review_artifacts/<paper_id>/evidence_manifest.json`
Reviewed artifact: `review_artifacts/<paper_id>/final_review.md`

## Summary
[ready | ready with low-severity issues | blocked pending fixes]

## Findings
- Q1:
  - Severity: high | medium | low
  - Category: missing required section | unsupported or vague claim | identity leakage | biased or inappropriate wording | evidence-rating mismatch | generic prose | broken Markdown/HTML structure
  - Location:
  - Issue:
  - Required action:

## High-Severity Gate
- High-severity findings fixed: yes/no/not applicable
- Overrides: [explicit rationale for any high-severity issue not fixed]
```

## What to Check

- Missing required canonical sections.
- Unsupported factual claims or claims without paper anchors.
- Vague weaknesses that are not actionable.
- Missing or weak rebuttal questions.
- Reviewer identity leakage or confidential metadata that should not appear in author-facing text.
- Biased, dismissive, inflammatory, or inappropriate wording.
- Mismatch between critique severity and ratings or recommendation.
- Generic LLM-style prose that does not reflect the specific paper.
- Broken Markdown structure, malformed lists, or likely HTML rendering problems.
- Missing references to required artifacts such as evidence, numerical, citation, or self-critique reports when they are used.

## Severity Guidance

High severity:

- unsupported major criticism,
- hidden or invented evidence,
- identity leakage in author-facing text,
- ratings/recommendation contradict the critique,
- missing required form section,
- broken structure that would make the review unusable.

Medium severity:

- vague but fixable weakness,
- missing citation for a secondary claim,
- overly broad conclusion,
- unclear rebuttal question,
- minor section mismatch.

Low severity:

- wording polish,
- minor Markdown cleanup,
- redundant sentence,
- non-blocking organization improvement.

## Gate Rule

High-severity findings must be fixed or explicitly overridden before final HTML rendering or form submission. Overrides should state why the issue is acceptable and who made that judgment.

## Optional JSON Shape

```json
{
  "status": "ready | ready_with_low_severity_issues | blocked_pending_fixes",
  "reviewed_artifact": "review_artifacts/<paper_id>/final_review.md",
  "findings": [
    {
      "id": "Q1",
      "severity": "high",
      "category": "unsupported or vague claim",
      "location": "Weaknesses W2",
      "issue": "...",
      "required_action": "..."
    }
  ],
  "high_severity_gate": {
    "fixed": false,
    "overrides": []
  }
}
```
