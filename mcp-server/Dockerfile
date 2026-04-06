FROM python:3.12-slim

# Build args
ARG INSTALL_PLAYWRIGHT=false
# Set INSTALL_DOCKER_CLI=true only when docker-compose.privileged.yml is used.
# Do NOT set this for default deployments — it adds host-control capability.
ARG INSTALL_DOCKER_CLI=false

# System deps — openssh-client/git/curl for cloud tools; no docker.io by default.
# If INSTALL_DOCKER_CLI=true, docker.io is added for shell tools that need it
# (requires docker-compose.privileged.yml to mount /var/run/docker.sock).
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client git curl gnupg \
    && if [ "$INSTALL_DOCKER_CLI" = "true" ]; then \
        apt-get install -y --no-install-recommends docker.io && \
        echo "docker CLI installed (INSTALL_DOCKER_CLI=true)"; \
    fi \
    && rm -rf /var/lib/apt/lists/*

# Install gcloud CLI (for gcloud compute ssh and GCP tools)
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
    | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && apt-get update && apt-get install -y google-cloud-cli \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Optional: Playwright + Chromium (WARNING: adds ~400MB; only enable on 2GB+ VMs)
RUN if [ "$INSTALL_PLAYWRIGHT" = "true" ]; then \
        apt-get update && \
        playwright install chromium --with-deps && \
        rm -rf /var/lib/apt/lists/* && \
        echo "Playwright + Chromium installed"; \
    else \
        echo "Playwright skipped (INSTALL_PLAYWRIGHT != true)"; \
    fi

COPY . .

# ── Non-root runtime user ─────────────────────────────────────────────────────
# The MCP server has no legitimate reason to run as root.
# uid=1000 / gid=1000 is a safe unprivileged user.
# If docker-compose.privileged.yml is used (opt-in only), it overrides user to root.
RUN groupadd -r -g 1000 nexus && \
    useradd -r -u 1000 -g 1000 -d /app -s /sbin/nologin nexus && \
    chown -R nexus:nexus /app

USER nexus

ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os,socket; s=socket.create_connection(('127.0.0.1', int(os.environ.get('PORT', '8080'))), 3); s.close()"

CMD ["python", "server.py", "--transport", "http"]
