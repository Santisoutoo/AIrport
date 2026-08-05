"""DEL agent service — the generic pilot FastAPI app configured for Delivery."""

import logging
import os

from shared.agent_app import AgentAppConfig, create_app

from runner import run_agent

logger = logging.getLogger(__name__)

CONFIG = AgentAppConfig(
    label="DEL",
    role="delivery",
    title="AIrport DEL Agent",
    version="0.2.0",
    description="ATC Delivery controller — issues IFR departure clearances",
    data_key="clearance_data",
    context_fields=("flight_plan", "atis"),
)

app = create_app(CONFIG, run_agent, logger=logger)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
