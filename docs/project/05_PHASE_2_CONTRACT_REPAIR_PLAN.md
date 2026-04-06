# Phase 2 — Contract Repair Plan (`CodeAct -> NEXUS -> mojo_exec`)

## Status

Phase 2 exists to eliminate false product completeness.
After Phase 1, the repository may boot and test correctly, but it still cannot claim functional readiness if the main execution contracts are mismatched or half-implemented.

This phase is about **truthful runtime contracts**.
A public interface may not advertise behavior that does not exist behind it.

---

## Scope of Phase 2

This phase must fix only the following classes of problems:

1. transport contract alignment between Rust `codeact` and MCP/NEXUS server
2. request/response schema consistency for tool invocation
3. explicit registration and implementation status of `mojo_exec`
4. failure semantics for missing tools, invalid payloads, and backend unavailability
5. documentation accuracy for the chosen contract
6. regression protection for the exact mismatch that currently exists

This phase must **not**:

- redesign overall architecture
- expand the set of tools
- introduce Qwen runtime work
- add fine-tuning or dataset flows
- build broader orchestration features
- refactor unrelated crates or Python modules
- add speculative executor features not required by the contract

---

## Current Known Problems To Fix In This Phase

### P1. Endpoint mismatch

Observed mismatch class:

- Rust `codeact` issues `POST {NEXUS_URL}/tools/call`
- REST gateway advertises or exposes tool execution through `POST /api/v1/tools/{tool_name}`

Interpretation:

The caller and server do not currently share one transport contract.
This makes success accidental rather than guaranteed.

### P2. `mojo_exec` is advertised more strongly than it is implemented

If user-facing or code-facing paths imply `run_mojo` is ready, but the server does not register `mojo_exec` with a working backend, the repo is lying about readiness.

### P3. Error behavior is undefined or inconsistent

Tool invocation must clearly define behavior for:
- unknown tool
- malformed payload
- timeout
- transport failure
- backend unavailable
- internal execution error

### P4. Contract location is fragmented

The contract currently leaks across:
- Rust client code
- Python server/router code
- docs/README
- tests

Without a single source of truth, drift will recur.

---

## Mandatory Design Decisions For This Phase

### Decision D1 — choose one invocation transport

Pick exactly one of the following and document it:

#### Option A — REST is the canonical transport
- Rust calls REST endpoints only
- Python server exposes REST tool execution as the supported public contract
- MCP JSON-RPC may still exist internally, but is not the contract used by `codeact`

#### Option B — MCP JSON-RPC is the canonical transport
- Rust calls MCP directly
- REST gateway becomes a compatibility layer or is removed from this flow

#### Decision rule
Prefer the option that requires the fewest moving parts while preserving future extensibility.
If the repo already has a stable REST gateway shape, prefer REST for this phase.

### Decision D2 — choose one truth for `mojo_exec`

Exactly one of the following must be made true:

#### Option A — ship `mojo_exec` now
- register the tool
- implement the backend
- validate inputs
- define outputs
- add failure behavior
- smoke test success path

#### Option B — do not ship `mojo_exec` in public flow yet
- remove or disable public references that imply readiness
- make `run_mojo` return a controlled “not shipped” / “unsupported” response
- update docs so the product does not over-claim

#### Decision rule
If a trustworthy implementation can be completed inside phase scope, ship it.
If not, remove the lie and make the failure explicit.

No half-state is allowed.

---

## Deliverables

The PR for this phase must produce all of the following.

### D1. One canonical invocation contract

There must be one documented call path from Rust `codeact` to the server.

### D2. One canonical request and response schema

The contract must define:
- path
- method
- required fields
- optional fields
- success envelope
- error envelope
- HTTP or protocol semantics

### D3. `mojo_exec` truth state fixed

Either:
- fully available and working,
- or explicitly not shipped and removed from ready paths.

### D4. Error mapping and logging

Errors must be deterministic and logged with context.

### D5. Contract tests

Tests must cover success and failure semantics.

### D6. Docs updated

README, phase docs, and any API notes must match the real contract.

---

## Required File-Level Changes

Codex should inspect the actual repository, but expected change classes include:

### Rust side
Possible files to inspect or modify:
- `crates/.../codeact/...`
- transport client modules
- tool invocation helpers
- error mapping layers

### Python server side
Possible files to inspect or modify:
- router files under `mcp-server`
- server/gateway registration
- tool registry
- `mojo_exec` implementation or disablement path

### Documentation
Must update at least:
- README sections describing tool invocation
- project phase docs
- API or integration docs if present

### Tests
Add or modify:
- Rust integration tests or contract tests
- Python API tests
- end-to-end or bounded smoke tests

---

## Implementation Rules

1. Do not invent a second compatibility contract unless strictly required.
2. Do not silently remap requests in hidden glue code without documenting it.
3. Do not leave `run_mojo` available if the backend is absent.
4. Do not use generic `500` for known contract failures when a specific code is available.
5. Do not swallow backend errors.
6. Every network or subprocess path must include timeout and logging.
7. Error responses must be parseable and stable.
8. If feature is disabled, disable it explicitly and document it.
9. No feature marketing in docs beyond implemented truth.
10. Keep this PR focused on contract repair only.

---

## Required Acceptance Criteria

### AC1. One documented contract exists
There is exactly one supported invocation path for `codeact -> server`.

### AC2. Contract is consistent in code and docs
The same path/schema is used by the client, server, and docs.

### AC3. `mojo_exec` truth is fixed
It either works end-to-end or is explicitly not shipped and cannot be mistaken for ready.

### AC4. Failures are controlled
Unknown tool, invalid payload, timeout, and backend failure produce deterministic responses.

### AC5. Regression for current mismatch exists
The pre-phase endpoint mismatch cannot silently return.

### AC6. No scope creep
This PR does not drift into Qwen, release governance, or unrelated refactors.

---

## Six Mandatory Tests For This Phase

### T1. Tool registration test
Purpose:
Verify that the server registry truthfully includes or excludes `mojo_exec`.

### T2. Success contract test
Purpose:
Verify successful invocation using the canonical request shape and expected response schema.

### T3. Unknown tool / not found contract test
Purpose:
Verify controlled failure when the requested tool is absent.

### T4. Invalid payload contract test
Purpose:
Verify validation and stable error response for malformed input.

### T5. Timeout / backend failure propagation test
Purpose:
Verify timeout or backend outage maps to deterministic client-visible failure and logs.

### T6. Regression test for endpoint/path mismatch
Purpose:
Ensure the current mismatch between `/tools/call` and `/api/v1/tools/{tool_name}` cannot silently recur.

---

## Required Verification Output In The PR Body

Codex must include exact verification summaries for:

```bash
pytest mcp-server/tests -q
cargo test --workspace -- --nocapture
docker compose config
```

And additionally:

- one successful contract invocation example
- one invalid payload example
- one missing tool example
- one timeout or unavailable backend example
- confirmation of the final `mojo_exec` truth state

---

## Suggested PR Title

```text
phase-2: repair tool invocation contract and define mojo_exec truth state
```

---

## Suggested PR Body Template

```md
## What this PR does
- aligns the canonical tool invocation contract between Rust and server
- defines the final truth state for `mojo_exec`
- adds deterministic error mapping for contract failures
- updates docs to match runtime reality
- adds regression coverage for the prior mismatch

## What this PR does not do
- no Qwen runtime work
- no release governance work
- no new product features outside the contract scope

## Final contract decision
- transport: <REST or MCP>
- mojo_exec status: <shipped or not shipped>

## Verification
- [ ] canonical success invocation passes
- [ ] invalid payload failure is deterministic
- [ ] unknown tool failure is deterministic
- [ ] timeout/backend failure is deterministic
- [ ] `pytest mcp-server/tests -q`
- [ ] `cargo test --workspace -- --nocapture`
- [ ] `docker compose config`

## Notes
- explain why the chosen transport was selected
- confirm how `run_mojo` behaves after this PR
- list exact files changed and why
```

---

## Codex CLI Task Prompt

```text
You are implementing Phase 2 of a strict rebuild.

Mission:
Repair the execution contract between Rust `codeact`, the MCP/NEXUS server, and `mojo_exec`.

This phase exists to eliminate false completeness.
The repository may not claim a working Mojo execution path unless the transport, schema, registry, and backend all agree.

Primary goals:
1. Align Rust client invocation with the server’s canonical transport contract
2. Define one request/response schema as the source of truth
3. Fix the truth state of `mojo_exec`: fully working or explicitly not shipped
4. Add deterministic error semantics for unknown tool, invalid payload, timeout, and backend failure
5. Update docs to match reality
6. Add regression protection for the current endpoint mismatch

Constraints:
- no TODOs
- no placeholders
- no fake compatibility shims hidden from docs
- no Qwen work
- no broader architecture redesign
- no unrelated refactors
- no product marketing language beyond implemented truth

Implementation rules:
- choose one canonical transport and document it
- do not leave `run_mojo` in a half-working public state
- if `mojo_exec` cannot be completed safely in this phase, remove the lie and make unsupported behavior explicit
- every network/process failure path must have timeout handling, error mapping, and logging
- docs must match the exact path and payload used in code

Mandatory acceptance criteria:
- one documented contract exists
- client, server, and docs all use the same contract
- `mojo_exec` is either working end-to-end or explicitly not shipped
- error behavior is deterministic
- regression test exists for the prior mismatch
- no scope creep beyond contract repair

Mandatory six test classes:
1. tool registration truth
2. success contract
3. unknown tool failure
4. invalid payload failure
5. timeout/backend failure propagation
6. regression test for endpoint/path mismatch

Required verification in PR body:
- success invocation example
- invalid payload example
- missing tool example
- timeout/backend failure example
- pytest result
- cargo test result
- docker compose config result

Suggested PR title:
phase-2: repair tool invocation contract and define mojo_exec truth state
```

---

## Definition of Done

Phase 2 is done only when:
- the tool invocation path is singular and truthful,
- `run_mojo` cannot mislead users or tests,
- success and failure behavior are both documented and tested,
- the repo is ready for Phase 3 runtime work without contract ambiguity.
