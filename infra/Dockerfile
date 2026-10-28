FROM node:24-bookworm-slim AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
RUN npm run build

FROM python:3.13-slim-bookworm AS backend
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates libpango-1.0-0 libpangoft2-1.0-0 fonts-dejavu-core && \
    install -d /usr/share/postgresql-common/pgdg && \
    curl --fail --silent --show-error https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc && \
    echo 'deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main' > /etc/apt/sources.list.d/pgdg.list && \
    apt-get update && apt-get install -y --no-install-recommends postgresql-client-18 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
WORKDIR /workspace/apps/backend
COPY apps/backend/pyproject.toml apps/backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY apps/backend/src ./src
COPY apps/backend/migrations ./migrations
RUN uv sync --frozen --no-dev && useradd --uid 1000 --create-home assistant && mkdir -p /data && chown assistant:assistant /data
COPY --from=web /web/dist /workspace/apps/web/dist
ENV PATH="/workspace/apps/backend/.venv/bin:$PATH" PYTHONUNBUFFERED=1 WEB_DIST=/workspace/apps/web/dist DATA_DIR=/data
USER assistant
EXPOSE 8000
CMD ["uvicorn", "email_agentic.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
