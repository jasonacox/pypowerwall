# TARGETARCH and TARGETVARIANT are injected automatically by buildx.
# They must be declared before the first FROM to be usable in FROM instructions.
# For linux/arm/v8:  TARGETARCH=arm, TARGETVARIANT=v8  → selects base-armv8
# For linux/amd64:   TARGETARCH=amd64, TARGETVARIANT=""  → selects base-amd64
# For linux/arm64:   TARGETARCH=arm64, TARGETVARIANT=""  → selects base-arm64
ARG TARGETARCH
ARG TARGETVARIANT

# Base images per platform — all targets use Debian-slim to avoid Alpine/musl
# TLS fingerprint issues that cause Tesla token refresh 403 errors.
# See: https://github.com/jasonacox/pypowerwall/issues/344
FROM python:3.10-slim AS base-amd64
FROM python:3.10-slim AS base-arm64
FROM python:3.10-slim AS base-armv7
FROM python:3.10-slim AS base-armv8
FROM base-${TARGETARCH}${TARGETVARIANT}

WORKDIR /app

# Install system dependencies (package manager differs by base image)
RUN if command -v apk > /dev/null; then \
      apk add --no-cache git curl; \
    else \
      apt-get update && apt-get install -y --no-install-recommends git curl gcc libffi-dev python3-dev && rm -rf /var/lib/apt/lists/*; \
    fi

# Install pypowerwall and proxy dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# Copy proxy server files (only runtime-needed files)
COPY server.py transform.py __init__.py /app/
COPY web/ /app/web/
EXPOSE 8675
CMD ["python3", "server.py"]
