"""Small helpers shared across orchestrator modules.

Kept dependency-free (stdlib only) so any module in the service can import it
without pulling in FastAPI, SQLAlchemy or Redis.
"""

from datetime import datetime, timezone


def fmt_ts(ts: float | str | None) -> str:
    """Render a timestamp as ``HH:MM:SS`` (UTC).

    Accepts either a POSIX epoch value (int/float, or a string parseable as
    one by ``float()``) or an ISO-8601 string, with or without a trailing
    ``Z``. Anything unusable renders as ``"--:--:--"`` rather than raising,
    because these strings are only ever shown in the debrief report.
    """
    if ts is None:
        return "--:--:--"
    try:
        if isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
        return dt.strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return "--:--:--"
