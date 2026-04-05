# gangus-coder work log

## Current state

### Completed locally

- `nexus-mcp-server` was merged into the repository as `mcp-server/`
- Root `docker-compose.yml` was added for `gangus-agent` and `mcp-server`
- Shared root `.env.example` was normalized to variable names only
- `.devcontainer` was updated for Rust, Python 3.12, Node 22, Docker, forwarded ports `3000` and `8080`
- `Dockerfile` now builds both `gangus-coder` and `goosed`
- Default runtime routing was set to `xai` with `grok-4-1-fast-reasoning`
- High-risk legacy deployment files with private paths and host references were removed from `mcp-server/`
- Local working `.env` was copied into the repo root for compose-only development
- Root `README.md` was rewritten toward the merged monorepo shape
- GitHub Actions CI was moved away from `self-hosted` to `ubuntu-latest`
- Minimal Python tests were added for the bundled MCP server

### Verified

- Python syntax check passed for:
  - `mcp-server/server.py`
  - `mcp-server/rest_gateway.py`
  - `mcp-server/config.py`
- `docker compose config` passes from repo root
- `.env` is ignored by repo and docker context

### Known blockers

- This source tree came from a ZIP archive and has no `.git` history
- Task-level commits and GitHub pushes are blocked until a real authenticated git remote is available
- Full-history secret scanning is blocked until real git history is attached
- Local image build hit a Docker environment issue:
  - `mkdir /home/ubuntu/.docker: read-only file system`
- Rust toolchain validation is blocked in the current shell because system `cargo` is unavailable outside the target devcontainer/runtime
- Python test execution is blocked in the current shell because `pip` and `pytest` are not installed outside the target devcontainer/runtime

## Next work items

1. Finish security cleanup of private URLs, IPs, and legacy infra references in docs/training exports
2. Make root README release-ready for the merged monorepo
3. Add/adjust CI so Rust and Python checks run together
4. Run Rust and Python test suites in a working toolchain environment
5. Add Task 7 `hacker-laws` knowledge base and Context7 detection/tests
6. Prepare DigitalOcean deployment path for the later Qwen runtime stage
