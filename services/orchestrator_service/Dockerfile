FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8006
EXPOSE 8006
# Internal port 8006 — mapped to host 8007 in docker-compose to avoid conflict with asr_service

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
