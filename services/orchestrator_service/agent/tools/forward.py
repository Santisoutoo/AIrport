"""The orchestrator's central routing tool.

`forward_to_agent` is what actually talks to the DEL/GND/TWR pilot agents on
Cloud Run. Around that one HTTP call it does five other things, each extracted
into a named helper below so the tool itself reads as the pipeline it is:

    resolve target -> build payload -> call agent -> record reply
                   -> maybe dispatch a taxi plan -> write session state

The order matters and is part of the contract: the debrief entry is written
before the taxi dispatch (so an exploding router still leaves a timeline), and
the state keys `runner.py` reads are written last.
"""

import logging
import os
from typing import Any

import httpx
from google.adk.tools import ToolContext
from session_log import append_agent_reply

logger = logging.getLogger(__name__)

_FLIGHT_PLAN_URL = os.environ.get("FLIGHT_PLAN_SERVICE_URL", "")
_WEATHER_URL = os.environ.get("WEATHER_SERVICE_URL", "")

_ROUTES: dict[str, tuple[str, str]] = {
    "DEL": (os.environ.get("DEL_AGENT_URL", ""), "/agents/delivery/run"),
    "GND": (os.environ.get("GND_AGENT_URL", ""), "/agents/ground/run"),
    "TWR": (os.environ.get("TWR_AGENT_URL", ""), "/agents/tower/run"),
}

_DEFAULT_DEPENDENCY = "DEL"
_CONTEXT_TIMEOUT_S = 5
_AGENT_TIMEOUT_S = 60

# Bookkeeping columns that stay on the orchestrator side — the pilot agents
# receive the clearance fields only.
_NON_CLEARANCE_KEYS = ("registration", "dependency", "source")


# ---------------------------------------------------------------------------
# Target resolution
# ---------------------------------------------------------------------------


def _resolve_dependency(dependency: str) -> str:
    """Normalise the phase the LLM asked for; anything unknown becomes DEL."""
    dep = dependency.upper()
    return dep if dep in _ROUTES else _DEFAULT_DEPENDENCY


# ---------------------------------------------------------------------------
# Context fetching
# ---------------------------------------------------------------------------


def _fetch_context(base_url: str, path: str, label: str, subject: str) -> dict | None:
    """GET ``{base_url}{path}`` and return the JSON body, or None.

    Context is a nice-to-have: an unconfigured service, an unreachable one, or
    any non-200 answer all degrade to None so the pilot agent is still called.

    Args:
        base_url: Service root; empty means "not configured", skip the call.
        path:     Path to append, already containing the subject.
        label:    Human name of the resource, for the warning log only.
        subject:  What is being looked up (registration / ICAO). Empty means
                  there is nothing to ask for, so the call is skipped.
    """
    if not base_url or not subject:
        return None
    try:
        resp = httpx.get(f"{base_url}{path}", timeout=_CONTEXT_TIMEOUT_S)
        return resp.json() if resp.status_code == 200 else None
    except Exception as exc:
        logger.warning("[ORCH] could not fetch %s for %s: %s", label, subject, exc)
        return None


# ---------------------------------------------------------------------------
# Payload building
# ---------------------------------------------------------------------------


def _departure_icao_of(flight_plan: dict | None) -> str:
    """The flight plan service has shipped both spellings of this field."""
    plan = flight_plan or {}
    return plan.get("departure_ICAO") or plan.get("departure_icao", "")


def _del_context(registration: str) -> dict[str, Any]:
    """Flight plan + ATIS for the DEL agent, which has no state of its own."""
    flight_plan = _fetch_context(_FLIGHT_PLAN_URL, f"/plans/{registration}", "flight plan", registration)
    atis = _fetch_context(
        _WEATHER_URL,
        f"/atis/{_departure_icao_of(flight_plan)}",
        "ATIS",
        _departure_icao_of(flight_plan),
    )
    logger.debug("[ORCH] DEL payload — flight_plan=%s atis=%s", bool(flight_plan), bool(atis))
    return {"flight_plan": flight_plan, "atis": atis}


def _clearance_context(
    dep: str,
    registration: str,
    tool_context: ToolContext,
    taxi_route: dict | None,
) -> dict[str, Any]:
    """The clearance record GND/TWR need, taken from the pre-fetched state.

    Returns an empty dict — no ``clearance_data`` key at all — when nothing is
    known about the aircraft and no taxi route was computed.
    """
    known = tool_context.state.get("known_aircraft", [])
    aircraft_data = next((a for a in known if a.get("registration") == registration), {})
    clearance_fields = {k: v for k, v in aircraft_data.items() if k not in _NON_CLEARANCE_KEYS}
    # Merge the pre-computed taxi route so the GND agent knows the exact
    # waypoints and can produce a correct pilot readback.
    if taxi_route and taxi_route.get("success"):
        clearance_fields["taxi_route"] = taxi_route
    if not clearance_fields:
        return {}
    logger.debug("[ORCH] %s payload — clearance_data=%s", dep, clearance_fields)
    return {"clearance_data": clearance_fields}


def _build_payload(
    dep: str,
    registration: str,
    message: str,
    session_id: str,
    tool_context: ToolContext,
    taxi_route: dict | None,
) -> dict[str, Any]:
    """Assemble the agent request: the message plus phase-specific context."""
    payload: dict[str, Any] = {"session_id": session_id, "message": message}
    if dep == "DEL" and registration:
        payload.update(_del_context(registration))
    else:
        payload.update(_clearance_context(dep, registration, tool_context, taxi_route))
    return payload


# ---------------------------------------------------------------------------
# The agent call
# ---------------------------------------------------------------------------


def _call_agent(dep: str, target: str, payload: dict[str, Any]) -> tuple[str, Any, Any]:
    """POST to a pilot agent and unpack its answer.

    Never raises: transport and HTTP failures come back as an ``[ERROR] …``
    reply string, which is what the controller ends up hearing.

    Returns:
        ``(reply, clearance_data, taxi_data)``.
    """
    try:
        resp = httpx.post(target, json=payload, timeout=_AGENT_TIMEOUT_S)
        resp.raise_for_status()
        data = resp.json()
        reply = data.get("reply", "")
        logger.info("[ORCH] %s reply: %r", dep, reply[:100])
        return reply, data.get("clearance_data"), data.get("taxi_data")
    except httpx.HTTPStatusError as exc:
        logger.error("[ORCH] %s HTTP error: %s", dep, exc)
        return f"[ERROR] {dep} agent returned HTTP {exc.response.status_code}", None, None
    except httpx.RequestError as exc:
        logger.error("[ORCH] %s unreachable: %s", dep, exc)
        return f"[ERROR] could not reach {dep} agent at {target}: {exc}", None, None


# ---------------------------------------------------------------------------
# Side effects
# ---------------------------------------------------------------------------


def _record_reply(session_id: str, dep: str, registration: str, reply: str, taxi_data: Any) -> None:
    """Persist the reply for the debrief timeline (fire-and-forget).

    Error replies count: an outage the controller heard belongs in the
    timeline. Without a session there is nowhere to write it.
    """
    if not (reply and session_id):
        return
    append_agent_reply(
        session_id=session_id,
        dep=dep,
        registration=registration,
        callsign=(taxi_data or {}).get("aircraft_registration") if taxi_data else None,
        reply=reply,
        taxi_data=taxi_data,
    )


def _should_dispatch_taxi(dep: str, registration: str, taxi_data: Any) -> bool:
    """GND only, and only once the pilot has acknowledged movement.

    That acknowledgement is either a pushback approval or a non-blank taxi
    route; taxi-only clearances are the typical follow-up after pushback
    completes.
    """
    acknowledged = bool(taxi_data) and (
        taxi_data.get("pushback_approved") or (taxi_data.get("taxi_route") or "").strip()
    )
    return bool(dep == "GND" and registration and acknowledged)


def _dispatch_taxi(
    registration: str,
    message: str,
    reply: str,
    taxi_route: dict | None,
    taxi_data: Any,
    session_id: str,
) -> None:
    """Hand the acknowledged clearance to the shared taxi router.

    Imported lazily: the router pulls in the airport graph, which the tool
    module must not need at import time. Failures are swallowed — the readback
    has already been produced and the controller must still hear it.
    """
    try:
        from shared.services.taxi_router import dispatch_taxi_plan

        merged_clearance = {
            "taxi_route": taxi_route,
            "taxi_data": taxi_data,
            "instruction_text": reply,
        }
        dispatch_taxi_plan(
            merged_clearance,
            pilot_readback_text=reply,
            registration=registration,
            controller_instruction=message,
            callsign=taxi_data.get("aircraft_registration") or registration,
            session_id=session_id,
        )
    except Exception as exc:
        logger.error("[ORCH] taxi dispatch failed for %s: %s", registration, exc)


def _write_state(tool_context: ToolContext, reply: str, dep: str, registration: str, clearance_data: Any) -> None:
    """Publish the outcome to session state — `runner.py` reads these after
    the agent run finishes."""
    tool_context.state["reply"] = reply
    tool_context.state["dependency"] = dep
    tool_context.state["registration"] = registration or None
    tool_context.state["clearance_data"] = clearance_data


# ---------------------------------------------------------------------------
# The tool itself
# ---------------------------------------------------------------------------


def forward_to_agent(
    dependency: str,
    registration: str,
    message: str,
    tool_context: ToolContext,
    taxi_route: dict | None = None,
) -> str:
    """
    Forward the pilot message to the correct ATC controller agent and return
    the agent's clearance or instruction text.

    Args:
        dependency:   Controller to call — "DEL", "GND", or "TWR".
        registration: Aircraft callsign in canonical form (e.g. "EC-MIG").
        message:      The pilot message with the callsign corrected.
        taxi_route:   Pre-computed taxi route dict from get_taxi_route().
                      When provided (GND taxi clearances), it is merged into
                      clearance_data so the GND agent can produce a correct
                      readback without needing to call any routing tool itself.
    """
    dep = _resolve_dependency(dependency)

    agent_url, agent_path = _ROUTES[dep]
    if not agent_url:
        logger.error("[ORCH] %s agent URL not configured", dep)
        return f"[ERROR] {dep} agent is not configured"

    session_id = tool_context.state.get("session_id", "")
    target = f"{agent_url}{agent_path}"

    logger.info("[ORCH] forwarding to %s | reg=%s | session=%s | msg=%r", dep, registration, session_id, message[:80])

    payload = _build_payload(dep, registration, message, session_id, tool_context, taxi_route)
    reply, clearance_data, taxi_data = _call_agent(dep, target, payload)

    _record_reply(session_id, dep, registration, reply, taxi_data)
    if _should_dispatch_taxi(dep, registration, taxi_data):
        _dispatch_taxi(registration, message, reply, taxi_route, taxi_data, session_id)
    _write_state(tool_context, reply, dep, registration, clearance_data)

    return reply
