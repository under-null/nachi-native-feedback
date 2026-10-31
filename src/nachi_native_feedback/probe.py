"""Bounded TCP joint probe. Default is plan-only and opens no socket.

Controller use requires specific user approval under AGENTS.md. An execute flag
is a local operator action, not permission for an agent to run a hardware test.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import ipaddress
import time

from .observer import FeedbackObserver
from .protocol import FeedbackError, build_joint_request
from .session import ReadOnlyPoller


@dataclass(frozen=True)
class ProbePlan:
    host: str
    port: int = 9876
    samples: int = 1
    response_timeout: float = 2.0
    duration: float = 5.0
    source_address: str | None = None

    def __post_init__(self):
        if type(self.host) is not str:
            raise ValueError('Host must be an explicit IPv4 string')
        address = ipaddress.IPv4Address(self.host)
        if address.is_unspecified or address.is_multicast or address.is_reserved or str(address) == '255.255.255.255':
            raise ValueError('An explicit unicast IPv4 endpoint is required')
        if self.source_address is not None:
            if type(self.source_address) is not str:
                raise ValueError('Source address must be a literal IPv4 string')
            source = ipaddress.IPv4Address(self.source_address)
            if source.is_unspecified or source.is_multicast or source.is_reserved or str(source) == '255.255.255.255' or source == address:
                raise ValueError('Invalid explicit local source address')
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError('Invalid TCP port')
        if type(self.samples) is not int or not 1 <= self.samples <= 10:
            raise ValueError('Sample count must be 1..10')
        for value, limit in ((self.response_timeout, 5), (self.duration, 15)):
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 < value <= limit:
                raise ValueError('Invalid bounded probe timing')

    def describe(self):
        frame = build_joint_request()
        return {**asdict(self), 'mode': 'PLAN_ONLY', 'connections': 1, 'automatic_reconnect': False,
                'max_read_requests': self.samples, 'outbound_frame_sha256': hashlib.sha256(frame).hexdigest(),
                'request_xml': frame[8:].decode('utf-8'), 'controller_contacted': False,
                'network_settings_changes': False, 'operation_builders': [],
                'future_execution_requires_specific_user_approval': True}


def execute_probe(plan: ProbePlan, *, execute=False, clock=time.monotonic):
    if execute is not True:
        return plan.describe()
    # This explicit connection route is never used by demo, replay, request
    # export, plan-only execution or ordinary package imports.
    import socket

    observer = FeedbackObserver(stale_after=plan.response_timeout)
    records = []
    wire = None
    deadline = clock() + plan.duration
    connection_attempted = False
    local_endpoint = None
    remote_endpoint = None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream:
            connection_attempted = True
            stream.settimeout(min(plan.response_timeout, plan.duration))
            if plan.source_address is not None:
                stream.bind((plan.source_address, 0))
            stream.connect((plan.host, plan.port))
            local_endpoint = stream.getsockname()
            remote_endpoint = stream.getpeername()
            if (plan.source_address is not None and local_endpoint[0] != plan.source_address) or tuple(remote_endpoint) != (plan.host, plan.port):
                raise FeedbackError('Connected socket endpoint did not match the approved source/target')
            wire = _CaptureStream(stream)
            poller = ReadOnlyPoller(wire, observer, clock)
            for _ in range(plan.samples):
                item = poller.poll(plan.response_timeout, session_deadline=deadline)
                records.append({'reading': asdict(item['reading']),
                                'host_transaction_seconds': item['host_transaction_seconds']})
            observer.finish()
    except (OSError, FeedbackError) as exc:
        observer.fail(exc)
        # No retry, heartbeat sender, negotiation guessing or fallback operation.
    return {'mode': 'EXPLICIT_TCP_PROBE', 'endpoint': f'{plan.host}:{plan.port}',
            'connection_attempted': connection_attempted, 'records': records,
            'local_endpoint': local_endpoint, 'remote_endpoint': remote_endpoint,
            'final_state': observer.snapshot(clock()), 'elapsed_limit_seconds': plan.duration,
            'compatibility_verified': False, 'controller_measurement_age_known': False,
            'wire_capture': wire.report() if wire is not None else None}


class _CaptureStream:
    """Bounded wire evidence for a future test; no independent I/O entry point."""
    def __init__(self, stream, max_rx_bytes=131072):
        if type(max_rx_bytes) is not int or not 1 <= max_rx_bytes <= 4 * 1024 * 1024:
            raise ValueError('Invalid bounded receive-capture size')
        self.stream = stream
        self.max_rx_bytes = max_rx_bytes
        self.tx = bytearray()
        self.rx = bytearray()

    def settimeout(self, value):
        self.stream.settimeout(value)

    def send(self, data):
        count = self.stream.send(data)
        if type(count) is int and 0 < count <= len(data):
            self.tx.extend(data[:count])
        return count

    def recv(self, size):
        chunk = self.stream.recv(size)
        if len(self.rx) + len(chunk) > self.max_rx_bytes:
            raise FeedbackError('Session wire-capture budget exceeded')
        self.rx.extend(chunk)
        return chunk

    def report(self):
        return {'tx_bytes': len(self.tx), 'tx_sha256': hashlib.sha256(self.tx).hexdigest(),
                'rx_bytes': len(self.rx), 'rx_sha256': hashlib.sha256(self.rx).hexdigest(),
                'rx_hex': self.rx.hex(), 'source': 'explicit_probe_peer_unverified'}
