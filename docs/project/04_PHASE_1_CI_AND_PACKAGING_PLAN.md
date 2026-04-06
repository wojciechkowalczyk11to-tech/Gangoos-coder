# Phase 1 — CI and Packaging Stabilization Plan

## Status

Phase 1 exists to make the repository bootable, testable, and CI-verifiable from a clean clone.

This phase is intentionally narrow.
It does **not** fix product completeness.
It fixes the engineering baseline required before any higher-level integration work can be trusted.

If this phase is not green, all later claims about Mojo execution, CodeAct orchestration, Qwen remote inference, or release readiness are invalid.

---

## Scope of Phase 1

This phase must fix only the following classes of problems:

1. Python package/import path correctness for `mcp-server`
2. deterministic test execution from repository root
3. CI reproducibility for Python and Rust jobs
4. clean dependency declaration for local and CI use
5. basic boot verification for the MCP server and monorepo layout
6. removal of any hidden reliance on ad hoc developer shell state

This phase must **not**:

- redesign architecture
- introduce new product features
- implement Qwen fine-tuning
- expand Mojo executor semantics
- add broad new tools
- change public API contracts unless required strictly for boot/test stability
- refactor unrelated files “while touching them”

---

## Current Known Problems To Fix In This Phase

### P1. Python tests fail during collection from repo root

Observed class of failure:

- `ModuleNotFoundError: No module named 'config'`
- `ModuleNotFoundError: No module named 'server'`

Interpretation:

The current `mcp-server` Python layout is not packaged or invoked consistently.
Tests depend on implicit path state instead of a defined import model.

### P2. CI relies on fragile execution context

If tests only pass when run from inside a subdirectory, after manual export of `PYTHONPATH`, or after local shell mutation, the repo is not CI-stable.

### P3. Rust checks are not yet a trustworthy gate

The Rust job currently fails in CI.
This phase must determine whether the failure is due to:

- missing workspace normalization,
- missing dependencies,
- incorrect working directory,
- inconsistent toolchain assumptions,
- ignored or stale packages.

### P4. Repo-level commands are not yet canonical

A clean clone must have one obvious command set for:

- install/setup
- Python tests
- Rust tests/checks
- boot/smoke verification

### P5. Devcontainer/bootstrap may not match CI reality

If devcontainer setup hides packaging problems that appear in CI, the repo is not stable.
This phase must align local bootstrap with CI, not paper over CI breakage.

---

## Mandatory Design Decision For This Phase

### Single source of truth for Python import strategy

Codex must choose **one** import model and apply it consistently:

#### Option A — package-style imports

Example direction:

- convert `mcp-server` Python code into an installable package
- use absolute imports consistently
- make tests import package modules explicitly
- run tests against package context from repo root

#### Option B — explicit test/runtime path bootstrap

Only acceptable if package conversion is too invasive for this phase.
If used, it must still be deterministic and committed, for example through:

- a `pytest.ini`
- a root-level test bootstrap file
- explicit `pythonpath` configuration
- consistent invocation wrappers

### Decision rule

Prefer **Option A** if it can be done without destabilizing the current codebase.
Use **Option B** only if it is the minimum-change path to a green baseline.

No hidden shell exports.
No undocumented “run this from inside that folder”.
No reliance on editor-specific behavior.

---

## Deliverables

The PR for this phase must produce all of the following.

### D1. Deterministic Python test execution

From a clean clone, the following must work from repository root:

```bash
pytest mcp-server/tests -q
```

No manual `PYTHONPATH` export may be required.

### D2. Deterministic Rust verification

From a clean clone, at least one canonical Rust verification command must pass from repository root or from a clearly documented workspace entry point.

Example accepted command set:

```bash
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

If full workspace-wide execution is not yet possible, the PR must narrow scope explicitly and document the exact package path used, with reasoning.

### D3. Canonical setup commands

The repo must expose one canonical setup flow for contributors and CI.
That flow must not depend on tribal knowledge.

### D4. CI workflow aligned with real commands

GitHub Actions must run the same command family documented in the repo.
No shadow commands that are different from README/project docs.

### D5. Basic MCP server boot smoke path

There must be at least one validated smoke path proving the MCP server can import and start far enough to expose a health-like or startup confirmation path.

### D6. Phase documentation updated

The PR must update relevant docs so another engineer can reproduce the green baseline without prior chat context.

---

## Required File-Level Changes

Codex should inspect and modify the actual repository structure, but the expected change classes are below.

### 1. Python packaging/test config files

Possible files to add or modify:

- `pytest.ini`
- `pyproject.toml` for Python package metadata if not already correct
- `requirements-dev.txt` or equivalent locked dev dependency file
- `mcp-server/__init__.py` and package markers where needed
- test bootstrap helpers only if truly necessary

### 2. CI workflow files

Possible files to modify:

- `.github/workflows/ci.yml`
- related workflow fragments if split across multiple files

### 3. Devcontainer/bootstrap alignment

Possible files to inspect and adjust:

- `.devcontainer/devcontainer.json`
- `setup.sh`
- bootstrap/install scripts
- compose-related developer setup docs

### 4. Documentation

Must update at least one of:

- `README.md`
- `docs/project/...`
- contributor/setup docs

The docs must reflect real commands only.

---

## Implementation Rules

1. Do not rename major top-level directories unless absolutely required.
2. Do not introduce new product features in this PR.
3. Do not “fix” Qwen integration in this PR.
4. Do not “fix” Mojo tool semantics in this PR.
5. Do not weaken CI to make it pass.
6. Do not replace failing checks with no-op scripts.
7. Do not mark tests skipped unless there is a documented, justified, temporary blocker unrelated to Phase 1 scope.
8. Do not silence lints by blanket allow/ignore directives unless narrowly justified.
9. Every new script must include error handling and clear logging/output.
10. If a file is dead or redundant, remove it only when its removal is proven safe and documented in the PR summary.

---

## Required Acceptance Criteria

The Phase 1 PR is acceptable only if all criteria below are met.

### AC1. Clean-clone Python test pass

On a clean environment, from repository root:

```bash
pytest mcp-server/tests -q
```

must pass.

### AC2. Clean-clone Rust verification pass

The documented Rust verification command set must pass in CI and locally.

### AC3. No manual path hacks

There must be no requirement to manually export `PYTHONPATH`, `cd` into hidden subdirectories, or rely on IDE runtime magic.

### AC4. CI commands match docs exactly

Commands used in CI must be present in docs or scripts referenced by docs.

### AC5. MCP server import/boot smoke exists

A smoke test or command must prove that the server can import and initialize beyond static parsing.

### AC6. No scope creep

The PR must remain focused on CI, packaging, and reproducible boot/test behavior.

---

## Six Mandatory Tests For This Phase

Every PR in this project should carry six tests.
For Phase 1, use these exact classes.

### T1. Python import stability test

Purpose:
Ensure key server/config modules import from a clean test context.

Target:
- import config module(s)
- import server entry module(s)
- fail loudly if import path assumptions regress

### T2. Repo-root pytest execution test

Purpose:
Guarantee tests are runnable from repo root without manual environment hacks.

Target:
- subprocess-based invocation or equivalent reproducibility check
- validates documented repo-root command path

### T3. MCP server smoke test

Purpose:
Ensure server initialization path reaches a minimal valid state.

Target:
- construct app/server object
- or invoke startup command in a controlled test context
- verify non-crashing initialization

### T4. CI dependency completeness test

Purpose:
Catch missing dev/test dependencies before Actions does.

Target:
- tests that require CI-installed packages must run under the declared dependency set
- no implicit local-only packages

### T5. Rust workspace sanity test

Purpose:
Ensure the Rust workspace or target crate resolves correctly.

Target:
- package discovery
- manifest consistency
- test/check invocation from documented location

### T6. Command documentation consistency test

Purpose:
Prevent docs drift.

Target:
- if scripts are introduced, verify documented commands exist
- if entrypoints are named in README, ensure they resolve to real files/commands

These tests may be implemented through a mix of Python tests, Rust tests, and lightweight repo validation scripts, but all six classes must be covered.

---

## Required Verification Output In The PR Body

Codex must include a concise verification section in the PR body with exact command outputs or summaries for:

```bash
python --version
pytest mcp-server/tests -q
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

If any command needed a justified scoped variant, the PR body must explain why and show the exact alternative command used.

Also include:

```bash
docker compose config
```

and one MCP server smoke command or test summary.

---

## Suggested PR Title

```text
phase-1: stabilize ci, packaging, and reproducible repo-root test execution
```

---

## Suggested PR Body Template

```md
## What this PR does
- fixes Python import/package path issues for `mcp-server`
- makes repo-root test execution deterministic
- aligns CI commands with documented commands
- stabilizes Rust verification path
- adds MCP server smoke coverage

## What this PR does not do
- no Qwen runtime integration work
- no Mojo contract redesign
- no new user-facing features

## Verification
- [ ] `pytest mcp-server/tests -q`
- [ ] `cargo fmt --all -- --check`
- [ ] `cargo clippy --workspace --all-targets -- -D warnings`
- [ ] `cargo test --workspace`
- [ ] `docker compose config`
- [ ] MCP server smoke path passes

## Notes
- explain selected Python import strategy
- explain any narrowly scoped Rust command deviations if needed
- confirm no manual `PYTHONPATH` export is required
```

---

## Codex CLI Task Prompt

Use the block below as the direct implementation task.

```text
You are working in the repository as Phase 1 of a strict multi-phase rebuild.

Mission:
Stabilize CI, packaging, and reproducible repository-root test execution.
Do not add product features.
Do not expand scope into Mojo, Qwen, or higher-level orchestration.

Context:
The repo currently has evidence of broken Python test collection from repo root and failing CI.
This phase exists to make the repository trustworthy from a clean clone.

Primary goals:
1. Fix Python import/package path issues for `mcp-server`
2. Ensure `pytest mcp-server/tests -q` passes from repository root with no manual `PYTHONPATH`
3. Stabilize Rust verification so the documented Rust check/test commands work from the documented location
4. Align CI commands with real documented commands
5. Add or repair a minimal MCP server smoke path
6. Update docs to reflect the actual canonical commands

Constraints:
- no TODOs
- no placeholders
- no fake green CI
- no weakening checks to hide failures
- no Qwen integration work in this PR
- no Mojo executor redesign in this PR
- no unrelated refactors
- every file change must be directly justified by the phase goals

Implementation rules:
- choose one Python import strategy and apply it consistently
- prefer a proper package-style solution if low-risk
- if package conversion is too invasive, use a deterministic committed test/runtime bootstrap
- do not require developers or CI to run commands from obscure subdirectories unless fully documented and justified
- keep the PR minimal but complete

Mandatory acceptance criteria:
- `pytest mcp-server/tests -q` passes from repo root
- documented Rust verification commands pass, or a narrowly justified documented scoped variant passes
- CI uses the same command family documented in the repo
- MCP server smoke path exists and passes
- no manual environment hacks are required
- no scope creep beyond CI/packaging/boot stability

Mandatory six test classes to cover in this PR:
1. Python import stability
2. Repo-root pytest execution
3. MCP server smoke
4. CI dependency completeness
5. Rust workspace sanity
6. Command/documentation consistency

Required verification to include in the PR body:
- python version
- pytest command result
- cargo fmt check result
- cargo clippy result
- cargo test result
- docker compose config result
- MCP server smoke result

Suggested PR title:
phase-1: stabilize ci, packaging, and reproducible repo-root test execution
```

---

## Definition of Done

Phase 1 is done only when:

- CI is green for the commands defined in this phase,
- another engineer can clone the repo and reproduce the results from docs,
- there is no hidden shell-state dependency,
- the repo is ready for Phase 2 contract repair work.
