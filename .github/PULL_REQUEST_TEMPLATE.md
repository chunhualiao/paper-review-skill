# Pull Request

## Summary
<!-- Brief description of what this PR changes and why. -->

## Related issue
<!-- "Closes #N", "Refs #N", or link to the issue this addresses. -->
Closes #

## Type of change
- [ ] Bug fix
- [ ] Documentation
- [ ] Enhancement / new feature
- [ ] Breaking change

## Validation
<!-- Run these from the repo root before requesting review. Check what you ran. -->
- [ ] `python3 -m pip install -e ".[dev]"`
- [ ] `python3 scripts/validate_skill_evals.py`
- [ ] `python3 scripts/regression_test_review_fixtures.py`
- [ ] `python3 -m coverage run -m unittest discover -s tests` && `python3 -m coverage report -m`
- [ ] `python3 scripts/smoke_test_review_scripts.py`
- [ ] Bot review audit comment posted with `scripts/record_pr_review_audit.sh` before merge
- [ ] Not applicable (non-code change)

## Notes
<!-- Anything reviewers should pay attention to, or follow-up work. -->
