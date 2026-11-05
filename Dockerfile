FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_ACCOUNT_MODE=supabase
RUN npm run build

FROM python:3.13-slim-bookworm
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 ACADEMY_SERVE_FRONTEND=1
COPY requirements-cloud.txt ./
RUN pip install --no-cache-dir -r requirements-cloud.txt
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY migrations/ ./migrations/
COPY alembic.ini ./
COPY --from=frontend /build/frontend/dist ./frontend/dist/
RUN useradd --uid 10001 --create-home academy
USER academy
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
