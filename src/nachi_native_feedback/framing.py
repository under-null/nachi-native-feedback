"""Bounded incremental envelope codec, based on the two audited Linux libraries."""
from __future__ import annotations

import struct

HEADER = struct.Struct('<HHI')
MAGIC = 0xBA5E
VERSION = 1
MAX_PAYLOAD = 65536


class FrameError(ValueError):
    pass


def encode_frame(payload: bytes) -> bytes:
    if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_PAYLOAD:
        raise FrameError('Payload must contain 1..65536 bytes')
    return HEADER.pack(MAGIC, VERSION, len(payload)) + payload


class FrameDecoder:
    """Never buffers beyond one allowed frame; errors require a new decoder."""

    def __init__(self):
        self._buffer = bytearray()
        self._expected = HEADER.size
        self.failed = False
        self.closed = False

    @property
    def pending_bytes(self):
        return len(self._buffer)

    def feed(self, chunk: bytes) -> list[bytes]:
        if self.failed or self.closed:
            raise FrameError('Stream has ended or failed')
        if not isinstance(chunk, bytes):
            raise TypeError('Stream chunks must be bytes')
        output = []
        offset = 0
        try:
            while offset < len(chunk):
                take = min(self._expected - len(self._buffer), len(chunk) - offset)
                self._buffer.extend(chunk[offset:offset + take])
                offset += take
                if len(self._buffer) != self._expected:
                    continue
                if self._expected == HEADER.size:
                    magic, version, size = HEADER.unpack(self._buffer)
                    if magic != MAGIC or version != VERSION or not 0 < size <= MAX_PAYLOAD:
                        raise FrameError('Invalid magic, version or payload length')
                    self._expected += size
                else:
                    output.append(bytes(self._buffer[HEADER.size:]))
                    self._buffer.clear()
                    self._expected = HEADER.size
        except FrameError:
            self.failed = True
            self._buffer.clear()
            raise
        return output

    def finish(self):
        if self.failed or self.closed:
            raise FrameError('Stream has already ended or failed')
        self.closed = True
        if self._buffer:
            self.failed = True
            self._buffer.clear()
            raise FrameError('EOF inside a frame')
