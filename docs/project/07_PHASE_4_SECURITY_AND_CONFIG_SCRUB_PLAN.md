# Phase 4 — Security and Config Scrub Plan

## Status

Phase 4 exists to remove environmental drift and public leakage from the repository baseline.

A public repository cannot pretend to be clean if it still contains:
- hardcoded public hosts
- inconsistent env names
- local-author assumptions
- docs that only work in one environment
- secret-scanning that does not match real risk

This phase makes the baseline safe to mirror into an organization repo.

---

## Scope of Phase 4

This phase must fix only the following classes of problems:

1. `.env.example` neutrality
2. config/env key normalization
3. removal of public IPs, hostnames, and local-path drift
4. docs/config/compose consistency
5. secret scanning and repository hygiene checks
6. regression protection against future hardcoded infra leaks

This phase must **not**:

- redesign security architecture
- add new product features
- implement RBAC or auth systems unrelated to config hygiene
- perform large refactors outside config normalization
- alter release workflow beyond what is needed for scrub readiness

---

## Current Known Problems To Fix In This Phase

### P1. `.env.example` is not neutral

Example class of problem:
- concrete `OLLAMA_HOST=http://164.90.217.149:11434`

A public example file must teach structure, not expose current infra.

### P2. Config names drift across files

Example class of problem:
- one part of runtime uses `MCP_ALLOWED_HOSTS`
- another uses `ALLOWED_SSH_HOSTS`

This creates broken mental models and increases operator error.

### P3. Docs and runtime may disagree on env usage

If README lists one env contract and compose/runtime read another, operators will configure the repo incorrectly.

### P4. Secret/infrastructure hygiene is incomplete

Even if secrets are not present, public infra traces can still leak:
- public IPs
- operator-specific hostnames
- local machine paths
- shell history style assumptions in docs

---

## Mandatory Design Decisions For This Phase

### Decision D1 — one env key per responsibility

Each responsibility must have one canonical env key.
Aliases should be temporary only if migration is required, and must be documented.

### Decision D2 — define example value policy

Examples in public files must be:
- neutral
- safe
- copyable
- non-secret
- non-identifying

Example:
- `OLLAMA_HOST=http://ollama.example.internal:11434`
or
- `OLLAMA_HOST=http://127.0.0.1:11434`

### Decision D3 — define doc source of truth

Choose one documentation location as the canonical env contract reference.
Other docs must point to it rather than re-describing keys inconsistently.

---

## Deliverables

### D1. Neutral `.env.example`
No public IPs, personal paths, or environment-specific values.

### D2. Canonical config naming
One env name per responsibility, reflected in runtime, compose, and docs.

### D3. Repo-wide hygiene scrub
Remove or normalize drift across docs and config examples.

### D4. Hygiene checks
Automated checks to catch future hardcoded infra details.

### D5. Secret scanning alignment
Ensure scanning/config rules match the real repo surface.

### D6. Docs updated
README and setup docs must reflect the clean config contract.

---

## Required File-Level Changes

Possible change classes include:

- `.env.example`
- config parsing files
- compose files
- README env/config sections
- workflow or lint scripts
- grep/check scripts for infra leakage detection
- secret scanning configuration

---

## Implementation Rules

1. Do not commit real IPs, real private hostnames, or local user paths.
2. Do not keep duplicate env names unless migration requires it temporarily.
3. If aliases exist temporarily, document deprecation and tests.
4. Example values must be safe and unambiguous.
5. Docs must reference the same keys runtime uses.
6. Add checks that are deterministic and CI-friendly.
7. Do not introduce secret-scanning theater; checks must reflect actual repo risk.
8. Keep this PR focused on hygiene and normalization only.
9. Every config rename must have regression coverage.
10. Remove stale docs rather than allowing contradiction.

---

## Required Acceptance Criteria

### AC1. `.env.example` is neutral
No real public infra traces remain in example config.

### AC2. Config names are canonical
Runtime, compose, and docs agree on env names.

### AC3. Docs and config match
README/setup instructions reflect the actual runtime keys and defaults.

### AC4. Hygiene checks exist
At least one automated check guards against reintroducing public infra details.

### AC5. Secret scanning is aligned
The repo’s scanning and hygiene checks reflect current repository reality.

### AC6. No scope creep
No auth, provider, or orchestration work outside config hygiene.

---

## Six Mandatory Tests / Checks For This Phase

### T1. `.env.example` neutrality check
Purpose:
Ensure no real public IPs/hosts or local paths are committed in example config.

### T2. Config consistency test
Purpose:
Ensure runtime config readers and documented env keys agree.

### T3. README env table consistency check
Purpose:
Ensure docs list the same env keys runtime expects.

### T4. Compose/env consistency check
Purpose:
Ensure compose references match the canonical env contract.

### T5. Public infra grep regression check
Purpose:
Catch accidental reintroduction of hardcoded public IPs or personal hostnames.

### T6. Alias/deprecation regression test
Purpose:
If env aliases are temporarily supported, verify deterministic behavior and documented precedence.

---

## Required Verification Output In The PR Body

Codex must include:
- sanitized `.env.example` diff summary
- grep/check output proving no banned infra strings remain
- config consistency test summary
- README/env consistency summary
- `docker compose config` result
- confirmation of any env key renames or aliases

---

## Suggested PR Title

```text
phase-4: scrub public infra drift and normalize config contracts
```

---

## Suggested PR Body Template

```md
## What this PR does
- neutralizes `.env.example`
- normalizes env/config naming across runtime, compose, and docs
- removes public infra drift from the public baseline
- adds hygiene checks to prevent regression
- aligns secret/config scanning with real repository risk

## What this PR does not do
- no auth redesign
- no provider work
- no runtime feature expansion
- no release workflow work beyond hygiene requirements

## Config decisions
- canonical env reference: <path>
- renamed keys: <list>
- temporary aliases: <list or none>

## Verification
- [ ] `.env.example` neutrality check passes
- [ ] config consistency check passes
- [ ] README/env consistency check passes
- [ ] compose/env consistency check passes
- [ ] infra grep regression check passes
- [ ] `docker compose config`

## Notes
- explain any renamed env keys
- confirm removed hardcoded values
- list exact files changed and why
```

---

## Codex CLI Task Prompt

```text
You are implementing Phase 4 of a strict rebuild.

Mission:
Scrub public infra drift from the repository and normalize config/env contracts.

This phase exists to make the repository safe and clean before organization mirroring and release gating.

Primary goals:
1. Neutralize `.env.example`
2. Normalize env key naming across runtime, compose, and docs
3. Remove public IPs, hostnames, and local-path drift from the baseline
4. Add automated hygiene checks for future regression
5. Align docs and secret/config scanning with reality

Constraints:
- no TODOs
- no placeholders
- no feature work
- no auth redesign
- no unrelated refactors
- no real infra values in committed example/config files

Implementation rules:
- one env key per responsibility
- examples must be safe, neutral, and copyable
- docs must point to one canonical env source of truth
- add deterministic checks for banned infra patterns
- if temporary aliases are needed, document and test them

Mandatory acceptance criteria:
- `.env.example` is neutral
- config names are canonical
- docs and runtime match
- hygiene checks exist
- secret/config scanning is aligned
- no scope creep beyond hygiene

Mandatory six test/check classes:
1. `.env.example` neutrality
2. config consistency
3. README/env consistency
4. compose/env consistency
5. public infra grep regression
6. alias/deprecation regression

Required verification in PR body:
- sanitized env diff summary
- banned-pattern grep output
- config consistency summary
- README consistency summary
- docker compose config result
- any rename/alias summary

Suggested PR title:
phase-4: scrub public infra drift and normalize config contracts
```

---

## Definition of Done

Phase 4 is done only when:
- the repo no longer leaks environment-specific baseline details,
- configuration is understandable and consistent,
- new contributors can configure the repo from one truthful contract,
- the baseline is clean enough for release gating and org mirroring.
