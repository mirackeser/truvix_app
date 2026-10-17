# Stage 1: Builder
FROM python:3.14-slim AS builder

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock* ./

RUN uv sync --frozen --no-dev

# Stage 2: Runtime
FROM python:3.14-slim

WORKDIR /app

RUN useradd -m -s /bin/bash truvix && \
    chown -R truvix:truvix /app
USER truvix

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY src/ /app/src/

EXPOSE 8001

HEALTHCHECK CMD curl -f http://localhost:8001/healthz || exit 1

CMD ["uvicorn", "truvix_ai.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001"]
