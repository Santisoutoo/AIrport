"""Request models for the ASR API.

Keeps the endpoint signatures short (issue #64) and gives the multipart fields a
single validated home instead of a flat parameter list on the handler.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import Form
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def parse_list_field(raw: str | None) -> list[str]:
    """Parse a Form field that may be a JSON array (["A", "B"]) or a CSV string ("A,B")."""
    if not raw:
        return []
    raw = raw.strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except json.JSONDecodeError:
            logger.warning("[ASR] could not parse '%s' as JSON list — falling back to CSV", raw)
    return [v.strip() for v in raw.split(",") if v.strip()]


class TranscribeOptions(BaseModel):
    """Non-file fields of ``POST /transcribe``.

    The audio itself stays an ``UploadFile`` parameter on the endpoint; only the
    surrounding switches are grouped here. Bound to the request through
    :meth:`as_form`, so the multipart contract is unchanged — same field names,
    same defaults, same "everything is optional except the audio" behavior for
    the HMI proxy, the X-Plane plugin and ``agents_evaluation/benchmark_asr.py``.
    """

    session_id: str = ""
    apply_corrections: bool = True
    use_initial_prompt: bool = True
    context_mode: str = "generic"
    session_callsigns: Optional[str] = None
    session_sids: Optional[str] = None
    llm_fallback: Optional[bool] = None

    @classmethod
    def as_form(
        cls,
        session_id: str = Form(""),
        apply_corrections: bool = Form(True),
        use_initial_prompt: bool = Form(True),
        context_mode: str = Form("generic"),
        session_callsigns: str | None = Form(None),
        session_sids: str | None = Form(None),
        llm_fallback: bool | None = Form(None),
    ) -> "TranscribeOptions":
        """FastAPI dependency: collect the multipart fields into a ``TranscribeOptions``."""
        return cls(
            session_id=session_id,
            apply_corrections=apply_corrections,
            use_initial_prompt=use_initial_prompt,
            context_mode=context_mode,
            session_callsigns=session_callsigns,
            session_sids=session_sids,
            llm_fallback=llm_fallback,
        )

    @property
    def callsigns(self) -> list[str]:
        """Active callsigns for this session, JSON array or CSV."""
        return parse_list_field(self.session_callsigns)

    @property
    def sids(self) -> list[str]:
        """Expected SIDs for this session, JSON array or CSV."""
        return parse_list_field(self.session_sids)
