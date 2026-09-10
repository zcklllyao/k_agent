"""Classification of transient infrastructure failures for execution tracing."""

from __future__ import annotations

from typing import Any


# These failures describe an unavailable upstream service rather than a failed
# agent decision or a bad artifact. Authentication, invalid-model, and prompt
# errors are intentionally excluded.
_NON_FATAL_MARKERS = (
    "connection error",
    "connecterror",
    "all connection attempts failed",
    "connection refused",
    "connection reset",
    "network is unreachable",
    "server disconnected",
    "peer closed connection",
    "incomplete chunked read",
    "incomplete message body",
    "timed out",
    "timeout",
    "temporarily unavailable",
    "service unavailable",
    "servers are currently overloaded",
    "rate limit",
    "too many requests",
    "concurrency limit",
    "http 429",
    "status code 429",
)


def _error_text(error: Any) -> str:
    if error is None:
        return ""
    parts: list[str] = []
    current = error if isinstance(error, BaseException) else None
    if current is None:
        parts.append(str(error))
    else:
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            parts.append(type(current).__name__)
            parts.append(str(current))
            current = current.__cause__ or current.__context__
    return " ".join(parts).lower()


def is_non_fatal_infrastructure_error(error: Any) -> bool:
    """Return whether *error* is a transient upstream availability failure."""
    message = _error_text(error)
    return any(marker in message for marker in _NON_FATAL_MARKERS)


def is_non_fatal_loop_failure(error: Any) -> bool:
    """Return whether a failed LoopRun came from verifier infrastructure.

    A verifier outage is fail-open by design: the generated artifact remains
    deliverable and must not lower the Loop quality health. A timeout of the
    whole research task is different because the task itself did not finish,
    so those historical failures remain real failures.
    """
    if not is_non_fatal_infrastructure_error(error):
        return False
    message = _error_text(error)
    return not any(
        marker in message
        for marker in (
            "research timed out",
            "research task timed out",
        )
    )


__all__ = [
    "is_non_fatal_infrastructure_error",
    "is_non_fatal_loop_failure",
]
