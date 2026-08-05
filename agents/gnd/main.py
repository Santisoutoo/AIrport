"""GND agent service — the generic pilot FastAPI app configured for Ground."""

import logging
import os

from shared.agent_app import AgentAppConfig, create_app

from runner import run_agent

logger = logging.getLogger(__name__)

CONFIG = AgentAppConfig(
    label="GND",
    role="ground",
    title="AIrport GND Agent",
    version="0.1.0",
    description="ATC Ground controller — issues pushback and taxi instructions",
    data_key="taxi_data",
    context_fields=("clearance_data",),
)

app = create_app(CONFIG, run_agent, logger=logger)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
