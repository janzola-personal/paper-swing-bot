"""Retry wrapper for transient Alpaca / network failures (timeouts, disconnects)."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, TypeVar

log = logging.getLogger("bot")

T = TypeVar("T")

# Attempts total (initial + retries). C3: ×3.
DEFAULT_ATTEMPTS = 3


def is_retryable(exc: BaseException) -> bool:
    """Timeouts and connection blips — not auth / validation errors."""
    if isinstance(exc, (TimeoutError, ConnectionError, ConnectionResetError)):
        return True
    name = type(exc).__name__.lower()
    if "timeout" in name or "temporarily" in name:
        return True
    msg = str(exc).lower()
    if "timeout" in msg or "timed out" in msg or "connection reset" in msg:
        return True
    return False


def call_with_retries(
    fn: Callable[..., T],
    *args: Any,
    attempts: int = DEFAULT_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
    label: str = "alpaca",
    **kwargs: Any,
) -> T:
    """Call fn; on retryable errors retry up to `attempts` total tries."""
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — classify then re-raise
            last = exc
            if not is_retryable(exc) or i >= attempts - 1:
                raise
            delay = 0.5 * (2**i)
            log.warning(
                "%s attempt %s/%s failed (%s); retry in %.1fs",
                label,
                i + 1,
                attempts,
                type(exc).__name__,
                delay,
            )
            sleep(delay)
    assert last is not None
    raise last
