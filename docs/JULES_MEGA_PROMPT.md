# Mega-Prompt for Google Jules AI Agent: Gangoos-Coder Repository Enhancement

This document provides a comprehensive, phased mega-prompt for the Google Jules AI agent to enhance the Gangoos-Coder repository, a Rust-based AI coding agent with multiple components and integrations. The prompt is divided into five actionable phases, each with clear objectives, acceptance criteria, specific files to modify, test commands to verify progress, and estimated scope. The goal is to systematically improve code quality, testing, documentation, performance, and feature set while maintaining a structured approach.

---

## Overview of Gangoos-Coder Repository
- **Core**: Rust agent core in `crates/goose`
- **MCP Server**: 170+ tool Python server in `mcp-server/`
- **LLM Integration**: Local Qwen3 via Ollama in `llm/`
- **Platform Extensions**: `codeact`, `context7`, `git_aware`, `watcher`, `memory`, `planner`, `hooks`
- **Dataset Generation**: Mojo-battle-generator
- **UI**: Desktop application using Electron

---

## Phase 1: Code Quality & Safety
**Objective**: Improve code quality, eliminate warnings, and ensure safety by addressing linter issues, error handling, and potential security risks.

**Acceptance Criteria**:
- All Clippy warnings are resolved (0 warnings on `cargo clippy --all -- -D warnings`).
- Error handling is implemented for all fallible operations using `Result` or `Option`.
- No hardcoded secrets, IPs, or sensitive data remain in the codebase.
- Input validation is added for all user or external inputs.
- Unsafe code is either removed or justified with detailed comments and safety guarantees.

**Files to Modify**:
- Rust core: `crates/goose/src/*.rs`, `crates/goose/Cargo.toml`
- Platform extensions: `crates/extensions/*/src/*.rs`
- MCP server: `mcp-server/*.py`, `mcp-server/tools/*.py`
- Configuration files: `config/*.toml`, `config/*.yaml`

**Test Commands**:
- `cargo clippy --all -- -D warnings` (should return no warnings)
- `cargo build --all` (should compile without errors)
- `cargo test --all` (ensure no regressions)
- Manual grep for secrets: `grep -r -E "password|secret|key|ip|localhost" .`

**Estimated Scope**: 1-2 weeks
- Clippy fixes: 1-2 days
- Error handling: 3-4 days
- Secrets and input validation: 2-3 days
- Unsafe code review: 1-2 days

**Instructions for Jules**:
1. Run `cargo clippy --all -- -D warnings` and fix all reported issues in Rust code.
2. Audit all functions in `crates/goose` and extensions for missing error handling; wrap fallible operations in `Result` or `Option`.
3. Search for hardcoded secrets or IPs using regex patterns and replace them with environment variables or configuration file entries.
4. Add input validation for API endpoints, command-line arguments, and configuration parsing.
5. Review `unsafe` blocks in Rust code; refactor to safe alternatives where possible or add detailed safety documentation.

---

## Phase 2: Test Coverage
**Objective**: Increase test coverage to ensure reliability and catch regressions across core components and extensions.

**Acceptance Criteria**:
- Unit tests cover all public functions in platform extensions.
- Integration tests validate MCP client-to-server communication flows.
- Property-based tests are implemented for critical paths (e.g., data parsing, command execution).
- Test coverage reaches at least 80% for core crates (`crates/goose`) as reported by `cargo tarpaulin`.

**Files to Modify**:
- Rust core tests: `crates/goose/tests/*.rs`
- Extension tests: `crates/extensions/*/tests/*.rs`
- MCP integration tests: `mcp-server/tests/*.py`
- Critical path property tests: Add new files in `crates/goose/tests/property/*.rs`

**Test Commands**:
- `cargo test --all` (all tests pass)
- `cargo tarpaulin --all --out Html` (verify coverage ≥ 80% for core crates)
- `python -m pytest mcp-server/tests/` (MCP server tests pass)

**Estimated Scope**: 2-3 weeks
- Unit tests for extensions: 5-7 days
- Integration tests for MCP: 3-5 days
- Property-based tests: 2-3 days
- Coverage analysis and fixes: 2-3 days

**Instructions for Jules**:
1. Write unit tests for all public functions in each platform extension (`codeact`, `context7`, etc.) under their respective `tests/` directories.
2. Create integration tests in `mcp-server/tests/` to simulate client-server interactions, ensuring proper request handling and error responses.
3. Use a property-based testing library like `proptest` to add tests for critical paths (e.g., input parsing, command execution) in `crates/goose`.
4. Run coverage analysis with `cargo tarpaulin` and add tests for uncovered areas in core crates until 80% coverage is achieved.

---

## Phase 3: Documentation & API
**Objective**: Enhance project documentation and API specifications for better maintainability and user onboarding.

**Acceptance Criteria**:
- OpenAPI specification is generated for the MCP server and saved as `mcp-server/openapi.yaml`.
- Rustdoc comments are added to all public types, functions, and modules in Rust code.
- Architecture Decision Records (ADRs) are created for major design choices in `docs/adr/`.
- README.md is updated with accurate build, run, and dependency installation instructions.

**Files to Modify**:
- MCP server API spec: `mcp-server/openapi.yaml` (new file)
- Rust documentation: `crates/goose/src/*.rs`, `crates/extensions/*/src/*.rs`
- ADRs: `docs/adr/*.md` (new files)
- Project root: `README.md`

**Test Commands**:
- `cargo doc --all --no-deps` (generate and verify Rust documentation)
- Manual validation of `mcp-server/openapi.yaml` using a tool like Swagger Editor.
- Manual review of `README.md` for accuracy by running listed commands.

**Estimated Scope**: 1-2 weeks
- OpenAPI spec: 2-3 days
- Rustdoc comments: 3-4 days
- ADRs: 1-2 days
- README update: 1 day

**Instructions for Jules**:
1. Use a tool like `FastAPI` (if applicable) or manually write an OpenAPI spec for the MCP server endpoints in `mcp-server/openapi.yaml`.
2. Add detailed Rustdoc comments to all public items in `crates/goose` and extensions, following Rust documentation guidelines.
3. Create ADRs in `docs/adr/` for key decisions (e.g., why Qwen3 via Ollama, extension architecture) using a standard ADR template.
4. Update `README.md` with step-by-step instructions for building, running, and testing the project, including dependencies for Rust, Python, and Electron.

---

## Phase 4: Performance & Reliability
**Objective**: Optimize performance and improve reliability for robust operation under load and failure conditions.

**Acceptance Criteria**:
- Connection pooling is implemented for MCP client connections to reduce overhead.
- Retry logic with exponential backoff is added for external API calls and LLM interactions.
- Circuit breaker pattern is implemented for external services to prevent cascading failures.
- Hot paths are profiled and optimized, reducing latency by at least 10% on critical operations.

**Files to Modify**:
- MCP client: `crates/goose/src/mcp_client.rs` (or similar)
- Retry logic: `crates/goose/src/api_utils.rs` (or new file)
- Circuit breaker: `crates/goose/src/circuit_breaker.rs` (new file)
- Hot path optimizations: Identify via profiling, likely in `crates/goose/src/*.rs`

**Test Commands**:
- `cargo bench` (compare before/after performance for hot paths)
- `cargo test --all` (ensure no regressions)
- Stress test MCP client with pooling: Custom script or tool like `wrk` on MCP server endpoints.

**Estimated Scope**: 2-3 weeks
- Connection pooling: 3-4 days
- Retry with backoff: 2-3 days
- Circuit breaker: 2-3 days
- Profiling and optimization: 3-5 days

**Instructions for Jules**:
1. Implement connection pooling for MCP client using a library like `r2d2` or equivalent in Rust.
2. Add retry logic with exponential backoff for external API calls and LLM requests using a crate like `retry`.
3. Implement a circuit breaker pattern for external services using a library or custom logic to handle failure states gracefully.
4. Use `cargo bench` or a profiler like `flamegraph` to identify and optimize hot paths in the core Rust code, targeting a 10% latency reduction.

---

## Phase 5: Features
**Objective**: Implement new features and extensions to enhance functionality and user interaction.

**Acceptance Criteria**:
- `gangus_memory` extension is implemented for persistent project memory.
- `planner` extension supports structured task planning with dependency graphs.
- `hooks` extension allows pre/post tool validation logic.
- Telegram bot integration is added for notifications and basic commands.
- Rate limiting is implemented on MCP server to prevent abuse.

**Files to Modify**:
- New extension: `crates/extensions/gangus_memory/src/*.rs`
- Planner extension: `crates/extensions/planner/src/*.rs`
- Hooks extension: `crates/extensions/hooks/src/*.rs`
- Telegram bot: `crates/goose/src/telegram_bot.rs` (or new crate)
- MCP rate limiting: `mcp-server/app.py` or middleware in `mcp-server/*.py`

**Test Commands**:
- `cargo test --all` (all new features have passing tests)
- Manual testing of Telegram bot integration with a test bot token.
- Stress test MCP server with rate limiting using `wrk` or similar to confirm limits are enforced.

**Estimated Scope**: 3-4 weeks
- `gangus_memory`: 4-5 days
- `planner`: 4-5 days
- `hooks`: 3-4 days
- Telegram bot: 2-3 days
- MCP rate limiting: 2-3 days

**Instructions for Jules**:
1. Implement `gangus_memory` extension to store and retrieve project-specific data persistently, integrating with existing memory systems.
2. Enhance the `planner` extension to support task dependency graphs and structured planning logic for multi-step operations.
3. Develop the `hooks` extension to allow custom pre/post validation logic for tool execution, with configurable callbacks.
4. Add Telegram bot integration using a Rust library like `teloxide`, supporting basic commands and notifications.
5. Implement rate limiting on the MCP server using a middleware or library like `ratelimit` in Python to prevent abuse.

---

## Final Notes for Jules
- Prioritize phases sequentially, completing each phase fully before moving to the next.
- Commit changes incrementally with descriptive messages for each task within a phase.
- If blockers or ambiguities arise (e.g., unclear requirements for an extension), document them in an issue on the repository and proceed with the next task.
- Provide a summary report at the end of each phase, detailing completed tasks, test results, and any deviations from the plan.

This structured approach ensures systematic improvement of the Gangoos-Coder repository while maintaining clarity and accountability at each step.
