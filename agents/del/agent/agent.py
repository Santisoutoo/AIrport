import os
from google.adk.agents import Agent

from agent.prompts.system import SYSTEM_PROMPT
from shared.callbacks import log_before, log_after

del_agent = Agent(
    name="DEL",
    model=os.environ["AGENT_MODEL"],
    description="ATC Delivery controller — issues IFR departure clearances",
    instruction=SYSTEM_PROMPT,
    tools=[],
    before_agent_callback=log_before,
    after_agent_callback=log_after,
)
