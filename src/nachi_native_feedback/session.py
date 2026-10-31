"""Bounded fixed-read poller over an injected byte stream; owns no connection route."""
from __future__ import annotations

import math
import time
from typing import Protocol

from .observer import FeedbackObserver
from .protocol import FeedbackError, build_joint_request


class ByteStream(Protocol):
    def settimeout(self, timeout: float): ...
    def send(self, data: memoryview) -> int: ...
    def recv(self, size: int) -> bytes: ...


class ReadOnlyPoller:
    def __init__(self, stream: ByteStream, observer=None, clock=time.monotonic):
        self.stream = stream
        self.observer = observer if observer is not None else FeedbackObserver()
        self.clock = clock
        self.requests_sent = 0

    def _remaining(self, deadline):
        now = self.clock()
        self.observer._time(now)
        remaining = deadline - now
        if remaining <= 0:
            raise TimeoutError('Fixed read deadline expired')
        self.stream.settimeout(remaining)
        return now

    def poll(self, timeout=2.0, *, session_deadline=None):
        if isinstance(timeout, bool) or not math.isfinite(timeout) or not 0 < timeout <= 5:
            raise ValueError('Response timeout must be in (0, 5] seconds')
        if self.observer.closed or self.observer.failure:
            raise FeedbackError('Session has ended or failed')
        start = self.clock()
        deadline = start + timeout
        if session_deadline is not None:
            if not math.isfinite(session_deadline):
                raise ValueError('Invalid session deadline')
            deadline = min(deadline, session_deadline)
        try:
            if self.observer.decoder.pending_bytes:
                raise FeedbackError('Unread partial trailing frame before a new request')
            request = build_joint_request()
            offset = 0
            while offset < len(request):
                self._remaining(deadline)
                sent = self.stream.send(memoryview(request)[offset:])
                self._remaining(deadline)
                if type(sent) is not int or not 0 < sent <= len(request) - offset:
                    raise FeedbackError('Stream made no valid write progress')
                offset += sent
            self.requests_sent += 1
            total_bytes = 0
            for _ in range(4096):
                self._remaining(deadline)
                chunk = self.stream.recv(4096)
                received = self._remaining(deadline)
                if not isinstance(chunk, bytes) or len(chunk) > 4096:
                    raise FeedbackError('Invalid byte stream read result')
                if not chunk:
                    self.observer.finish()
                    raise FeedbackError('Peer closed before a matching joint reply')
                total_bytes += len(chunk)
                if total_bytes > 131072:
                    raise FeedbackError('Reply byte budget exceeded')
                readings = self.observer.ingest(chunk, received)
                if len(readings) > 1:
                    raise FeedbackError('More than one snapshot in a pull response is ambiguous')
                if readings:
                    return {'reading': readings[0], 'host_transaction_seconds': received - start}
            raise FeedbackError('Reply read-call budget exceeded')
        except (OSError, FeedbackError) as exc:
            self.observer.fail(exc)
            raise FeedbackError(str(exc)) from exc
