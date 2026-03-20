from config import config

_AGENT_MAP = {
    "DEL": ("DEL", config.DEL_AGENT_URL),
    "GND": ("GND", config.GND_AGENT_URL),
    "TWR": ("TWR", config.TWR_AGENT_URL),
}


def agent_name_to_url(agent: str) -> tuple[str, str]:
    """Return (agent_name, agent_url) for a given agent identifier (DEL/GND/TWR).

    Raises ValueError if the agent is unknown.
    """
    key = agent.strip().upper()
    if key not in _AGENT_MAP:
        raise ValueError(f"Unknown agent '{agent}'. Must be one of: {', '.join(_AGENT_MAP)}")
    return _AGENT_MAP[key]
