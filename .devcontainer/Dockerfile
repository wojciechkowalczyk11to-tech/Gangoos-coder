FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    git \
    gnome-keyring \
    libclang-dev \
    libdbus-1-dev \
    libprotobuf-dev \
    libssl-dev \
    libxcb1-dev \
    pkg-config \
    protobuf-compiler \
    unzip \
    && rm -rf /var/lib/apt/lists/*
