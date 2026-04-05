FROM python:3.12-slim

# Build arg: set to "true" to include Playwright + Chromium
# WARNING: Adds ~400MB to image and ~500MB RAM at runtime.
# On e2-micro (1GB) this WILL cause OOM. Only enable on 2GB+ VMs.
ARG INSTALL_PLAYWRIGHT=false

# System deps for SSH and git
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client git curl gnupg docker.io \
    && rm -rf /var/lib/apt/lists/*

# Install gcloud CLI (for gcloud compute ssh)
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
    | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && apt-get update && apt-get install -y google-cloud-cli \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Optional: Playwright + Chromium (only if build arg set)
RUN if [ "$INSTALL_PLAYWRIGHT" = "true" ]; then \
        apt-get update && \
        playwright install chromium --with-deps && \
        rm -rf /var/lib/apt/lists/* && \
        echo "Playwright + Chromium installed"; \
    else \
        echo "Playwright skipped (INSTALL_PLAYWRIGHT != true)"; \
    fi

COPY . .

ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os,socket; s=socket.create_connection(('127.0.0.1', int(os.environ.get('PORT', '8080'))), 3); s.close()"

CMD ["python", "server.py", "--transport", "http"]
