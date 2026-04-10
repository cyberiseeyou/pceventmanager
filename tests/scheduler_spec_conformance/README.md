# Scheduler Spec Conformance Tests

Every test in this directory corresponds to a branch in the spec files at
`docs/superpowers/specs/2026-04-10-scheduler-rewrite/`. Test names follow
the convention `test_<branch_id>_<description>` so that a spec→test coverage
matrix can be built automatically.

## Running

```bash
# Full conformance suite
pytest tests/scheduler_spec_conformance/ -v

# Single category
pytest tests/scheduler_spec_conformance/test_02_juicer_production.py -v

# Single branch
pytest tests/scheduler_spec_conformance/test_02_juicer_production.py::test_jp7 -v
```

## Invariants

Every test MUST:
- Use `spec_assert.exact_assignment(...)` or `spec_assert.manual_review(...)` to
  verify outcomes. Do not use `assert ... in ...` or other fuzzy assertions.
- Use fixed dates from `future_date(N)` rather than `datetime.now()`.
- Reference the spec branch ID in its docstring (e.g., `"""Spec branch JP7: ..."""`).
