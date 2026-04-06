# Codex CLI — Global Execution Rules for `gangoos-coder`

## Purpose

This file defines the standing implementation contract for Codex CLI across all phases.
Each phase prompt may add scope-specific requirements, but these rules always apply.

---

## Global Rules

### 1. No placeholders
Forbidden in release-critical or phase-critical paths:
- TODO
- FIXME
- placeholder comments pretending future work
- dead stubs
- interfaces without working backend
- skipped reality behind “temporary” wording

### 2. One PR, one responsibility
Each PR must focus on one phase or sub-phase.
No unrelated refactors.

### 3. Docs and runtime move together
If code changes, docs must reflect it.
If docs claim behavior, code and tests must prove it.

### 4. Every bugfix gets a regression test
No regression test = bugfix not complete.

### 5. Six tests/checks minimum per PR
Each PR must carry six meaningful tests or checks aligned with the phase plan.

### 6. No fake green CI
Do not:
- weaken checks
- replace real checks with no-op scripts
- skip tests without narrow documented justification
- hide failures behind blanket ignores

### 7. Defensive I/O always
Every network/file/process/subprocess/database path must have:
- timeout
- error handling
- logging
- controlled failure behavior
- failure-path coverage

### 8. No hidden shell-state assumptions
No manual `PYTHONPATH` export, secret local aliases, editor-only runtime behavior, or undocumented working-directory hacks.

### 9. No scope creep
Do not touch:
- unrelated providers
- unrelated refactors
- speculative architecture changes
- future roadmap items
unless explicitly required by the phase plan.

### 10. Truth over polish
If a feature cannot be shipped truthfully in a phase:
- disable it,
- remove the claim,
- or return a controlled “not shipped” behavior.

Never leave false readiness in public interfaces or docs.

---

## Required PR Structure

Every PR must include:

1. scope
2. files changed and why
3. acceptance criteria
4. exact tests/checks run
5. verification outputs
6. explicit “what this PR does not do” section

---

## Required Verification Mindset

Codex must verify with real commands, not assumption.
Whenever applicable, include outputs or precise summaries for:

```bash
python --version
pytest mcp-server/tests -q
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
docker compose config
```

If a phase requires a narrower or different command, the PR must explain why.

---

## Review Expectations

A PR should be considered rejectable if any of the following are true:
- the repo still over-claims readiness
- runtime/docs are inconsistent
- a bugfix lacks regression coverage
- a new env var is undocumented
- a subprocess/network path lacks timeout handling
- failures are swallowed or made ambiguous
- mock-only testing is used where a bounded smoke path is required
- public infra details are reintroduced

---

## Phase Discipline

### Phase order
1. Phase 0 docs
2. Phase 1 CI and packaging
3. Phase 2 contract repair
4. Phase 3 remote Qwen runtime
5. Phase 4 security and config scrub
6. Phase 5 release gates and smoke tests
7. Phase 6 org migration and RC policy
8. Phase 7 post-v1 roadmap

### Rule
No jumping ahead unless the previous phase is green and closed.

---

## Definition of Done

Codex is compliant with this file when each PR:
- stays within scope
- leaves the repo more truthful than before
- includes real verification
- preserves the path toward a credible `v1.0.0`
