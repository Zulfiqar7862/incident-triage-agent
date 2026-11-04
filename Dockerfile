# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    DB_PATH=/data/agent.db LOG_FORMAT=json
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY scenarios ./scenarios
COPY runbooks ./runbooks
COPY scripts ./scripts
COPY evals ./evals
COPY --from=frontend /frontend/dist ./frontend/dist

# Run as an unprivileged user; the database lives on a mounted volume.
RUN useradd --system --uid 10001 --home /app agent \
 && mkdir -p /data && chown agent:agent /data
USER agent
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=2).status == 200 else 1)"

# One worker: runs are owned by the process that drives them (see README, "Scaling").
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--timeout-graceful-shutdown", "20", "--no-server-header", "--proxy-headers"]
