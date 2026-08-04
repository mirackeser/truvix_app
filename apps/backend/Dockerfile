# Multi-stage build: dependencies resolve in a builder that carries compilers
# and caches, and only the resulting virtualenv is copied into the runtime.
# The runtime image therefore holds no build toolchain, which both shrinks it
# and removes tools an attacker could use after a compromise.

FROM python:3.14-slim-bookworm AS builder

# uv resolves and installs far faster than pip and honours the committed lock
# file exactly, so a CI build and a production build install identical code.
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /build

# Dependencies are installed before the source is copied, so editing a source
# file does not invalidate the dependency layer.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen


FROM python:3.14-slim-bookworm AS runtime

# curl is needed by the container healthcheck; nothing else is added.
RUN apt-get update \
    && apt-get install --no-install-recommends --yes curl \
    && rm -rf /var/lib/apt/lists/*

# The application runs as an unprivileged user so a container escape does not
# start from root.
RUN groupadd --system --gid 1001 truvix \
    && useradd --system --uid 1001 --gid truvix --create-home truvix

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder --chown=truvix:truvix /build/.venv ./.venv
COPY --from=builder --chown=truvix:truvix /build/src ./src
COPY --from=builder --chown=truvix:truvix /build/alembic ./alembic
COPY --from=builder --chown=truvix:truvix /build/alembic.ini ./

# Uploaded files live on a mounted volume; the directory must exist and be
# writable by the runtime user before the volume is attached.
RUN mkdir -p /app/storage && chown truvix:truvix /app/storage

USER truvix

EXPOSE 8000

# Liveness only: readiness depends on Postgres and Redis, and a dependency
# outage should not make the orchestrator kill and restart a healthy process.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --silent --fail http://localhost:8000/health/live || exit 1

CMD ["uvicorn", "truvix.main:app", "--host", "0.0.0.0", "--port", "8000"]
