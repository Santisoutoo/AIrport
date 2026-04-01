from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from config import config
from agents.delivery.prompts.system import SYSTEM_PROMPT
from agents.delivery.tools.clearance import make_issue_clearance

MODEL_STRING = config.get_litellm_model()

# Module-level singleton — used by /info endpoint only
DEL_AGENT = Agent(
    name="DEL",
    model=LiteLlm(model=MODEL_STRING),
    description="Delivery controller agent",
    instruction=SYSTEM_PROMPT,
    tools=[],
)


def build_del_agent(context: dict) -> Agent:
    """Build a fresh DEL agent per-request, binding issue_clearance to context."""
    return Agent(
        name="DEL",
        model=LiteLlm(model=MODEL_STRING),
        description="Delivery controller agent",
        instruction=SYSTEM_PROMPT,
        tools=[make_issue_clearance(context)],
    )
