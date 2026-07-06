# ─────────────────────────────────────────────────────────────────────────
# RAEL — single-service production image (Railway-ready).
# Stage 1 builds the React frontend; stage 2 runs FastAPI, which serves the
# built SPA itself (same-origin /api and /ws — no CORS, no proxy).
# ─────────────────────────────────────────────────────────────────────────

FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY agents/ agents/
COPY rael.yaml ./
COPY --from=frontend /build/dist frontend/dist

# Railway injects PORT; default to 8000 for local runs.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
