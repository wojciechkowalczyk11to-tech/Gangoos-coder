# Phase 6 — Organization Migration and Release Candidate Plan

## Status

Phase 6 exists to move a stabilized repository into the organization without importing chaos as the new baseline.

Mirroring or copying into an organization repo is not a repair strategy.
It is a publication step that must occur **after** quality gates have already been met.

---

## Preconditions

Phase 6 must not start unless all of the following are true:

1. Phase 0 documents exist and are current
2. Phase 1 CI/package baseline is green
3. Phase 2 contract truth is fixed
4. Phase 3 remote runtime policy is supported
5. Phase 4 config hygiene is clean
6. Phase 5 release gates and smoke tests are passing

If any of the above are false, migration is premature.

---

## Scope of Phase 6

This phase must implement only the following classes of work:

1. repository mirror/copy procedure
2. organization secrets and variables setup
3. branch protection enablement
4. initial organization-side CI validation
5. release candidate tagging process
6. rollback/abort policy if org baseline is unhealthy

This phase must **not**:

- rewrite product code unrelated to migration
- introduce new features
- weaken checks for the organization copy
- tag final release before organization validation succeeds

---

## Deliverables

### D1. Migration runbook
A step-by-step, reproducible procedure to move the repository.

### D2. Organization bootstrap checklist
A checklist for required secrets, variables, branch rules, and workflow setup.

### D3. Organization-side green build
The mirrored repo must pass the same required checks in the organization.

### D4. Release candidate procedure
A defined path for `v1.0.0-rc1`.

### D5. Final release promotion rule
A defined path from RC to final `v1.0.0`.

### D6. Abort and rollback policy
If the org mirror is unhealthy, promotion must stop.

---

## Required Design Decisions

### Decision D1 — mirror strategy

Choose and document one:
- clean mirror preserving history
- filtered copy preserving selected history
- fresh repo with curated import and explicit baseline commit

The choice must match your governance goals.

### Decision D2 — protected branch policy from first day

Document:
- protected default branch
- required checks
- merge strategy
- admin bypass policy
- tag creation policy

### Decision D3 — RC promotion rule

At minimum:
- `v1.0.0-rc1` only after first green org build
- `v1.0.0` only after post-mirror validation and no critical regressions

---

## Required File-Level Changes

Possible artifacts include:
- migration runbook docs
- org setup docs
- release checklist docs
- issue templates or PR templates if needed
- governance docs referencing protected branch policy

---

## Implementation Rules

1. Do not copy the repo into org before gates are green.
2. Do not create `v1.0.0` from the pre-org baseline.
3. Do not rely on undocumented org secrets or tribal knowledge.
4. Every required secret/variable must be named and scoped.
5. Branch protection must be enabled before normal development resumes in org.
6. RC tags must map to a green commit only.
7. Final release must require successful org-side validation.
8. Keep this PR/document set focused on migration and RC policy only.
9. Document rollback steps explicitly.
10. Treat org as the new public source of truth only after validation.

---

## Required Acceptance Criteria

### AC1. Migration runbook exists
Another engineer can perform the migration from docs.

### AC2. Org bootstrap checklist exists
Secrets, variables, workflows, and branch settings are documented.

### AC3. Org-side validation policy exists
The same gates used pre-org are required post-mirror.

### AC4. RC and final release rules exist
Tagging semantics are explicit and non-ceremonial.

### AC5. Abort policy exists
Migration or promotion stops if quality gates fail.

### AC6. No scope creep
No unrelated product changes in this phase.

---

## Six Mandatory Tests / Checks For This Phase

### T1. Migration dry-run checklist check
Purpose:
Verify the migration runbook is complete and executable.

### T2. Secrets/variables completeness check
Purpose:
Verify all required org-side variables/secrets are documented.

### T3. Branch protection mapping check
Purpose:
Verify documented required checks correspond to real workflow jobs.

### T4. Org-side CI validation check
Purpose:
Verify first org build criteria are defined and reproducible.

### T5. RC tagging precondition check
Purpose:
Verify RC cannot be cut without a green org baseline.

### T6. Rollback/abort policy check
Purpose:
Verify unhealthy org migration has a documented stop path.

---

## Required Verification Output In The PR Body

Codex must include:
- migration runbook summary
- list of required org secrets/variables
- branch protection mapping summary
- RC promotion checklist summary
- rollback policy summary
- explicit statement that no final `v1.0.0` is allowed before green org validation

---

## Suggested PR Title

```text
phase-6: define org migration runbook and release-candidate promotion policy
```

---

## Suggested PR Body Template

```md
## What this PR does
- documents how to migrate the stabilized repo to the organization
- defines organization bootstrap requirements
- defines protected-branch and required-check expectations
- defines `v1.0.0-rc1` and `v1.0.0` promotion rules
- defines rollback/abort policy for unhealthy migration

## What this PR does not do
- no product feature work
- no code redesign
- no release shortcuts
- no final tag from an unvalidated org baseline

## Migration decisions
- migration strategy: <describe>
- protected branch: <name>
- required checks: <list>
- RC rule: <describe>
- final release rule: <describe>

## Verification
- [ ] migration runbook is complete
- [ ] org secret/variable checklist is complete
- [ ] branch protection mapping is complete
- [ ] RC preconditions are explicit
- [ ] rollback/abort policy is explicit

## Notes
- confirm no final tag before green org build
- list exact docs changed and why
```

---

## Codex CLI Task Prompt

```text
You are implementing Phase 6 of a strict rebuild.

Mission:
Define how the stabilized repository is migrated into the organization and how the first release candidate is promoted safely.

Primary goals:
1. Create a migration runbook
2. Define required organization secrets and variables
3. Define branch protection and required checks for the org repo
4. Define org-side validation requirements
5. Define `v1.0.0-rc1` and `v1.0.0` promotion rules
6. Define rollback/abort policy if org validation fails

Constraints:
- no TODOs
- no placeholders
- no product feature work
- no release shortcuts
- no final tag before successful org-side validation
- no undocumented secret requirements

Implementation rules:
- treat migration as publication, not repair
- map required checks to actual workflows
- document all org bootstrap requirements explicitly
- define one RC rule and one final release rule
- document rollback steps if org validation is unhealthy

Mandatory acceptance criteria:
- migration runbook exists
- org bootstrap checklist exists
- org-side validation policy exists
- RC and final release rules exist
- rollback/abort policy exists
- no scope creep beyond migration governance

Mandatory six test/check classes:
1. migration dry-run checklist
2. secrets/variables completeness
3. branch protection mapping
4. org-side CI validation
5. RC tagging precondition
6. rollback/abort policy

Required verification in PR body:
- migration summary
- org secret/variable list
- branch protection summary
- RC rule summary
- rollback summary
- explicit statement blocking final release before green org validation

Suggested PR title:
phase-6: define org migration runbook and release-candidate promotion policy
```

---

## Definition of Done

Phase 6 is done only when:
- the repo can be moved into the organization without ambiguity,
- the organization baseline is protected from first use,
- RC and final release semantics are real and gated,
- the project is ready for post-v1 expansion without governance debt.
