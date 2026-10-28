"""Network denial is the default for every in-process test."""

import asyncio
import socket

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    original_pair = socket.socketpair
    original_connect = socket.socket.connect

    def denied(*args, **kwargs):
        raise AssertionError("Network access is forbidden in offline tests")

    async def async_denied(*args, **kwargs):
        return denied(*args, **kwargs)

    def internal_pair(*args, **kwargs):
        # Windows implements asyncio's internal socketpair with a loopback connect.
        # Permit that construction only; all workload connections stay forbidden.
        def internal_connect(sock, address):
            if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
                return original_connect(sock, address)
            return denied(sock, address)

        with monkeypatch.context() as pair_patch:
            pair_patch.setattr(socket.socket, "connect", internal_connect)
            return original_pair(*args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket.socket, "sendto", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "socketpair", internal_pair)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(asyncio.BaseEventLoop, "create_connection", async_denied)
    monkeypatch.setattr(asyncio.BaseEventLoop, "create_datagram_endpoint", async_denied)
    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", async_denied)
    for name in ("SelectorEventLoop", "ProactorEventLoop"):
        loop_class = getattr(asyncio, name, None)
        if loop_class:
            monkeypatch.setattr(loop_class, "sock_connect", async_denied)
    # Ambient SDK headers are not part of this app's fake-key transport tests.
    monkeypatch.setenv("OPENAI_CUSTOM_HEADERS", "")
