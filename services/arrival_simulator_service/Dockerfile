FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Generated from the root pyproject.toml extras -- see scripts/sync_requirements.py
COPY services/arrival_simulator_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/arrival_simulator_service/ .
COPY shared/ ./shared/

ENV PORT=8000
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
