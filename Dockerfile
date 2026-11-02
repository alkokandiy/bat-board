# Build frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ .
# The commit being built. Railway passes this; it also busts the build cache
# for this stage, which is how a stale frontend shipped alongside a current
# backend for weeks without anyone being able to tell.
ARG BUILD_SHA=dev
ENV VITE_BUILD_SHA=$BUILD_SHA
RUN npm run build

# Build backend
FROM python:3.12-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/ .

ARG BUILD_SHA=dev
ENV BUILD_SHA=$BUILD_SHA

COPY --from=frontend-builder /app/frontend/dist /app/static

EXPOSE 8000

# Single-user: 1 worker is plenty (was 4). Override with WEB_CONCURRENCY=2 if needed.
# Railway provides PORT env, default to 8000 locally.
CMD sh -c 'gunicorn main:app --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-1} --timeout 60 --keep-alive 5 --log-level info'