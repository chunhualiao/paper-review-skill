# SC/Linklings Review Adapter

Use this adapter when converting a canonical Markdown review into an SC or Linklings offline review form.

The Markdown review remains the source artifact. Do not draft directly in the offline form first; doing so tends to scatter evidence and makes HTML rendering harder.

## Source Sections

Use these canonical Markdown sections:

```text
# Paper Review: [Title]
## Summary
## Motivation and Positioning
## Contributions
## How the Proposed Approach Works End to End
## Technical Soundness
## Costs vs. Benefits
## Evaluation Assessment
## Writing and Presentation
## Strengths
## Weaknesses
## Questions for Authors
## Minor Issues
## Venue-Specific Recommendations
## Overall Assessment
## Top Actions - Start Here
## Confidence
```

`Top Actions - Start Here` is for author-facing triage and should stay in the Markdown and HTML review. It usually does not map to a single SC form field; fold the highest-priority items into the appropriate summary, rebuttal, or detailed-comments fields.

## Example Workflow

1. Draft the canonical Markdown review as `review_comments.md`.
2. Keep `Top Actions - Start Here` in the Markdown review for author-facing triage.
3. Render the same Markdown file to `review_artifacts/<paper_id>/<paper_id>_review_comments.html` with `scripts/render_review_html.py`.
4. Copy the canonical sections into the offline review form using the field mapping below.
5. Select rating fields in the offline form only after the written critique and recommendation rationale are internally consistent.

## Field Mapping

### Summary and High Level Discussion

Use:

- `Summary`
- `Motivation and Positioning`
- `Contributions`
- the final verdict from `Overall Assessment`
- a short statement of why the work matters for the SC area

Keep this field high-level. It should identify the topic, contribution, importance, and main reason for the recommendation.

### Strengths

Use:

- `Strengths`
- any positive evidence from `How the Proposed Approach Works End to End`
- any positive venue-fit evidence from `Venue-Specific Recommendations`

Keep each strength specific. Prefer evidence-backed claims such as "the evaluation covers X devices" over generic praise.

### Weaknesses

Use:

- `Weaknesses`
- `Technical Soundness`
- `Evaluation Assessment`
- cost or missing-evidence concerns from `Costs vs. Benefits`

Separate major weaknesses from minor presentation issues. Minor issues usually belong in `Detailed Comments for Authors`.

### Comments for Rebuttal

Use:

- `Questions for Authors`
- the one or two highest-impact unresolved issues from `Weaknesses`
- the most important unresolved evidence gaps from `Technical Soundness` or `Evaluation Assessment`

This field is author-visible and rebuttal-limited. Ask direct questions that the authors can answer with evidence, clarification, or corrected claims. Avoid listing every minor issue here.

### Detailed Comments for Authors

Use:

- `Technical Soundness`
- `Evaluation Assessment`
- `Writing and Presentation`
- `Minor Issues`
- important evidence from `How the Proposed Approach Works End to End`
- important evidence from `Costs vs. Benefits`

This is the place for technical detail, organization comments, reproducibility requests, table/figure issues, and suggested revisions.

### Rating Fields

Use `Overall Assessment`, `Venue-Specific Recommendations`, `Technical Soundness`, and `Evaluation Assessment` to select the form options and preserve the reasoning. For SC forms, typical fields include:

- Relevance
- Technical Soundness
- Technical Importance
- Originality
- Quality of Presentation
- Recommended Action
- Level of confidence in your recommendation
- Level of your expertise in the relevant area

Each selected rating should be consistent with the written critique. If the written review says the work has major unsupported claims, do not assign a high technical soundness rating without explaining why those issues are non-fatal.

## SC Drafting Checklist

- Keep all Linklings metadata and question markers unchanged.
- Remove `//` only from the selected multiple-choice options.
- Paste prose only into text-response blanks.
- Preserve Markdown formatting when helpful; Linklings supports Markdown notation.
- Verify the uploaded review is parsed as expected after submission.
- If the canonical review is scoreless, add ratings only when the SC form requires them.

## Example Rendering Command

After drafting the canonical Markdown review, render the same file to HTML:

```bash
python3 scripts/render_review_html.py \
  --review-md review_comments.md \
  --paper /path/to/private/paper.pdf \
  --output review_artifacts/<paper_id>/<paper_id>_review_comments.html \
  --title "Paper Review"
```
