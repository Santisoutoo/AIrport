"""Fake Google ADK Runner for unit + integration tests.

The orchestrator service builds a Runner with ``orch_agent`` and iterates
``runner.run_async()``. Each yielded event may either be a tool invocation
(side-effect on tool_context.state) or the final user-facing response.

For tests we replace ``runner.Runner`` with ``FakeADKRunner``, which is
programmed via ``.script(state_updates=..., final_text=...)``: every call
to ``run_async`` applies the state updates to the session via the live
session_service and yields exactly one final event.

This lets tests drive the orchestrator end-to-end without needing the real
LLM: just say "when run_async is called next, leave state with
``advance_registration_gnd='EC-MIG'``".
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable


class _FakeEvent:
    """Mimic the subset of google.adk Event interface that runner.py uses."""

    def __init__(self, text: str = "", is_final: bool = True):
        self._is_final = is_final
        # ``runner.py`` reads event.content.parts[i].text
        self.content = SimpleNamespace(parts=[SimpleNamespace(text=text)])

    def is_final_response(self) -> bool:
        return self._is_final


class FakeADKRunner:
    """Programmable stand-in for google.adk.runners.Runner.

    Usage in tests:

        fake_runner = FakeADKRunner()
        fake_runner.script(
            state_updates={"reply": "ok", "dependency": "DEL", "registration": "EC-MIG"},
            final_text="Cleared to LEPA",
        )
        monkeypatch.setattr(runner, "Runner", lambda **_: fake_runner)
    """

    def __init__(self, *, agent: Any = None, app_name: str = "", session_service: Any = None, **__):
        self.agent = agent
        self.app_name = app_name
        self.session_service = session_service
        self._next_state_updates: dict | Callable[[dict], dict] | None = None
        self._next_final_text: str = ""
        self.calls: list[dict] = []

    def script(
        self,
        *,
        state_updates: dict | Callable[[dict], dict] | None = None,
        final_text: str = "",
    ) -> None:
        """Program the next call to run_async."""
        self._next_state_updates = state_updates
        self._next_final_text = final_text

    async def run_async(self, *, user_id: str, session_id: str, new_message: Any):
        self.calls.append({"user_id": user_id, "session_id": session_id, "new_message": new_message})

        # Apply scripted state mutations to the live session before yielding
        # the final event -- this is the same observable effect a real tool
        # invocation would have on state.
        if self._next_state_updates is not None and self.session_service is not None:
            session = await self.session_service.get_session(
                app_name=self.app_name, user_id=user_id, session_id=session_id
            )
            if session is not None:
                if callable(self._next_state_updates):
                    self._next_state_updates(session.state)
                else:
                    session.state.update(self._next_state_updates)

        yield _FakeEvent(text=self._next_final_text, is_final=True)


def install_fake_runner(monkeypatch, module) -> FakeADKRunner:
    """Install a FakeADKRunner singleton into ``module.Runner`` and return it.

    The returned instance is what every ``Runner(...)`` constructor invocation
    will yield, so tests can call ``fake.script(...)`` once and let the
    production code instantiate it lazily.
    """
    fake = FakeADKRunner()

    def _factory(*args, **kwargs):
        fake.agent = kwargs.get("agent", fake.agent)
        fake.app_name = kwargs.get("app_name", fake.app_name)
        fake.session_service = kwargs.get("session_service", fake.session_service)
        return fake

    monkeypatch.setattr(module, "Runner", _factory)
    return fake
