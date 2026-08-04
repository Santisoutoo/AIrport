# Controller HMI Service
# Stage 1: build the frontend (Vite + TypeScript) into static/
FROM node:22-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Stage 2: FastAPI backend serving the built static/
FROM python:3.11-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install base dependencies
RUN pip install --no-cache-dir \
    fastapi==0.109.0 \
    uvicorn[standard]==0.27.0 \
    pydantic==2.5.3 \
    httpx==0.26.0 \
    folium==0.15.1 \
    xplane-airports==4.0.1 \
    requests>=2.31.0 \
    psycopg2-binary \
    redis

# Copy application code (static/ from the build stage; note the compose bind
# mount ./static:/app/static shadows it in dev — run `npm run build` on the
# host there, see frontend/README.md)
COPY main.py .
COPY api/ ./api/
COPY --from=frontend-build /app/static ./static

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
