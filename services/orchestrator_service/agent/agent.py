import os

from google.adk.agents import Agent

from agent.prompts import SYSTEM_PROMPT
from agent.tools.aircraft import get_known_aircraft
from agent.tools.advance_to_gnd import advance_to_gnd
from agent.tools.advance_twr import advance_to_twr
from agent.tools.forward import forward_to_agent
from agent.tools.taxi_route import get_taxi_route
from shared.callbacks import log_before, log_after

orch_agent = Agent(
    name="ORCH",
    model=os.environ["AGENT_MODEL"],
    description="ATC orchestrator — routes pilot messages to DEL, GND, or TWR agents",
    instruction=SYSTEM_PROMPT,
    tools=[get_known_aircraft, advance_to_gnd, advance_to_twr, get_taxi_route, forward_to_agent],
    before_agent_callback=log_before,
    after_agent_callback=log_after,
)
