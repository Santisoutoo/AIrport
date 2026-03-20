from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService, VertexAiSessionService

from config import config, AgentMode
from prompts.system import SYSTEM_PROMPT


def build_runner() -> Runner:
    agent = Agent(
        name="DEL",
        model=LiteLlm(model=config.get_litellm_model()),
        description="Delivery controller agent — issues flight plan clearances",
        instruction=SYSTEM_PROMPT,
        tools=[],
    )

    if config.AGENT_MODE == AgentMode.CLOUD:
        session_service = VertexAiSessionService(
            project=config.VERTEX_PROJECT,
            location=config.VERTEX_LOCATION,
        )
    else:
        session_service = InMemorySessionService()

    return Runner(agent=agent, app_name="del_agent", session_service=session_service)
