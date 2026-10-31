"""All tests are offline, including packaging/result checks."""
import socket
import pytest


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def prohibited(*args, **kwargs):
        raise AssertionError('Real sockets and DNS are prohibited during tests')
    monkeypatch.setattr(socket, 'socket', prohibited)
    monkeypatch.setattr(socket, 'create_connection', prohibited)
    monkeypatch.setattr(socket, 'getaddrinfo', prohibited)
