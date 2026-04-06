# Gangoos-coder — Master Execution Index

## Purpose

This file is the operator index for the rebuild.
It defines the order in which documents should be consumed and the exact execution flow for the project.

This index is not optional.
If an engineer starts implementation without following this order, scope creep and false completeness will return.

---

## Canonical Document Order

### Phase 0 baseline
1. `docs/project/01_AUDIT_ERRORS_AND_BLOCKERS.md`
2. `docs/project/02_ENGINEERING_RULES_AND_TEST_GATES.md`
3. `docs/project/03_PHASED_COPY_TO_ORG_POLICY.md`

### Phase execution plans
4. `docs/project/04_PHASE_1_CI_AND_PACKAGING_PLAN.md`
5. `docs/project/05_PHASE_2_CONTRACT_REPAIR_PLAN.md`
6. `docs/project/06_PHASE_3_REMOTE_QWEN_RUNTIME_PLAN.md`
7. `docs/project/07_PHASE_4_SECURITY_AND_CONFIG_SCRUB_PLAN.md`
8. `docs/project/08_PHASE_5_RELEASE_GATES_AND_SMOKE_TESTS.md`
9. `docs/project/09_PHASE_6_ORG_MIGRATION_AND_RC_RELEASE_PLAN.md`
10. `docs/project/10_PHASE_7_POST_V1_ROADMAP.md`

### Handoff and coordination docs
11. `docs/project/12_NEW_CHAT_HANDOFF_AND_CANVAS_PROMPT.md`
12. `docs/project/13_CODEX_CLI_GLOBAL_EXECUTION_RULES.md`

---

## Execution Rules

1. No phase may begin before the previous phase meets its exit criteria.
2. One PR per phase or sub-phase.
3. Minimum six tests/checks per PR.
4. No merge on red CI.
5. No release tag before Phases 0-6 are satisfied.
6. No Phase 7 work may block Phase 1-6 completion.
7. Docs and runtime must be updated together.
8. Every bugfix requires a regression test.

---

## Suggested Work Sequence

### Step 1 — establish truth
Read:
- audit
- engineering rules
- phased policy

Output:
- agreed baseline
- no more false “done” claims
- issue/PR mapping for each critical blocker

### Step 2 — Phase 1 implementation
Use:
- `04_PHASE_1_CI_AND_PACKAGING_PLAN.md`

Output:
- trustworthy CI
- reproducible root-level test/boot path

### Step 3 — Phase 2 implementation
Use:
- `05_PHASE_2_CONTRACT_REPAIR_PLAN.md`

Output:
- truthful `CodeAct -> NEXUS -> mojo_exec` contract

### Step 4 — Phase 3 implementation
Use:
- `06_PHASE_3_REMOTE_QWEN_RUNTIME_PLAN.md`

Output:
- supported `VM1 -> VM2` remote Qwen runtime

### Step 5 — Phase 4 implementation
Use:
- `07_PHASE_4_SECURITY_AND_CONFIG_SCRUB_PLAN.md`

Output:
- clean public baseline
- stable env/config contract

### Step 6 — Phase 5 implementation
Use:
- `08_PHASE_5_RELEASE_GATES_AND_SMOKE_TESTS.md`

Output:
- release candidate gates
- compose and runtime smoke coverage

### Step 7 — Phase 6 implementation
Use:
- `09_PHASE_6_ORG_MIGRATION_AND_RC_RELEASE_PLAN.md`

Output:
- safe org mirror
- protected branch baseline
- RC promotion policy

### Step 8 — Phase 7 roadmap
Use:
- `10_PHASE_7_POST_V1_ROADMAP.md`

Output:
- controlled post-v1 expansion

---

## PR Naming Convention

Recommended pattern:
- `phase-1/ci-packaging-baseline`
- `phase-2/contract-repair`
- `phase-3/remote-qwen-runtime`
- `phase-4/config-scrub`
- `phase-5/release-gates`
- `phase-6/org-migration`
- `phase-7/post-v1-roadmap`

---

## Review Discipline

Every PR must include:
- scope
- changed files and why
- acceptance criteria
- six test/check results
- manual verification summary if applicable
- explicit statement of what the PR does **not** do

---

## Final Release Rule

`v1.0.0` means:
- Phase 0-6 complete
- required checks green
- docs truthful
- minimum product path proven
- org-side validation green
- no open critical blockers

Anything less is not `v1.0.0`.

---

## Definition of Done

This index is done when it remains accurate.
Any future phase addition or execution-policy change must update this file in the same PR.
