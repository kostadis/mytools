from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Callable
from typing import TypeVar

from notetaker.utils.logging import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable)


def retry(attempts: int = 3, delay: float = 1.0, exceptions: tuple = (Exception,)):
    """
    Decorator that retries the wrapped function on failure.

    Works for both sync and async functions. Each retry is preceded by a fixed
    `delay`-second sleep. After exhausting all attempts, the last exception is
    re-raised.
    """
    def decorator(func: F) -> F:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                last_exc: Exception | None = None
                for attempt in range(1, attempts + 1):
                    try:
                        return await func(*args, **kwargs)
                    except exceptions as exc:
                        last_exc = exc
                        if attempt < attempts:
                            logger.debug(
                                "retry.attempt",
                                func=func.__qualname__,
                                attempt=attempt,
                                max_attempts=attempts,
                                error=str(exc),
                            )
                            await asyncio.sleep(delay)
                        else:
                            logger.warning(
                                "retry.exhausted",
                                func=func.__qualname__,
                                attempts=attempts,
                                error=str(exc),
                            )
                raise last_exc
            return async_wrapper  # type: ignore[return-value]
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                last_exc: Exception | None = None
                for attempt in range(1, attempts + 1):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as exc:
                        last_exc = exc
                        if attempt < attempts:
                            logger.debug(
                                "retry.attempt",
                                func=func.__qualname__,
                                attempt=attempt,
                                max_attempts=attempts,
                                error=str(exc),
                            )
                            time.sleep(delay)
                        else:
                            logger.warning(
                                "retry.exhausted",
                                func=func.__qualname__,
                                attempts=attempts,
                                error=str(exc),
                            )
                raise last_exc
            return sync_wrapper  # type: ignore[return-value]
    return decorator
