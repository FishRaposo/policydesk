"""Prove async transports cannot escape the test network boundary."""

import asyncio
import socket
from typing import Any, cast

import pytest


@pytest.mark.skipif(not hasattr(asyncio, "ProactorEventLoop"), reason="Windows proactor route")
def test_proactor_connect_is_blocked_before_os_operation(monkeypatch):
    loop = asyncio.new_event_loop()

    def sentinel(*args, **kwargs):
        raise RuntimeError("Async connect bypassed the test boundary")

    monkeypatch.setattr(cast(Any, loop)._proactor, "connect", sentinel)
    sock = socket.socket()
    sock.setblocking(False)
    try:
        with pytest.raises(AssertionError, match="Network access is forbidden"):
            loop.run_until_complete(loop.sock_connect(sock, ("127.0.0.1", 9)))
    finally:
        sock.close()
        loop.close()


def test_async_creation_and_dns_are_blocked():
    async def exercise():
        loop = asyncio.get_running_loop()
        with pytest.raises(AssertionError, match="Network access is forbidden"):
            await loop.create_connection(asyncio.Protocol, "api.openai.com", 443)

    asyncio.run(exercise())
