# Phase 3 — Remote Qwen Runtime Plan (VM1 -> VM2)

## Status

Phase 3 converts the current remote-Qwen shape from documentation-level intent into a supported runtime path.

This phase exists because a repository is not truly multi-node just because it has:
- `OLLAMA_HOST`
- a setup script
- a compose profile
- a README paragraph

This phase makes the two-VM topology reliable, observable, and testable.

---

## Target Topology

### VM1
- `gangus-agent`
- `mcp-server`
- orchestration logic
- fallback policy
- health and telemetry surfaces

### VM2
- `ollama`
- `qwen3:8b`
- model runtime endpoint
- controlled exposure to VM1 only

---

## Scope of Phase 3

This phase must fix only the following classes of problems:

1. explicit remote Ollama contract
2. environment parsing and config normalization for remote inference
3. pre-inference health verification
4. timeout, retry, and backoff policy
5. fallback behavior when VM2 is unavailable or degraded
6. smoke and integration coverage for `VM1 -> VM2`

This phase must **not**:

- perform Qwen fine-tuning
- build dataset pipelines
- redesign the agent architecture
- add unrelated providers
- rework Mojo contract semantics
- add large telemetry stacks unless required for observability basics

---

## Current Known Problems To Fix In This Phase

### P1. Remote inference is declared but not fully supported

The repo advertises remote `OLLAMA_HOST`, but this does not yet prove:
- VM2 is reachable before request time
- the target model is available
- errors are recoverable
- fallback behavior exists
- the path is validated end-to-end

### P2. Health behavior is not guaranteed

A remote model node must be checked before inference attempts.
Without explicit health checks, every request becomes the health check.

### P3. Failure semantics are not locked down

The runtime must clearly define behavior for:
- `OLLAMA_HOST` missing
- invalid host URL
- VM2 unreachable
- `/api/tags` or equivalent health endpoint failing
- model not pulled / missing
- inference timeout
- partial downstream response
- fallback provider success or failure

### P4. Local/dev and remote/prod semantics may drift

The same config model must support:
- local profile
- remote VM2 profile
- CI or controlled mock profile

---

## Mandatory Design Decisions For This Phase

### Decision D1 — define the remote Ollama contract

The runtime must document:
- required env vars
- required endpoint(s)
- health endpoint(s)
- required model name
- timeout defaults
- retry defaults
- fallback policy
- log fields

### Decision D2 — define fallback behavior

Choose and document one policy, for example:
- no fallback; hard fail
- fallback to cloud provider only on connectivity failure
- fallback only for selected task classes
- fallback to alternate local provider

The policy must be testable and deterministic.

### Decision D3 — define startup vs request-time validation

At least one of these must be true:

#### Option A — startup validation
VM1 verifies remote node reachability during startup and exposes unhealthy state early.

#### Option B — lazy validation with caching
VM1 validates on first use and caches health state with bounded refresh.

#### Decision rule
Prefer startup or bounded lazy validation if it improves operator visibility without making boot brittle.

---

## Deliverables

### D1. Explicit remote Qwen config contract
A single documented config model for remote inference.

### D2. Healthcheck implementation
At minimum, a reachability and model availability check.

### D3. Retry/backoff implementation
Bounded retries with logging and timeout control.

### D4. Fallback implementation or explicit no-fallback policy
The runtime must behave intentionally, not accidentally.

### D5. Smoke and integration tests
A validated path showing VM1 can talk to VM2.

### D6. Docs updated
README and project docs must reflect the actual runtime contract.

---

## Required File-Level Changes

Possible change classes include:

### Config and runtime
- config parsing modules
- inference client modules
- healthcheck helpers
- retry/backoff wrappers
- fallback policy modules

### Compose and environment
- compose or profile docs
- `.env.example`
- setup/bootstrap docs

### Tests
- unit tests for env parsing
- failure-path tests
- integration or mock-based smoke tests

---

## Implementation Rules

1. No hidden fallback behavior.
2. No infinite retry loops.
3. Every outbound model request must have timeout handling.
4. Every retry policy must be bounded and logged.
5. Health checks must not leak secrets.
6. If VM2 is unsupported in a given mode, docs must say so explicitly.
7. Avoid provider-specific sprawl outside the remote-Qwen path.
8. Keep this PR focused on supported runtime behavior.
9. Any subprocess or network call must fail clearly.
10. Metrics/logging fields must be consistent across success and failure.

---

## Required Acceptance Criteria

### AC1. Remote config is explicit
The required env keys and defaults are documented and validated.

### AC2. Healthcheck exists
VM1 can verify VM2 reachability and model availability intentionally.

### AC3. Timeout/retry behavior is deterministic
The runtime does not hang indefinitely or retry without bounds.

### AC4. Fallback policy is explicit
Either fallback works and is tested, or the runtime explicitly hard-fails by design.

### AC5. Smoke path exists
A controlled test proves `VM1 -> VM2` works.

### AC6. No scope creep
No fine-tuning, dataset generation, or broader architecture changes.

---

## Six Mandatory Tests For This Phase

### T1. Env parsing test
Purpose:
Validate `OLLAMA_HOST`, model name, defaults, and invalid env handling.

### T2. Healthcheck success test
Purpose:
Verify healthy VM2 returns reachable/ready state.

### T3. Healthcheck failure test
Purpose:
Verify unreachable or invalid VM2 produces deterministic unhealthy state.

### T4. Timeout / retry behavior test
Purpose:
Verify bounded retry and final failure on slow or unavailable runtime.

### T5. Fallback behavior test
Purpose:
Verify configured fallback policy for connectivity or inference failure.

### T6. Integration smoke test
Purpose:
Verify `VM1 -> VM2` request path using either a controlled mock server or a bounded test runtime.

---

## Required Verification Output In The PR Body

Codex must include:

```bash
pytest mcp-server/tests -q
docker compose config
```

And additionally:
- remote config example
- healthcheck command or test output
- one success inference smoke summary
- one timeout/failure summary
- one fallback summary or explicit no-fallback confirmation

If a live remote VM is not used in CI, the PR must explain the controlled mock strategy and show the exact validation commands.

---

## Suggested PR Title

```text
phase-3: support remote qwen runtime with healthchecks, timeout policy, and fallback
```

---

## Suggested PR Body Template

```md
## What this PR does
- defines the remote Ollama/Qwen contract
- adds health verification before or around inference
- adds bounded timeout/retry behavior
- defines and tests fallback behavior
- adds smoke coverage for VM1 -> VM2

## What this PR does not do
- no fine-tuning
- no dataset work
- no Mojo contract work
- no unrelated provider expansion

## Runtime policy
- startup validation: <yes/no, explain>
- health endpoint: <path>
- timeout policy: <value/strategy>
- retry policy: <count/backoff>
- fallback policy: <describe>

## Verification
- [ ] env parsing tests pass
- [ ] healthcheck success/failure tests pass
- [ ] timeout/retry tests pass
- [ ] fallback test passes
- [ ] integration smoke passes
- [ ] `pytest mcp-server/tests -q`
- [ ] `docker compose config`

## Notes
- explain how VM1 should reach VM2
- confirm the final env keys
- list exact files changed and why
```

---

## Codex CLI Task Prompt

```text
You are implementing Phase 3 of a strict rebuild.

Mission:
Convert the current remote-Qwen placeholder into a supported two-VM runtime path.

Target topology:
- VM1 runs `gangus-agent` and `mcp-server`
- VM2 runs `ollama` with `qwen3:8b`

Primary goals:
1. Define the remote Ollama/Qwen config contract
2. Add health verification for the remote model node
3. Add bounded timeout and retry behavior
4. Define and implement fallback behavior or explicit no-fallback policy
5. Add smoke coverage for VM1 -> VM2
6. Update docs to match runtime reality

Constraints:
- no TODOs
- no placeholders
- no fine-tuning
- no dataset work
- no Mojo contract redesign
- no unrelated provider expansion
- no hidden fallback logic

Implementation rules:
- every outbound model request must have timeout handling
- retry must be bounded and logged
- health checks must be explicit and deterministic
- config validation must fail clearly on bad input
- if live VM2 is not available in CI, use a controlled mock and document it
- keep the PR focused on runtime support only

Mandatory acceptance criteria:
- explicit config contract exists
- healthcheck exists and is tested
- timeout/retry behavior is deterministic
- fallback behavior is explicit and tested
- VM1 -> VM2 smoke path exists
- docs match the real runtime

Mandatory six test classes:
1. env parsing
2. healthcheck success
3. healthcheck failure
4. timeout/retry behavior
5. fallback behavior
6. integration smoke

Required verification in PR body:
- config example
- healthcheck result
- smoke success result
- timeout/failure result
- fallback result or explicit no-fallback statement
- pytest result
- docker compose config result

Suggested PR title:
phase-3: support remote qwen runtime with healthchecks, timeout policy, and fallback
```

---

## Definition of Done

Phase 3 is done only when:
- remote Qwen is a supported runtime path rather than a README promise,
- VM2 failure behavior is intentional and observable,
- the two-node topology is reproducible from docs,
- the repo is ready for security/config cleanup in the next phase.
