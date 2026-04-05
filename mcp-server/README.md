# gangus-coder MCP server

This directory contains the Python MCP server bundled into the `gangus-coder` monorepo as `mcp-server/`.

It is intended to run beside the Rust `goosed` agent through the root-level `docker-compose.yml`.

## Local development

From the repository root:

```bash
docker compose up --build
```

Services exposed by the monorepo stack:

- `gangus-agent` on `http://localhost:3000`
- `mcp-server` on `http://localhost:8080`

## Required environment

The monorepo uses the shared root `.env` file. The main variables consumed by this service are:

- `PORT`
- `NEXUS_AUTH_TOKEN`
- `XAI_API_KEY`
- `GEMINI_API_KEY`
- `DEEPSEEK_API_KEY`
- `GITHUB_TOKEN`
- `DIGITALOCEAN_TOKEN`

## Notes

- The server keeps its Python dependencies in `requirements.txt`.
- Documentation and deployment examples in this monorepo assume Codespaces for development and DigitalOcean for runtime hosting.
- Legacy single-host deployment notes were intentionally removed from this copy.
