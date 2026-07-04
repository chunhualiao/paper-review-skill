# Numerical and Consistency Checks

Use this convention when review comments depend on quantitative claims, tables, figures, equations, device coverage, baselines, or reported improvements.

The goal is not to require code execution. The goal is to make numerical criticisms auditable and to distinguish verified arithmetic from reviewer judgment.

## Artifact Path

Store check notes and any code snippets in:

```text
review_artifacts/<paper_id>/checks/numerical_checks.md
```

Reference the evidence manifest near the top:

```markdown
Evidence manifest: `review_artifacts/<paper_id>/evidence_manifest.json`
```

## Check Format

```markdown
# Numerical and Consistency Checks

Evidence manifest: `review_artifacts/<paper_id>/evidence_manifest.json`

## Scope
- Claims/tables/figures/equations checked:
- Paper sections or pages:

## Verified Arithmetic
- V1: Source values: ...
  Formula or method: ...
  Computed result: ...
  Paper result: ...
  Status: matches | mismatch | cannot verify

## Consistency Findings
- C1: Location A says ...
  Location B says ...
  Concern:

## Reviewer Judgment
- J1: Interpretation:
  Evidence:
  Why this matters:

## Code or Manual Method
- Tool or manual process:
- Code snippet or command, if used:

## Limitations
- Missing raw data, unreadable figure, absent confidence intervals, no code execution, or other limits:
```

## What to Check

- Speedups and slowdowns.
- Percentages and retained-performance claims.
- Averages, geometric means, and aggregation choices.
- Confidence intervals, variance, sample sizes, and repeated-run claims.
- Table, figure, and text consistency.
- Device, workload, dataset, browser, driver, baseline, and result accounting.
- Internal references, unresolved citations, acronym definitions, and terminology drift.

## Code Execution

Code execution is optional. Use it when calculations are repeated, arithmetic is nontrivial, or the paper provides enough raw values to reproduce a claim.

When code execution is unavailable or unnecessary, write the manual calculation or inspection method. Do not imply that a calculation was executed if it was only inspected manually.

## Final Review Use

Quantitative criticisms in `final_review.md` should cite either:

- a paper anchor such as a section, page, table, figure, equation, or appendix item, or
- `review_artifacts/<paper_id>/checks/numerical_checks.md`.

Keep these categories distinct:

- Verified arithmetic: recomputed or directly checked.
- Consistency finding: mismatch across paper locations or artifacts.
- Reviewer judgment: interpretation of why the quantitative issue matters.

## Priority Examples

When applicable, prioritize:

- Resource, dataset, workload, and configuration consistency across claims and reported tables.
- Baseline comparison decomposition, especially whether multiple improvements are mixed in a single result.
- Support for headline component-level and end-to-end improvement claims.
- Variance, repeated-run, and confidence-interval reporting gaps.
- Whether implementation-specific claims are supported by enough evaluation detail.
