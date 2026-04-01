from typing import Any

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from config import config
from agent.prompts.system import SYSTEM_PROMPT
from tools.flight_plan import make_get_flight_plan
from tools.weather import make_get_atis
from tools.clearance import make_issue_clearance

# Module-level singleton — reused across requests.
_model = LiteLlm(model=config.get_litellm_model())


def build_agent(
    flight_plan: dict | None,
    atis: dict | None,
    context: dict[str, Any],
) -> Agent:
    """
    Build a per-request DEL agent with pre-fetched flight plan and ATIS injected
    into the tools. Clearance data is written back into `context` by issue_clearance.
    """
    return Agent(
        name="DEL",
        model=_model,
        description="ATC Delivery controller — issues IFR departure clearances",
        instruction=SYSTEM_PROMPT,
        tools=[
            make_get_flight_plan(flight_plan),
            make_get_atis(atis),
            make_issue_clearance(context),
        ],
    )
