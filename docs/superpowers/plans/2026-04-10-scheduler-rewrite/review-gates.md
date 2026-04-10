# Review Gates — 2026-04-10 Scheduler Rewrite

> Every plan task in this directory passes through a subset of these 5 gates. A gate is a fresh subagent dispatch with a specific prompt. The gate's output is stored in the plan file as a PR comment or inline checklist update before the next step proceeds.

## Gate A — Spec Verification

**When:** Once per spec file, before any corresponding plan work begins.
**Who:** Fresh `Explore` subagent (or `general-purpose` if Explore is unavailable).
**Duration:** ~5 minutes subagent time.

**Purpose:** Ensure the spec file faithfully reproduces the source image. Catches transcription errors, dropped branches, and paraphrase drift.

**Prompt template:**

```
You are performing a spec-verification review. Do NOT write code or modify files.

Task: Compare the spec file at `docs/superpowers/specs/2026-04-10-scheduler-rewrite/<N>-<name>.md` against the source image it transcribes.

The source image is image <N> of 7 in the conversation that produced this spec set. The image is the sole authority — if the spec file and the image disagree, the spec file is wrong.

Read the spec file in full. Then list, for each rule and branch drawn in the image:
1. Whether the rule appears in the spec file (PASS / MISSING / DRIFTED)
2. If DRIFTED, quote both the image's exact wording and the spec's exact wording
3. If MISSING, quote the image's exact wording

Also confirm these structural requirements are satisfied in the spec file:
- Has a "Verbatim spec" section that transcribes the image
- Has Inputs / Outputs / Pre-conditions / Post-conditions / Branches / Edge cases / Do NOT / Traceability table sections
- Branches are numbered (e.g., JP1, JP2, ...)
- Every branch appears in the Traceability table

Report format:
  STATUS: PASS | FAIL
  Rules checked: <n>
  Rules PASS: <n>
  Rules MISSING: <n> (list)
  Rules DRIFTED: <n> (list with quoted diffs)
  Structural requirements: PASS | FAIL (which missing)
  Recommendation: <one sentence>

Keep the report under 600 words.
```

**Pass criteria:** 100% of image rules present in spec file, no drift, all structural requirements met.

**On fail:** The spec file must be updated to address every missing/drifted rule. Gate A is re-run. The plan file that depends on this spec cannot start until Gate A passes.

## Gate B — Pre-Implementation Audit

**When:** Once per plan file, before Task 1 runs.
**Who:** Fresh `Explore` subagent.
**Duration:** ~10 minutes subagent time.

**Purpose:** Build a "preserve vs change" punch list of every existing behavior in the affected code, so the refactor doesn't silently break features that aren't in the spec but are valuable in practice.

**Prompt template:**

```
You are performing a pre-implementation audit. Do NOT write code.

Context: I am about to refactor <file path> to match the spec in `docs/superpowers/specs/2026-04-10-scheduler-rewrite/<N>-<name>.md`. Before I start, I need a complete inventory of the current behavior in the affected code paths.

Read these files in full:
1. The spec file: `docs/superpowers/specs/2026-04-10-scheduler-rewrite/<N>-<name>.md`
2. The current code file(s): <list the specific files the plan touches>
3. Any test files that currently exercise this code: <list test files>

Produce a punch list with three sections:

### IN SPEC AND IN CODE (to preserve as-is)
List every behavior that both the spec describes AND the current code implements. For each, cite the code line and the spec section. These need no change.

### IN SPEC BUT NOT IN CODE (to add)
List every spec branch/rule that the current code does NOT implement. Cite the spec section.

### IN CODE BUT NOT IN SPEC (decision required)
List every behavior that the current code implements but the spec does NOT mention. For each, provide:
- Code location (file:line range)
- 1-sentence description of what it does
- Your assessment: IS_SAFETY_RAIL (preserve), LEGACY_DEAD_CODE (remove), UNDOCUMENTED_FEATURE (needs spec update), or UNKNOWN (flag for human review)

Report format:
  STATUS: COMPLETE | BLOCKED
  In spec and in code: <count>
  To add: <count, with spec section references>
  To preserve (safety rails): <count, with code refs>
  To remove (dead code): <count, with code refs>
  Undocumented features needing spec update: <count>
  Items needing human review: <count, with code refs>
  Recommendation: <one sentence>

Keep the report under 1000 words.
```

**Pass criteria:** All items categorized. No UNKNOWN items (they must be escalated to a human for classification).

**On fail:** Human reviews UNKNOWN items, updates the plan with an explicit decision per item, re-runs Gate B.

## Gate C — Plan Coverage Review

**When:** Once per plan file, after it is written and before Task 1 runs.
**Who:** Fresh `Explore` subagent.
**Duration:** ~5 minutes subagent time.

**Purpose:** Ensure every branch in the spec's traceability table has a corresponding plan task, and every plan task references a real branch.

**Prompt template:**

```
You are performing a plan-coverage review. Do NOT write code.

Context: The plan file `docs/superpowers/plans/2026-04-10-scheduler-rewrite/<N>-<name>.md` implements the spec at `docs/superpowers/specs/2026-04-10-scheduler-rewrite/<N>-<name>.md`. I need you to verify that every branch in the spec has a task in the plan, and every plan task references a real branch.

Read both files in full.

Produce a coverage matrix:

### Spec branches → Plan tasks
For every branch ID in the spec file's "Branches" section and its traceability table:
| Branch ID | Spec description | Plan task ID | Plan task description | Status |
  where Status is COVERED, MISSING (no plan task), or MISREFERENCED (plan task points to a different branch).

### Plan tasks → Spec branches
For every task ID in the plan file:
| Plan task ID | Description | Spec branch(es) referenced | Status |
  where Status is VALID (branch exists in spec), INVALID (branch doesn't exist), or NO_REFERENCE (plan task doesn't reference any branch — this is a warning, not necessarily fatal for infrastructure tasks).

Report format:
  STATUS: PASS | FAIL
  Spec branches total: <n>
  Spec branches covered: <n>
  Spec branches MISSING: <n> (list)
  Plan tasks total: <n>
  Plan tasks VALID: <n>
  Plan tasks INVALID: <n> (list)
  Plan tasks with no reference: <n> (list, informational)
  Recommendation: <one sentence>

Keep the report under 800 words.
```

**Pass criteria:** No MISSING spec branches, no INVALID plan task references.

**On fail:** Plan file is updated to add missing tasks and fix invalid references. Gate C re-runs.

## Gate D — Implementation Drift Review

**When:** After each plan task commits, before the next plan task starts.
**Who:** Fresh `general-purpose` subagent.
**Duration:** ~3 minutes subagent time.

**Purpose:** Ensure the implementation matches what the spec and plan prescribed — no extras, no omissions.

**Prompt template:**

```
You are performing an implementation-drift review. Do NOT write code.

Context: Plan task <T-id> in `docs/superpowers/plans/2026-04-10-scheduler-rewrite/<N>-<name>.md` was just completed. The commit is the most recent one on the current branch. I need you to verify the implementation matches the plan task and the spec.

Read:
1. The plan task section for <T-id>: the code blocks, the test, the commit message.
2. The git diff of the most recent commit: `git show HEAD --stat && git show HEAD`
3. The corresponding spec section: `docs/superpowers/specs/2026-04-10-scheduler-rewrite/<N>-<name>.md`, specifically branches cited in the task.

Produce a drift report:

### Implementation fidelity
- Does the code in the commit match the code shown in the plan task? (Line-by-line; minor formatting differences are OK.)
- Does the test match the test shown in the plan task?
- Does the code implement the spec branch cited? Cite the exact branch ID.

### Scope creep detection
- Does the commit modify files NOT mentioned in the plan task's "Files" section? If yes, list them and describe the unexpected change.
- Does the commit add functionality not described in the spec branch? If yes, describe.
- Does the commit introduce new dependencies (imports, libraries, env vars)? If yes, list.

### Omission detection
- Are any Do-NOTs from the spec violated?
- Are any invariants from the plan README (Safety invariants section) violated?

Report format:
  STATUS: PASS | FAIL | WARN
  Plan task: T-<id>
  Spec branch(es) cited: <list>
  Fidelity: matches / deviates (with quoted diff)
  Scope creep: none / <list>
  Omissions: none / <list>
  Do-NOTs violated: none / <list>
  Recommendation: <one sentence>

Keep the report under 600 words.
```

**Pass criteria:** STATUS = PASS. WARN may proceed with a noted caveat.

**On fail:** The most recent commit is reverted (`git reset --hard HEAD~1`). The task is redone with a subagent that is briefed on the specific drift. Gate D re-runs.

## Gate E — Test Adequacy Review

**When:** After all test tasks for a plan file are written.
**Who:** Fresh `Explore` subagent.
**Duration:** ~5 minutes subagent time.

**Purpose:** Ensure every spec branch in the plan's scope has a passing test, and every test asserts a real spec rule.

**Prompt template:**

```
You are performing a test-adequacy review. Do NOT write code.

Context: Plan `docs/superpowers/plans/2026-04-10-scheduler-rewrite/<N>-<name>.md` has completed all its implementation tasks. The tests are now in `tests/scheduler_spec_conformance/test_<N>_*.py`. I need you to verify that every spec branch has a test, and every test asserts what the spec says.

Read:
1. The spec file: `docs/superpowers/specs/2026-04-10-scheduler-rewrite/<N>-<name>.md`
2. The test file(s) for this spec: `tests/scheduler_spec_conformance/test_<N>_*.py`

Produce a spec-to-test coverage matrix:

### Branch → Test mapping
For every branch ID in the spec file:
| Branch ID | Spec description | Test function | Assertion check | Status |
  where Status is:
  - PASS (test exists, assertion correctly verifies the branch)
  - PARTIAL (test exists but assertion is too weak — e.g., only checks success, not the specific outcome)
  - MISSING (no test for this branch)
  - WRONG (test exists but asserts the wrong thing)

### Test-to-branch back-reference
For every test function in the test file:
| Test function | Spec branches claimed | Actual spec branches covered | Status |

### Determinism check
For each test, confirm:
- The test uses a fixed input (no randomness, no wall-clock time without freezing).
- The test asserts a specific outcome (a specific employee_id, a specific datetime, a specific failure_reason).
- The test does NOT use >= or <= comparisons where = would work.

Report format:
  STATUS: PASS | FAIL
  Spec branches total: <n>
  Branches PASS: <n>
  Branches PARTIAL: <n> (list with recommendations)
  Branches MISSING: <n> (list with spec section references)
  Branches WRONG: <n> (list with recommendations)
  Non-deterministic tests: <n> (list)
  Recommendation: <one sentence>

Keep the report under 800 words.
```

**Pass criteria:** 0 MISSING, 0 WRONG, 0 non-deterministic tests.

**On fail:** The test file is updated to add/fix tests. Gate E re-runs.

## Gate execution recap

| Step | Gate | Blocking? |
|---|---|---|
| Spec file written | Gate A | Yes — no plan work starts |
| Plan file written | Gate B (audit) + Gate C (coverage) | Yes — no implementation starts |
| Each plan task committed | Gate D (drift) | Yes — next task cannot start |
| All test tasks completed | Gate E (adequacy) | Yes — no PR merge |
| PR opened | All gates passed | Merge allowed |

## How to dispatch a gate

From the main conversation, use the Agent tool with `subagent_type=Explore` (or `general-purpose` for Gate D). Paste the relevant prompt template, substituting the `<N>-<name>` placeholders. Store the subagent's response in a comment in the plan file (inline, next to the task that triggered the gate). Do not delete the response — it is the audit trail.

## Time budget per gate

| Gate | Budget | Notes |
|---|---|---|
| A | 5 min | Per spec file; 9 files × 5 min = 45 min total up front |
| B | 10 min | Per plan file; 10 plan files × 10 min = 100 min total up front |
| C | 5 min | Per plan file; 10 × 5 = 50 min total up front |
| D | 3 min | Per task; ~150 tasks × 3 = 7.5 hours over the life of the project |
| E | 5 min | Per plan file; 10 × 5 = 50 min total |

Total gate budget: ~10 hours of subagent time over the life of the refactor. Fast for the guarantees it provides.
