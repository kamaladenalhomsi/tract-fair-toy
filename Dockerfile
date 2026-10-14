FROM node:22.23.2-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-trixie
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-17 nginx gosu tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --create-home fairtoy
ENV PATH="/usr/lib/postgresql/17/bin:${PATH}" \
    PGDATA=/var/lib/postgresql/data \
    DATABASE_URL="postgresql+psycopg://fairtoy@/fairtoy?host=/var/run/postgresql" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app/backend
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-cache-dir .
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY --from=frontend /build/dist /app/frontend
COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY docker/start.sh /usr/local/bin/fairtoy-start
RUN chmod +x /usr/local/bin/fairtoy-start
EXPOSE 8080
VOLUME ["/var/lib/postgresql/data"]
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)"
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/fairtoy-start"]
