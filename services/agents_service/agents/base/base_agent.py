from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from config import config


class BaseAgent:
    """Wraps an ADK Agent using LiteLLM as the model backend."""

    def __init__(
        self,
        name: str,
        description: str,
        instruction: str,
        tools: list,
    ):
        self.model_string = config.get_litellm_model()
        self.agent: Agent = Agent(
            name=name,
            model=LiteLlm(model=self.model_string),
            description=description,
            instruction=instruction,
            tools=tools,
        )

    def get_agent(self) -> Agent:
        return self.agent
