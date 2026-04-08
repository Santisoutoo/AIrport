FROM python:3.11-slim

WORKDIR /app

COPY services/orchestrator_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Orchestrator service code
COPY services/orchestrator_service/ .

# Shared modules needed by the taxi router (airport data store, aircraft state, etc.)
COPY shared/ ./shared/

# Taxi graph engine (AirportGraph, data_parser, models)
COPY plugins/GND/ ./plugins/GND/

COPY services/orchestrator_service/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENV PORT=8006
EXPOSE 8006

ENTRYPOINT ["/docker-entrypoint.sh"]
