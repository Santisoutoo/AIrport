from agents.base.base_agent import BaseAgent
from agents.delivery.prompts.system import SYSTEM_PROMPT

_DEL = BaseAgent(
    name="DEL",
    description="Delivery controller agent",
    instruction=SYSTEM_PROMPT,
    tools=[],
)

# Raw ADK Agent — used by Runner in main.py
DEL_AGENT = _DEL.get_agent()
MODEL_STRING = _DEL.model_string
