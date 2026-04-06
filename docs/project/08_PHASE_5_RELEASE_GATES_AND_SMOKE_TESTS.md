# Phase 5 — Release Gates and Smoke Tests

## Status

Phase 5 exists to convert the repository from “a set of improving components” into a release candidate baseline.

This phase does not add product scope.
It adds **proof** that the claimed product baseline works predictably and is governed by hard gates.

---

## Scope of Phase 5

This phase must implement only the following classes of work:

1. branch and CI release gates
2. compose-level smoke validation
3. health endpoint and startup verification
4. main-path runtime smoke validation
5. release checklist and candidate policy
6. regression protection against failures fixed in Phases 1-4

This phase must **not**:

- expand product surface
- add new tools
- add fine-tuning
- redesign architecture
- add non-essential services
- mask instability with looser checks

---

## Preconditions

Phase 5 must not start unless Phases 1-4 are complete:
- boot/test baseline stable
- contract truth repaired
- remote runtime defined
- config hygiene stabilized

If those are not true, release gates are theater.

---

## Deliverables

### D1. Required checks defined and enforced
The repo must identify which checks are required for protected branches.

### D2. Compose smoke path
There must be a deterministic smoke validation path for compose configuration and minimal startup.

### D3. Health verification
At least one health-like path must confirm that the server starts to a usable state.

### D4. Main-path smoke validation
The repository’s primary runtime promise must have at least one bounded smoke path.

### D5. Release checklist
A documented checklist for `v1.0.0-rc1` and `v1.0.0`.

### D6. Regression carry-forward
Failures fixed in earlier phases must remain guarded.

---

## Required Design Decisions

### Decision D1 — define the minimum releasable product path

Choose and document the minimum path that must work for a release candidate.
Example:
- repo boots
- MCP server starts
- canonical tool invocation works
- remote or mocked model path works
- health surface responds

### Decision D2 — define release candidate vs release

At minimum:
- `v1.0.0-rc1` means all gates pass and docs are truthful
- `v1.0.0` means the RC remained stable after org mirror validation

### Decision D3 — define branch protection policy

Document:
- required checks
- merge strategy
- force-push policy
- review requirement
- whether squash-only is required

---

## Required File-Level Changes

Possible change classes include:

- workflow configuration
- branch protection documentation
- smoke test scripts
- compose/startup helpers
- release docs/checklists
- README release/runbook sections

---

## Implementation Rules

1. Do not weaken checks to “get a release out”.
2. Do not define a release path that avoids the main product promise.
3. Do not rely on manual invisible operator steps.
4. Smoke tests must be bounded, deterministic, and documented.
5. Health checks must prove meaningful readiness, not just process existence.
6. Release checklist items must map to executable or inspectable proof where possible.
7. Protected branch policy must match actual repo practice.
8. Keep this PR focused on release gates and smoke validation only.
9. No ceremonial docs without executable backing.
10. Every gate must be reproducible by another engineer.

---

## Required Acceptance Criteria

### AC1. Required checks are defined
The repo states exactly which checks gate merges and release.

### AC2. Compose smoke exists
There is a deterministic compose validation and minimal startup path.

### AC3. Health verification exists
A health or readiness path can be checked consistently.

### AC4. Main-path smoke exists
The minimum releasable product path is actually exercised.

### AC5. Release checklist exists
RC and final release criteria are documented and actionable.

### AC6. No scope creep
No new feature expansion beyond release gates and smoke tests.

---

## Six Mandatory Tests / Checks For This Phase

### T1. Compose config check
Purpose:
Verify compose files remain syntactically valid and fully renderable.

### T2. Minimal compose startup smoke
Purpose:
Verify the minimum service set can start under a controlled environment.

### T3. Health endpoint/readiness check
Purpose:
Verify the server reaches meaningful readiness.

### T4. Main-path runtime smoke
Purpose:
Verify the minimum releasable product path works end-to-end or through a bounded mock.

### T5. Required checks verification
Purpose:
Verify the documented required checks correspond to actual workflow jobs/scripts.

### T6. Cross-phase regression check
Purpose:
Ensure at least one representative failure from Phases 1-4 is still guarded.

---

## Required Verification Output In The PR Body

Codex must include:
- `docker compose config`
- minimal startup smoke output
- health endpoint or readiness output
- main-path smoke summary
- list of required checks
- release checklist summary

If local or CI constraints require a bounded mock for one path, the PR must explain that precisely.

---

## Suggested PR Title

```text
phase-5: add release gates, compose smoke tests, and readiness verification
```

---

## Suggested PR Body Template

```md
## What this PR does
- defines release-gating checks
- adds compose smoke validation
- adds health/readiness verification
- adds main-path runtime smoke coverage
- documents release candidate and final release criteria

## What this PR does not do
- no new product features
- no architecture redesign
- no fine-tuning or dataset work
- no unrelated refactors

## Release decisions
- minimum releasable path: <describe>
- required checks: <list>
- merge policy: <describe>
- release candidate definition: <describe>

## Verification
- [ ] `docker compose config`
- [ ] minimal compose startup smoke passes
- [ ] health/readiness check passes
- [ ] main-path smoke passes
- [ ] required checks map to actual workflows/scripts
- [ ] regression carry-forward check passes

## Notes
- explain any mocked path
- confirm branch protection expectations
- list exact files changed and why
```

---

## Codex CLI Task Prompt

```text
You are implementing Phase 5 of a strict rebuild.

Mission:
Add release gates, smoke tests, and readiness verification so the repository can honestly approach a release candidate.

Primary goals:
1. Define required checks for protected branches and release
2. Add deterministic compose smoke validation
3. Add meaningful health/readiness verification
4. Add a bounded smoke path for the minimum releasable product promise
5. Document RC and final release criteria
6. Preserve regression protection from earlier phases

Constraints:
- no TODOs
- no placeholders
- no feature expansion
- no architecture redesign
- no weakening checks to make release easier
- no ceremonial docs without executable backing

Implementation rules:
- define one minimum releasable path and prove it
- keep smoke tests deterministic and bounded
- ensure docs map to actual workflow jobs/scripts
- if a bounded mock is necessary, document it precisely
- keep the PR focused on release gates only

Mandatory acceptance criteria:
- required checks are defined
- compose smoke exists
- health verification exists
- main-path smoke exists
- release checklist exists
- no scope creep beyond release gates and smoke validation

Mandatory six test/check classes:
1. compose config
2. minimal startup smoke
3. health/readiness
4. main-path smoke
5. required-check mapping
6. cross-phase regression carry-forward

Required verification in PR body:
- compose config result
- startup smoke result
- health result
- main-path smoke result
- required checks list
- release checklist summary

Suggested PR title:
phase-5: add release gates, compose smoke tests, and readiness verification
```

---

## Definition of Done

Phase 5 is done only when:
- the repo can be evaluated as a release candidate through objective gates,
- the minimum product promise is exercised,
- required checks are clear and enforceable,
- the repo is ready for clean org mirroring and RC validation.
