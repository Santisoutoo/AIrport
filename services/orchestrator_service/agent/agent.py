import os

from google.adk.agents import Agent

from agent.prompts import SYSTEM_PROMPT
from agent.tools.aircraft import get_known_aircraft
from agent.tools.forward import forward_to_agent
from shared.callbacks import log_before, log_after

orch_agent = Agent(
    name="ORCH",
    model=os.environ["AGENT_MODEL"],
    description="ATC orchestrator — routes pilot messages to DEL, GND, or TWR agents",
    instruction=SYSTEM_PROMPT,
    tools=[get_known_aircraft, forward_to_agent],
    before_agent_callback=log_before,
    after_agent_callback=log_after,
)
