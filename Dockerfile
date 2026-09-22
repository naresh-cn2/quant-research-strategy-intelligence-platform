# syntax=docker/dockerfile:1
# QRSIP — Docker image + Compose service.
#
# This image is intended for fresh-environment verification and CI,
# not as the only way to run the project (spec §33).
#
# Build:
#   docker build -t qrsip:dev .
#
# Run tests:
#   docker run --rm qrsip:dev make ci
#   docker compose run --rm qrsip make ci
#
# Run CLI:
#   docker run --rm qrsip:dev qrsip doctor

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

FROM base AS build

RUN apt-get update && \
    apt-get install --no-install-recommends -y \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Metadata + manifest first for better layer caching.
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY configs/ ./configs/
COPY tests/ ./tests/
COPY scripts/ ./scripts/
COPY docs/ ./docs/

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip setuptools wheel && \
    pip install -e ".[dev]"

FROM base AS runtime

COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY --from=build /app /app

RUN useradd --create-home --shell /bin/bash qrsipuser && \
    chown -R qrsipuser:qrsipuser /app
USER qrsipuser

ENTRYPOINT ["qrsip"]
CMD ["--help"]

