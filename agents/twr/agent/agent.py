import os
from google.adk.agents import Agent

from agent.prompts.system import SYSTEM_PROMPT
from shared.callbacks import log_before, log_after

twr_agent = Agent(
    name="TWR",
    model=os.environ["AGENT_MODEL"],
    description="Pilot on Tower frequency — reads back lineup, takeoff and landing clearances",
    instruction=SYSTEM_PROMPT,
    tools=[],
    before_agent_callback=log_before,
    after_agent_callback=log_after,
)
