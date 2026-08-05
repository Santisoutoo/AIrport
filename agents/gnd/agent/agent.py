import os

from google.adk.agents import Agent

from agent.prompts.system import SYSTEM_PROMPT
from shared.callbacks import log_after, log_before

gnd_agent = Agent(
    name="GND",
    model=os.environ["AGENT_MODEL"],
    description="ATC Ground controller — issues pushback and taxi instructions",
    instruction=SYSTEM_PROMPT,
    tools=[],
    before_agent_callback=log_before,
    after_agent_callback=log_after,
)
