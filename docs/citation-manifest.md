# Citation Manifest

Use a citation manifest when review comments rely on related work, novelty comparisons, prior systems, external benchmarks, venue policy, or web-search results.

The manifest exists to keep source provenance auditable. It is not a requirement to browse the web. Offline mode remains valid when it is limited to the submitted paper, the paper's reference list, reviewer knowledge explicitly labeled as such, and user-provided context.

## Artifact Path

```text
review_artifacts/<paper_id>/citation_manifest.md
```

Reference the evidence manifest near the top:

```markdown
Evidence manifest: `review_artifacts/<paper_id>/evidence_manifest.json`
```

## Format

```markdown
# Citation Manifest

Evidence manifest: `review_artifacts/<paper_id>/evidence_manifest.json`

## Source Inventory
- S1: [Title, system name, policy page, or short source name]
  - Origin: submitted paper | paper reference list | reviewer knowledge | web search | user-provided context
  - Location or link: [section, reference number, URL, file path, or "not available"]
  - Used for: [novelty, baseline comparison, factual background, venue fit, and so on]

## External Claims Used in Review
- Claim: [...]
  - Source id: S1
  - Review section: [...]
  - Provenance: submitted paper | paper reference list | reviewer knowledge | web search | user-provided context

## Citation Sanity Check
- No invented bibliographic details: yes/no
- No unused manifest sources: yes/no
- No unsupported related-work claims: yes/no
- Search-derived claims have links or source notes: yes/no/not applicable
- Offline limitations, if any: [...]
```

## Provenance Categories

- Submitted paper: evidence from the paper text, figures, tables, equations, appendix, or supplement.
- Paper reference list: bibliographic entries or claims traceable to references cited by the paper.
- Reviewer knowledge: prior knowledge not newly verified during this review; label it cautiously.
- Web search: source found through search or browsing; include a link or source note.
- User-provided context: files, links, notes, or constraints provided by the user.

## Web Search Guidance

Use web search only when requested, when current external context is necessary, or when the review would otherwise make unstable claims about related work or venue policy. Search-derived claims must be linked or otherwise auditable.

Do not use search to pad the review with generic background. Prefer targeted checks for novelty, baseline availability, benchmark/tool status, venue policy, or disputed factual claims.

## Final Sanity Check

Before finalizing `final_review.md`, check that:

- every external related-work claim maps to a manifest source,
- no source is listed but unused,
- no bibliographic details are invented,
- reviewer-knowledge claims are labeled as such,
- offline limitations are stated when search was not used.

## Example Source Notes

Likely sources to track include:

- systems, datasets, benchmarks, tools, or prior work cited by the paper,
- venue area or review-form requirements from the provided review form,
- any web-search result used to verify whether a baseline, standard, tool, or venue policy is current.
