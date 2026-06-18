import asyncio
from unittest.mock import MagicMock

import pytest

from notetaker.utils.retry import retry


def test_succeeds_first_try():
    mock = MagicMock(return_value="ok")

    @retry(attempts=3, delay=0)
    def fn():
        return mock()

    assert fn() == "ok"
    assert mock.call_count == 1


def test_retries_on_transient_error():
    call_count = 0

    @retry(attempts=3, delay=0)
    def fn():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("transient")
        return "success"

    assert fn() == "success"
    assert call_count == 3


def test_raises_after_exhaustion():
    @retry(attempts=2, delay=0)
    def fn():
        raise RuntimeError("always fails")

    with pytest.raises(RuntimeError, match="always fails"):
        fn()


def test_async_retries():
    call_count = 0

    @retry(attempts=3, delay=0)
    async def afn():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise IOError("transient")
        return "done"

    result = asyncio.run(afn())
    assert result == "done"
    assert call_count == 2


def test_async_raises_after_exhaustion():
    @retry(attempts=2, delay=0)
    async def afn():
        raise ConnectionError("always fails")

    with pytest.raises(ConnectionError):
        asyncio.run(afn())
