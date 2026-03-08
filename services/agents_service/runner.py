from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService, VertexAiSessionService

from config import config, AgentMode
from agents.delivery.agent import DEL_AGENT


def build_session_service():
    if config.AGENT_MODE == AgentMode.CLOUD:
        return VertexAiSessionService(
            project=config.VERTEX_PROJECT,
            location=config.VERTEX_LOCATION,
        )
    return InMemorySessionService()


session_service = build_session_service()
runner = Runner(agent=DEL_AGENT, app_name="airport_del", session_service=session_service)
